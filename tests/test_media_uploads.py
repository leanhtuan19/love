"""Durable uploads, original bytes, transaction ownership and range regression checks."""
from concurrent.futures import ThreadPoolExecutor
import errno
import io
import json
import os
from pathlib import Path
import secrets
import sqlite3
import struct
import tempfile
import time
import unittest
import uuid
from unittest import mock

from PIL import Image
from werkzeug.security import generate_password_hash

from server import create_app
from media_uploads import CHUNK_BYTES


class MediaUploadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = secrets.token_urlsafe(24)
        cls.hashed = generate_password_hash(cls.password, method="scrypt:32768:8:1")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="lovedays-media-test-")
        self.clock = [time.time()]
        self.config = {"TESTING": True, "DATA_DIR": self.temporary.name,
                       "PASSWORD_HASH": self.hashed, "TIME_PROVIDER": lambda: self.clock[0]}
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.login()

    def tearDown(self):
        self.temporary.cleanup()

    def headers(self, **extra):
        return {"Origin": "http://localhost", "X-CSRF-Token": self.csrf, **extra}

    def login(self):
        self.csrf = self.client.get("/api/session").get_json()["csrfToken"]
        response = self.client.post("/api/auth", json={"password": self.password}, headers=self.headers())
        self.assertEqual(response.status_code, 200, response.get_json())
        self.csrf = response.get_json()["csrfToken"]

    @staticmethod
    def image():
        output = io.BytesIO()
        image = Image.new("RGB", (20, 15), "pink")
        exif = Image.Exif()
        exif[270] = "original-camera-metadata"
        image.save(output, "JPEG", exif=exif)
        return output.getvalue()

    @staticmethod
    def webm():
        # A real VP8 keyframe comes from Pillow's lossily encoded WebP chunk;
        # VP8 elementary frames are shared by WebP and WebM. No ffmpeg or
        # downloaded third-party asset is needed for this small video fixture.
        output = io.BytesIO()
        Image.new("RGB", (32, 32), "pink").save(output, "WEBP", quality=75)
        riff = output.getvalue()
        start = riff.index(b"VP8 ") + 4
        frame_size = int.from_bytes(riff[start:start + 4], "little")
        frame = riff[start + 4:start + 4 + frame_size]
        def element(kind, payload):
            identifier = kind.to_bytes((kind.bit_length() + 7) // 8, "big")
            width = next(width for width in range(1, 9) if len(payload) < (1 << (7 * width)) - 1)
            size = ((1 << (7 * width)) | len(payload)).to_bytes(width, "big")
            return identifier + size + payload
        def number(kind, value):
            return element(kind, value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big"))
        header = element(0x1A45DFA3, number(0x4286, 1) + number(0x42F7, 1) + number(0x42F2, 4) + number(0x42F3, 8)
                         + element(0x4282, b"webm") + number(0x4287, 4) + number(0x4285, 2))
        info = element(0x1549A966, number(0x2AD7B1, 1000000) + element(0x4489, struct.pack(">d", 200.0)))
        track = element(0x1654AE6B, element(0xAE, number(0xD7, 1) + number(0x73C5, 1) + number(0x83, 1)
                        + element(0x86, b"V_VP8") + element(0xE0, number(0xB0, 32) + number(0xBA, 32))))
        cluster = element(0x1F43B675, number(0xE7, 0) + element(0xA3, b"\x81\0\0\x80" + frame)
                          + element(0xA3, b"\x81\0\x64\x80" + frame))
        return header + element(0x18538067, info + track + cluster)

    def start(self, data, name="photo.jpg", mime="image/jpeg", scope="letters"):
        response = self.client.post("/api/uploads", json={"scope": scope, "name": name,
                                    "size": len(data), "mimeType": mime, "lastModified": 10}, headers=self.headers())
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()["id"]

    def chunk(self, upload_id, data, offset=0):
        return self.client.put("/api/uploads/" + upload_id, data=data,
                               headers=self.headers(**{"Upload-Offset": str(offset)}), content_type="application/octet-stream")

    def finish(self, upload_id):
        return self.client.post("/api/uploads/" + upload_id + "/finish", json={}, headers=self.headers())

    def uploaded(self, data=None, **options):
        data = data or self.image()
        upload_id = self.start(data, **options)
        for offset in range(0, len(data), CHUNK_BYTES):
            response = self.chunk(upload_id, data[offset:offset + CHUNK_BYTES], offset)
            self.assertEqual(response.status_code, 200, response.get_json())
        response = self.finish(upload_id)
        self.assertEqual(response.status_code, 200, response.get_json())
        return upload_id

    def letter(self, ids, **changes):
        return self.client.post("/api/letters", json={"senderId": "tuan", "recipientId": "thu",
                                "type": "love-letter", "title": "Thư gốc", "content": "Thương em\nNhiều lắm",
                                "uploadIds": ids, **changes}, headers=self.headers())

    def test_originals_private_until_claimed_and_byte_range_after_claim(self):
        original = self.image()
        upload_id = self.uploaded(original)
        self.assertEqual(self.client.get("/api/images/" + upload_id).status_code, 404)
        saved = self.letter([upload_id])
        self.assertEqual(saved.status_code, 201, saved.get_json())
        metadata = saved.get_json()["letter"]["images"][0]
        self.assertEqual(metadata["kind"], "image")
        self.assertNotIn("storageKey", metadata)
        with self.client.get(metadata["url"]) as response:
            self.assertEqual(response.data, original)
        with self.client.get(metadata["url"], headers={"Range": "bytes=2-11"}) as response:
            self.assertEqual(response.status_code, 206)
            self.assertEqual(response.data, original[2:12])
        self.assertEqual(self.app.test_client().get(metadata["url"]).status_code, 401)
        self.assertEqual(self.client.delete("/api/uploads/" + upload_id, headers=self.headers()).status_code, 409)

    def test_real_vp8_video_attaches_alongside_image_and_keeps_original(self):
        video = self.webm()
        image_id = self.uploaded()
        video_id = self.uploaded(video, name="moment.webm", mime="video/webm")
        response = self.letter([image_id, video_id])
        self.assertEqual(response.status_code, 201, response.get_json())
        media = response.get_json()["letter"]["images"]
        self.assertEqual([item["kind"] for item in media], ["image", "video"])
        with self.client.get(media[1]["url"], headers={"Range": "bytes=0-19"}) as fetched:
            self.assertEqual(fetched.status_code, 206)
            self.assertEqual(fetched.mimetype, "video/webm")
            self.assertEqual(fetched.data, video[:20])

    def test_resume_offset_survives_app_restart_and_partial_network_request(self):
        data = self.image()
        upload_id = self.start(data)
        self.assertEqual(self.chunk(upload_id, data[:31]).get_json()["offset"], 31)
        self.assertEqual(self.chunk(upload_id, data[:31]).status_code, 409)
        self.assertEqual(self.finish(upload_id).status_code, 409)
        browser = self.client.get_cookie("lovedays_browser").value
        session = self.client.get_cookie("lovedays_session").value
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.client.set_cookie("lovedays_browser", browser)
        self.client.set_cookie("lovedays_session", session)
        status = self.client.get("/api/uploads/" + upload_id).get_json()
        self.assertEqual(status["offset"], 31)
        response = self.client.open("/api/uploads/" + upload_id, method="PUT", input_stream=io.BytesIO(data[31:40]),
                                   content_type="application/octet-stream", headers=self.headers(**{"Upload-Offset": "31"}),
                                   environ_overrides={"CONTENT_LENGTH": "50"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get("/api/uploads/" + upload_id).get_json()["offset"], 31)
        self.assertEqual(self.chunk(upload_id, data[31:], 31).status_code, 200)
        self.assertEqual(self.finish(upload_id).status_code, 200)

    def test_all_requests_check_auth_csrf_origin_and_browser_ownership(self):
        upload_id = self.start(self.image())
        outsider = self.app.test_client()
        self.assertEqual(outsider.get("/api/uploads/" + upload_id).status_code, 404)
        self.assertEqual(self.client.put("/api/uploads/" + upload_id, data=b"x", content_type="application/octet-stream").status_code, 403)
        self.assertEqual(self.client.post("/api/uploads/" + upload_id + "/finish", headers={"Origin": "https://else.invalid", "X-CSRF-Token": self.csrf}).status_code, 403)
        self.clock[0] += 301
        self.assertEqual(self.chunk(upload_id, b"x").status_code, 401)
        self.assertEqual(self.client.get("/api/uploads/" + upload_id).status_code, 401)
        self.assertEqual(self.finish(upload_id).status_code, 401)

    def test_invalid_media_and_filename_do_not_publish_and_can_be_discarded(self):
        for name, mime, data in [("fake.mp4", "video/mp4", b"not a video"),
                                 ("fake.webm", "video/webm", b"\x1aE\xdf\xa3bad"),
                                 ("fake.png", "image/png", self.image())]:
            upload_id = self.start(data, name, mime)
            self.assertEqual(self.chunk(upload_id, data).status_code, 200)
            self.assertEqual(self.finish(upload_id).status_code, 400)
            self.assertEqual(self.client.get("/api/images/" + upload_id).status_code, 404)
            self.assertEqual(self.client.delete("/api/uploads/" + upload_id, headers=self.headers()).status_code, 200)
        self.assertEqual(list(self.app.extensions["media_uploads"].directory.iterdir()), [])
        for field, value in [("name", []), ("scope", {}), ("mimeType", {})]:
            body = {"name": "photo.jpg", "size": 10, "scope": "letters", "mimeType": "image/jpeg", field: value}
            self.assertEqual(self.client.post("/api/uploads", json=body, headers=self.headers()).status_code, 400)

    def test_no_attachment_count_or_five_megabyte_business_limit(self):
        data = self.image() + b"\0" * (6 * 1024 * 1024)
        first = self.uploaded(data)
        ids = [first] + [self.uploaded() for _ in range(6)]
        response = self.letter(ids)
        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertEqual(len(response.get_json()["letter"]["images"]), 7)
        with self.client.get(response.get_json()["letter"]["images"][0]["url"]) as media:
            self.assertEqual(media.data, data)

    def test_same_offset_concurrent_requests_commit_exactly_one_chunk(self):
        data = self.image()
        upload_id = self.start(data)
        cookies = [(name, self.client.get_cookie(name).value) for name in ("lovedays_browser", "lovedays_session")]
        def send():
            client = self.app.test_client()
            for name, value in cookies:
                client.set_cookie(name, value)
            return client.put("/api/uploads/" + upload_id, data=data[:25], content_type="application/octet-stream",
                              headers=self.headers(**{"Upload-Offset": "0"})).status_code
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(lambda _: send(), range(2)))
        self.assertEqual(sorted(statuses), [200, 409])
        self.assertEqual(self.client.get("/api/uploads/" + upload_id).get_json()["offset"], 25)
        self.assertEqual((self.app.extensions["media_uploads"].incoming / (upload_id + ".part")).read_bytes(), data[:25])

    def test_chunk_transport_bound_is_not_total_file_bound(self):
        data = self.image()
        upload_id = self.start(data)
        self.assertEqual(self.chunk(upload_id, b"x" * (CHUNK_BYTES + 1)).status_code, 413)
        self.assertEqual(self.chunk(upload_id, data).status_code, 200)
        self.assertEqual(self.finish(upload_id).status_code, 200)

    def test_disk_full_keeps_completed_upload_and_current_offset(self):
        completed = self.uploaded()
        data = self.image()
        upload_id = self.start(data)
        with mock.patch("media_uploads.os.fsync", side_effect=OSError(errno.ENOSPC, "disk full")):
            response = self.chunk(upload_id, data)
        self.assertEqual(response.status_code, 507, response.get_json())
        self.assertEqual(response.get_json()["error"], "storage_full")
        self.assertEqual(self.client.get("/api/uploads/" + upload_id).get_json()["offset"], 0)
        self.assertEqual(self.client.get("/api/uploads/" + completed).get_json()["state"], "complete")
        self.assertEqual(self.chunk(upload_id, data).status_code, 200)
        self.assertEqual(self.finish(upload_id).status_code, 200)

    def test_sqlite_full_reports_storage_error_without_losing_completed_upload(self):
        upload_id = self.uploaded()
        with mock.patch.object(self.app.extensions["letter_store"], "write", side_effect=sqlite3.OperationalError("database or disk is full")):
            response = self.letter([upload_id])
        self.assertEqual(response.status_code, 507, response.get_json())
        self.assertEqual(response.get_json()["error"], "storage_full")
        self.assertEqual(self.client.get("/api/uploads/" + upload_id).get_json()["state"], "complete")

    def test_save_failure_preserves_completed_queue_and_prevents_reuse(self):
        upload_id = self.uploaded()
        with mock.patch.object(self.app.extensions["letter_store"], "write", side_effect=OSError("simulated")), self.assertLogs(self.app.logger, level="ERROR"):
            response = self.letter([upload_id])
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.client.get("/api/uploads/" + upload_id).get_json()["state"], "complete")
        self.assertEqual(self.letter([upload_id]).status_code, 201)
        self.assertEqual(self.letter([upload_id]).status_code, 409)

    def test_receiver_pair_checked_on_both_sides(self):
        self.assertEqual(self.letter([], recipientId="tuan").status_code, 400)
        self.assertEqual(self.letter([], senderId="thu", recipientId="tuan").status_code, 201)

    def test_json_reference_blocks_discard_and_reuse_after_sql_claim_crash(self):
        upload_id = self.uploaded()
        response = self.letter([upload_id])
        self.assertEqual(response.status_code, 201)
        url = response.get_json()["letter"]["images"][0]["url"]
        # Simulate SIGKILL between JSON atomic replace and SQL claim commit.
        with self.app.extensions["auth_store"].transaction() as db:
            db.execute("UPDATE media_uploads SET state='complete',target_id=NULL WHERE id=?", (upload_id,))
        self.assertEqual(self.client.delete("/api/uploads/" + upload_id, headers=self.headers()).status_code, 409)
        self.assertEqual(self.letter([upload_id]).status_code, 409)
        with self.client.get(url) as media:
            self.assertEqual(media.status_code, 200)
            self.assertEqual(media.data, self.image())

    def test_finish_recovers_rename_before_sql_commit_process_crash(self):
        data = self.image()
        upload_id = self.start(data)
        self.assertEqual(self.chunk(upload_id, data).status_code, 200)
        store = self.app.extensions["media_uploads"]
        source = store.incoming / (upload_id + ".part")
        destination = store.directory / (upload_id.replace("-", "") + ".jpg")
        os.replace(source, destination)
        response = self.finish(upload_id)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.client.get("/api/uploads/" + upload_id).get_json()["state"], "complete")
        self.assertEqual(destination.read_bytes(), data)

    def test_many_unknown_size_webm_clusters_are_siblings_not_nested(self):
        original = self.webm()
        segment_id = b"\x18\x53\x80\x67"
        cluster_id = b"\x1f\x43\xb6\x75"
        segment = original.index(segment_id)
        cluster = original.index(cluster_id)
        # This fixture uses a two-byte Segment size and one-byte Cluster size.
        self.assertEqual(original[segment + 4] & 0xC0, 0x40)
        self.assertTrue(original[cluster + 4] & 0x80)
        unknown = b"\x01" + b"\xff" * 7
        block = cluster_id + unknown + original[cluster + 5:]
        streaming = original[:segment + 4] + unknown + original[segment + 6:cluster] + block * 24
        upload_id = self.uploaded(streaming, name="stream.webm", mime="video/webm")
        self.assertEqual(self.letter([upload_id]).status_code, 201)

    def test_explicit_cleanup_preserves_linked_crash_references_and_recent_queue(self):
        linked = self.uploaded()
        self.assertEqual(self.letter([linked]).status_code, 201)
        abandoned = self.uploaded()
        partial = self.start(self.image())
        recent = self.uploaded()
        store = self.app.extensions["media_uploads"]
        orphan = store.incoming / (str(uuid.uuid4()) + ".part")
        orphan.write_bytes(b"interrupted-before-SQL-insert")
        os.utime(orphan, (self.clock[0] - 8 * 86400, self.clock[0] - 8 * 86400))
        with self.app.extensions["auth_store"].transaction() as db:
            db.execute("UPDATE media_uploads SET updated=? WHERE id IN (?,?,?)", (self.clock[0] - 8 * 86400, linked, abandoned, partial))
            # The JSON reference also protects a claim interrupted by a crash.
            db.execute("UPDATE media_uploads SET state='complete',target_id=NULL WHERE id=?", (linked,))
        preview = store.cleanup(7, dry_run=True)
        self.assertEqual(preview, {"removed": 3, "protected": 1, "dryRun": True})
        self.assertEqual(self.client.get("/api/uploads/" + abandoned).status_code, 200)
        result = store.cleanup(7)
        self.assertEqual(result, {"removed": 3, "protected": 1, "dryRun": False})
        self.assertFalse(orphan.exists())
        self.assertEqual(self.client.get("/api/uploads/" + abandoned).status_code, 404)
        self.assertEqual(self.client.get("/api/uploads/" + partial).status_code, 404)
        self.assertEqual(self.client.get("/api/uploads/" + recent).status_code, 200)
        self.assertEqual(self.client.get("/api/uploads/" + linked).status_code, 200)


if __name__ == "__main__":
    unittest.main()
