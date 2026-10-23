"""Durable mailbox deadlines: no waits and no production credentials/data."""
from datetime import datetime
from pathlib import Path
import secrets
import sqlite3
import tempfile
import time
import unittest

from werkzeug.security import generate_password_hash

from server import AuthStore, create_app


class MailboxExpiryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = secrets.token_urlsafe(24)
        cls.password_hash = generate_password_hash(cls.password, method="scrypt:32768:8:1")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="lovedays-expiry-test-")
        self.clock = [time.time()]
        self.started = self.clock[0]
        self.config = {"TESTING": True, "DATA_DIR": self.temporary.name,
                       "PASSWORD_HASH": self.password_hash, "TIME_PROVIDER": lambda: self.clock[0]}
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/session").get_json()["csrfToken"]

    def tearDown(self):
        self.temporary.cleanup()

    def headers(self):
        return {"Origin": "http://localhost", "X-CSRF-Token": self.csrf}

    def login(self):
        response = self.client.post("/api/auth", json={"password": self.password}, headers=self.headers())
        self.assertEqual(response.status_code, 200, response.get_json())
        self.csrf = response.get_json()["csrfToken"]
        return response.get_json()

    def at(self, seconds):
        self.clock[0] = self.started + seconds

    @staticmethod
    def timestamp(value):
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()

    def test_reads_and_background_checks_never_renew_five_minute_idle(self):
        session = self.login()
        self.assertEqual(session["expiresIn"], 300)
        self.assertIsNone(session["closeExpiresAt"])
        deadline = session["idleExpiresAt"]
        for second in (60, 120, 250, 299):
            self.at(second)
            self.assertEqual(self.client.get("/api/letters").status_code, 200)
            current = self.client.get("/api/session").get_json()
            self.assertTrue(current["authenticated"])
            self.assertEqual(current["idleExpiresAt"], deadline)
        self.at(300)
        self.assertEqual(self.client.get("/api/letters").status_code, 401)
        self.assertEqual(self.client.get("/api/images/missing").status_code, 401)
        self.assertFalse(self.client.get("/api/session").get_json()["authenticated"])

    def test_only_explicit_csrf_protected_activity_renews_idle(self):
        self.login()
        self.at(299)
        self.assertEqual(self.client.post("/api/activity", json={}).status_code, 403)
        response = self.client.post("/api/activity", json={}, headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["expiresIn"], 300)
        self.at(598)
        self.assertEqual(self.client.get("/api/letters").status_code, 200)
        self.at(599)
        self.assertEqual(self.client.post("/api/activity", json={}, headers=self.headers()).status_code, 401)

    def test_close_reopen_and_repeated_closes_keep_earliest_deadline(self):
        self.login()
        self.at(100)
        first = self.client.post("/api/mailbox/close", json={}, headers=self.headers()).get_json()
        self.assertEqual(first["expiresIn"], 30)
        close_at = first["closeExpiresAt"]
        self.at(120)
        reopened = self.client.get("/api/session").get_json()
        self.assertTrue(reopened["authenticated"])
        self.assertEqual(reopened["closeExpiresAt"], close_at)
        self.at(125)
        active = self.client.post("/api/activity", json={}, headers=self.headers()).get_json()
        self.assertEqual(active["expiresIn"], 5)
        self.at(126)
        again = self.client.post("/api/mailbox/close", json={}, headers=self.headers()).get_json()
        self.assertEqual(again["closeExpiresAt"], close_at)
        self.at(130)
        self.assertEqual(self.client.get("/api/letters").status_code, 401)

    def test_idle_deadline_can_precede_close_grace(self):
        self.login()
        self.at(290)
        response = self.client.post("/api/mailbox/close", json={}, headers=self.headers())
        self.assertEqual(response.get_json()["expiresIn"], 10)
        self.at(300)
        self.assertEqual(self.client.get("/api/letters").status_code, 401)

    def test_two_tabs_and_restart_share_close_deadline(self):
        self.login()
        other = self.app.test_client()
        for name in ("lovedays_browser", "lovedays_session"):
            other.set_cookie(name, self.client.get_cookie(name).value)
        self.at(20)
        self.client.post("/api/mailbox/close", json={}, headers=self.headers())
        self.at(35)
        self.assertEqual(other.get("/api/session").get_json()["expiresIn"], 15)
        restarted = create_app(self.config).test_client()
        for name in ("lovedays_browser", "lovedays_session"):
            restarted.set_cookie(name, self.client.get_cookie(name).value)
        self.assertEqual(restarted.get("/api/session").get_json()["expiresIn"], 15)
        self.at(50)
        self.assertEqual(other.get("/api/letters").status_code, 401)
        self.assertEqual(restarted.get("/api/letters").status_code, 401)

    def test_manual_lock_revokes_access_immediately_in_all_tabs(self):
        self.login()
        other = self.app.test_client()
        for name in ("lovedays_browser", "lovedays_session"):
            other.set_cookie(name, self.client.get_cookie(name).value)
        self.assertEqual(self.client.post("/api/logout", json={}, headers=self.headers()).status_code, 200)
        self.assertEqual(other.get("/api/letters").status_code, 401)
        self.assertEqual(self.client.get("/api/letters").status_code, 401)

    def test_absolute_limit_survives_continuous_actual_activity(self):
        self.login()
        for second in range(250, 1751, 250):
            self.at(second)
            response = self.client.post("/api/activity", json={}, headers=self.headers())
            self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["expiresIn"], 50)
        self.at(1800)
        self.assertEqual(self.client.get("/api/letters").status_code, 401)

    def test_configured_limits_are_read_from_server_settings(self):
        self.app.extensions["site_settings_reader"] = lambda: {"mailboxIdleSeconds": 90, "mailboxCloseSeconds": 12}
        self.assertEqual(self.login()["expiresIn"], 90)
        self.at(10)
        result = self.client.post("/api/mailbox/close", json={}, headers=self.headers()).get_json()
        self.assertEqual(result["expiresIn"], 12)
        self.at(22)
        self.assertEqual(self.client.get("/api/letters").status_code, 401)

    def test_existing_session_schema_migrates_without_resetting_values(self):
        directory = Path(self.temporary.name) / "legacy"
        directory.mkdir()
        with sqlite3.connect(directory / "auth.sqlite3") as db:
            db.execute("CREATE TABLE sessions(id TEXT PRIMARY KEY,browser_id TEXT,created REAL,seen REAL,version TEXT)")
            db.execute("INSERT INTO sessions VALUES(?,?,?,?,?)", ("old-session", "old-browser", 100, 200, "v"))
        store = AuthStore(directory)
        with store.connection() as db:
            row = db.execute("SELECT * FROM sessions WHERE id='old-session'").fetchone()
            self.assertEqual(row["last_activity"], 200)
            self.assertIsNone(row["close_deadline"])
            self.assertEqual(row["created"], 100)
        AuthStore(directory)
        with store.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
