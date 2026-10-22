"""Exercise the PythonAnywhere WSGI deployment against isolated private storage."""
import json
import os
from pathlib import Path
import runpy
import secrets
import tempfile
import unittest
from unittest import mock

from werkzeug.security import generate_password_hash

from server import ROOT, create_app


class PythonAnywhereTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = secrets.token_urlsafe(24)
        cls.password_hash = generate_password_hash(cls.password, method="scrypt:32768:8:1")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="lovedays-pythonanywhere-test-")
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name) / "example-user"
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith("LOVEDAYS_") and key != "RENDER_EXTERNAL_URL"}
        self.environment = mock.patch.dict(os.environ, environment, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.home_patch = mock.patch("pathlib.Path.home", return_value=self.home)
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)

    def load_application(self):
        app = runpy.run_path(str(ROOT / "pythonanywhere_wsgi.py"))["application"]
        app.config["TESTING"] = True
        return app

    def log_in(self, app, origin):
        client = app.test_client()
        first = client.get("/api/session", base_url=origin)
        token = first.get_json()["csrfToken"]
        self.assertFalse(first.get_json()["authenticated"])
        self.assertEqual(client.get("/api/letters", base_url=origin).status_code, 401)
        response = client.post("/api/auth", base_url=origin,
                               json={"password": self.password},
                               headers={"Origin": origin, "X-CSRF-Token": token})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertTrue(response.get_json()["authenticated"])
        return client, response

    def test_default_storage_matches_cli_and_survives_wsgi_reload(self):
        app = self.load_application()
        origin = "https://example-user.pythonanywhere.com"
        # Password initialization uses the same create_app entry point as the CLI.
        cli_app = create_app()
        self.assertEqual(app.config["DATA_DIR"], cli_app.config["DATA_DIR"])
        directory = Path(app.config["DATA_DIR"])
        self.assertTrue(self.home in directory.parents)
        cli_app.extensions["auth_store"].set_password(self.password_hash)
        with cli_app.extensions["auth_store"].connection() as db:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "delete")
        client, login = self.log_in(app, origin)
        self.assertTrue(all("Secure" in value and "HttpOnly" in value
                            for value in login.headers.getlist("Set-Cookie")))
        token = login.get_json()["csrfToken"]
        payload = {"senderId": "tuan", "senderName": "Lê Anh Tuấn",
                   "recipientId": "thu", "recipientName": "Lê Phạm Anh Thư",
                   "type": "love-letter", "title": "Thư từ máy chủ miễn phí",
                   "content": "Một dòng tiếng Việt.\nMột lời thương."}
        created = client.post("/api/letters", base_url=origin, json=payload,
                              headers={"Origin": origin, "X-CSRF-Token": token})
        self.assertEqual(created.status_code, 201, created.get_json())
        saved = json.loads((directory / "letters.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["letters"][0]["content"], payload["content"])
        letter_id = saved["letters"][0]["id"]
        reloaded = self.load_application()
        other_device, other_login = self.log_in(reloaded, origin)
        self.assertTrue(other_login.get_json()["authenticated"])
        detail = other_device.get(f"/api/letters/{letter_id}", base_url=origin)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.get_json()["letter"]["content"], payload["content"])
        headers = {"Origin": origin, "X-CSRF-Token": other_login.get_json()["csrfToken"]}
        edited_payload = dict(payload, title="Một lá thư đã cập nhật")
        edited = other_device.put(f"/api/letters/{letter_id}", base_url=origin,
                                  json=edited_payload, headers=headers)
        self.assertEqual(edited.status_code, 200, edited.get_json())
        self.assertEqual(edited.get_json()["letter"]["id"], letter_id)
        listed = other_device.get("/api/letters", base_url=origin).get_json()["letters"]
        self.assertEqual(listed[0]["title"], edited_payload["title"])
        removed = other_device.delete(f"/api/letters/{letter_id}", base_url=origin,
                                      headers=headers)
        self.assertEqual(removed.status_code, 200, removed.get_json())
        self.assertEqual(other_device.get(f"/api/letters/{letter_id}", base_url=origin).status_code, 404)
        anonymous = reloaded.test_client()
        self.assertEqual(anonymous.get("/api/letters", base_url=origin).status_code, 401)
        self.assertEqual(anonymous.get("/letters.json", base_url=origin).status_code, 404)

    def test_explicit_eu_origin_is_accepted_and_other_origin_is_rejected(self):
        origin = "https://example-user.eu.pythonanywhere.com"
        os.environ["LOVEDAYS_PUBLIC_ORIGIN"] = origin
        os.environ["LOVEDAYS_DATA_DIR"] = str(Path(self.temporary.name) / "explicit-data")
        app = self.load_application()
        app.extensions["auth_store"].set_password(self.password_hash)
        client = app.test_client()
        token = client.get("/api/session", base_url=origin).get_json()["csrfToken"]
        rejected = client.post("/api/auth", base_url=origin, json={"password": self.password},
                               headers={"Origin": "https://example-user.pythonanywhere.com",
                                        "X-CSRF-Token": token})
        self.assertEqual(rejected.status_code, 403)
        self.log_in(app, origin)

    def test_invalid_journal_mode_is_rejected(self):
        os.environ["LOVEDAYS_SQLITE_JOURNAL_MODE"] = "OFF"
        with self.assertRaisesRegex(ValueError, "WAL or DELETE"):
            self.load_application()


if __name__ == "__main__":
    unittest.main()
