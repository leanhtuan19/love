"""Exercise prefork-worker lock renewal without touching real private storage."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
import unittest
from unittest import mock

from filelock import FileLock as NativeFileLock
from werkzeug.security import generate_password_hash

import server


NativeRLock = threading.RLock


class PidBoundLock:
    """Reproduce modern filelock's fork guard while using an actual OS lock."""

    def __init__(self, delegate, kind):
        self.delegate = delegate
        self.kind = kind
        self.pid = os.getpid()
        self.entries = 0

    def __enter__(self):
        if self.pid != os.getpid():
            raise RuntimeError(
                f"{self.kind} was inherited across fork; construct a new instance")
        self.entries += 1
        self.delegate.__enter__()
        return self

    def __exit__(self, *args):
        return self.delegate.__exit__(*args)


@contextmanager
def guarded_factories(guard_threads=False):
    file_locks, thread_locks = [], []

    def file_factory(*args, **kwargs):
        lock = PidBoundLock(NativeFileLock(*args, **kwargs), "UnixFileLock")
        if Path(lock.delegate.lock_file).name == "letters.lock":
            file_locks.append(lock)
        return lock

    def thread_factory(*args, **kwargs):
        lock = PidBoundLock(NativeRLock(*args, **kwargs), "RLock")
        thread_locks.append(lock)
        return lock

    with mock.patch.object(server, "FileLock", side_effect=file_factory):
        if guard_threads:
            with mock.patch.object(server.threading, "RLock", side_effect=thread_factory):
                yield file_locks, thread_locks
        else:
            yield file_locks, thread_locks


class ForkLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = secrets.token_urlsafe(24)
        cls.password_hash = generate_password_hash(cls.password, method="scrypt:32768:8:1")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="lovedays-fork-lock-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def create_app(self):
        return server.create_app({"TESTING": True, "DATA_DIR": str(self.directory),
                                  "PASSWORD_HASH": self.password_hash,
                                  "PUBLIC_ORIGIN": "http://localhost",
                                  "SQLITE_JOURNAL_MODE": "DELETE"})

    def log_in(self, app):
        client = app.test_client()
        token = client.get("/api/session").get_json()["csrfToken"]
        response = client.post("/api/auth", json={"password": self.password},
                               headers={"Origin": "http://localhost", "X-CSRF-Token": token})
        self.assertEqual(response.status_code, 200, response.get_json())
        headers = {"Origin": "http://localhost",
                   "X-CSRF-Token": response.get_json()["csrfToken"]}
        return client, headers

    @staticmethod
    def payload(title):
        return {"senderId": "tuan", "senderName": "Lê Anh Tuấn",
                "recipientId": "thu", "recipientName": "Lê Phạm Anh Thư",
                "type": "love-letter", "title": title,
                "content": "Một dòng tiếng Việt.\nMột lời yêu thương."}

    def test_pid_change_renews_both_locks_once_and_keeps_nested_locking(self):
        pid = [os.getpid()]
        with mock.patch.object(server.os, "getpid", side_effect=lambda: pid[0]):
            with guarded_factories(guard_threads=True) as (files, threads):
                store = server.LetterStore(self.directory)
                self.assertEqual((len(files), len(threads)), (1, 1))
                original_files, original_threads = tuple(files), tuple(threads)
                pid[0] += 1
                for _ in range(3):
                    with store.locked():
                        with store.locked():
                            self.assertEqual(store.read(), {"schemaVersion": 1, "letters": []})
                            store.write(store.read())
                self.assertEqual((len(files), len(threads)), (2, 2))
                self.assertEqual(files[-1].delegate.timeout, 15)
                self.assertEqual(files[-1].pid, pid[0])
                self.assertEqual(threads[-1].pid, pid[0])
                self.assertEqual(original_files[0].entries, 1)
                self.assertEqual(original_threads[0].entries, 1)
                pid[0] += 1
                with store.locked():
                    store.read()
                self.assertEqual((len(files), len(threads)), (3, 3))

    def test_authenticated_list_and_crud_survive_worker_pid_change(self):
        pid = [os.getpid()]
        with mock.patch.object(server.os, "getpid", side_effect=lambda: pid[0]):
            with guarded_factories() as (files, _):
                app = self.create_app()
                client, headers = self.log_in(app)
                first = client.post("/api/letters", json=self.payload("Trước khi fork"), headers=headers)
                self.assertEqual(first.status_code, 201, first.get_json())
                first_id = first.get_json()["letter"]["id"]
                original_bytes = (self.directory / "letters.json").read_bytes()
                pid[0] += 1
                listed = client.get("/api/letters")
                self.assertEqual(listed.status_code, 200, listed.get_json())
                self.assertEqual([item["id"] for item in listed.get_json()["letters"]], [first_id])
                self.assertEqual((self.directory / "letters.json").read_bytes(), original_bytes)
                second = client.post("/api/letters", json=self.payload("Sau khi fork"), headers=headers)
                self.assertEqual(second.status_code, 201, second.get_json())
                second_id = second.get_json()["letter"]["id"]
                changed = client.put(f"/api/letters/{first_id}", json=self.payload("Đã sửa"), headers=headers)
                self.assertEqual(changed.status_code, 200, changed.get_json())
                self.assertEqual(changed.get_json()["letter"]["id"], first_id)
                saved = json.loads((self.directory / "letters.json").read_text(encoding="utf-8"))
                self.assertEqual({item["id"] for item in saved["letters"]}, {first_id, second_id})
                deleted = client.delete(f"/api/letters/{second_id}", headers=headers)
                self.assertEqual(deleted.status_code, 200, deleted.get_json())
                self.assertEqual(client.get(f"/api/letters/{second_id}").status_code, 404)
                detail = client.get(f"/api/letters/{first_id}")
                self.assertEqual(detail.status_code, 200, detail.get_json())
                self.assertEqual(detail.get_json()["letter"]["title"], "Đã sửa")
                self.assertEqual(len(files), 2)

    def test_external_lock_contention_after_pid_change_still_returns_503(self):
        pid = [os.getpid()]
        with mock.patch.object(server.os, "getpid", side_effect=lambda: pid[0]):
            with guarded_factories() as (files, _):
                app = self.create_app()
                client, _ = self.log_in(app)
                pid[0] += 1
                self.assertEqual(client.get("/api/letters").status_code, 200)
                files[-1].delegate.timeout = 0
                acquired, release = threading.Event(), threading.Event()

                def hold_external_lock():
                    with NativeFileLock(str(self.directory / "letters.lock"), timeout=1):
                        acquired.set()
                        if not release.wait(5):
                            raise AssertionError("External lock holder was not released")

                with ThreadPoolExecutor(max_workers=1) as executor:
                    holder = executor.submit(hold_external_lock)
                    try:
                        self.assertTrue(acquired.wait(3), "External lock was not acquired")
                        busy = client.get("/api/letters")
                        self.assertEqual(busy.status_code, 503, busy.get_json())
                        self.assertEqual(busy.get_json()["error"], "storage_busy")
                    finally:
                        release.set()
                    holder.result(timeout=3)
                self.assertEqual(client.get("/api/letters").status_code, 200)
                self.assertEqual(len(files), 2)

    @unittest.skipUnless(hasattr(os, "fork"), "Actual prefork regression requires POSIX os.fork")
    def test_actual_fork_worker_renews_inherited_locks(self):
        import select
        import signal

        with guarded_factories(guard_threads=True):
            store = server.LetterStore(self.directory)
            read_fd, write_fd = os.pipe()
            child_pid = os.fork()
            if child_pid == 0:
                os.close(read_fd)
                try:
                    with store.locked():
                        with store.locked():
                            store.write(store.read())
                    os.write(write_fd, b"ok")
                    os._exit(0)
                except BaseException as exc:
                    os.write(write_fd, repr(exc).encode("utf-8")[:2000])
                    os._exit(1)
            os.close(write_fd)
            child_finished = False
            try:
                readable, _, _ = select.select([read_fd], [], [], 10)
                self.assertTrue(readable, "Forked worker failed to finish within 10 seconds")
                message = os.read(read_fd, 4096).decode("utf-8")
                _, status = os.waitpid(child_pid, 0)
                child_finished = True
                self.assertEqual(status, 0, message)
                self.assertEqual(message, "ok")
                with store.locked():
                    self.assertEqual(store.read(), {"schemaVersion": 1, "letters": []})
            finally:
                os.close(read_fd)
                if not child_finished:
                    os.kill(child_pid, signal.SIGKILL)
                    os.waitpid(child_pid, 0)


if __name__ == "__main__":
    unittest.main()
