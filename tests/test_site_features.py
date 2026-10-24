"""Integration/security checks use only generated, disposable credentials/data."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import secrets
import tempfile
import time
import unittest
from unittest import mock

from PIL import Image
from werkzeug.security import check_password_hash, generate_password_hash

from server import create_app
from site_features import setup_admins


class SiteFeaturesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mail_password = secrets.token_urlsafe(24)
        cls.mail_hash = generate_password_hash(cls.mail_password, method="scrypt:32768:8:1")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="lovedays-features-")
        self.addCleanup(self.temporary.cleanup)
        self.clock = [time.time()]
        self.config = {"TESTING": True, "DATA_DIR": self.temporary.name, "PASSWORD_HASH": None,
                       "SQLITE_JOURNAL_MODE": "DELETE", "TIME_PROVIDER": lambda: self.clock[0]}
        self.app = create_app(self.config)
        self.auth = self.app.extensions["auth_store"]
        self.auth.set_password(self.mail_hash)
        self.store = self.app.extensions["site_features"]
        self.username1, self.username2 = ("admin-" + secrets.token_hex(6) for _ in range(2))
        self.password1, self.password2, self.journal_password = (secrets.token_urlsafe(24) for _ in range(3))
        self.setup_environment = {"LOVEDAYS_ADMIN_1_USERNAME": self.username1, "LOVEDAYS_ADMIN_1_PASSWORD": self.password1,
                                  "LOVEDAYS_ADMIN_2_USERNAME": self.username2, "LOVEDAYS_ADMIN_2_PASSWORD": self.password2}
        with mock.patch.dict(os.environ, self.setup_environment):
            self.assertTrue(setup_admins(self.app))
        self.client = self.app.test_client()

    def headers(self, client=None):
        client = client or self.client
        csrf = client.get("/api/session").get_json()["csrfToken"]
        return {"Origin": "http://localhost", "X-CSRF-Token": csrf}

    def login(self, client=None, username=None, password=None):
        client = client or self.client
        response = client.post("/api/admin/login", json={"username": username or self.username1, "password": password or self.password1}, headers=self.headers(client))
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()

    def configure_journal(self):
        self.login()
        response = self.client.put("/api/admin/settings/security", json={"newJournalPassword": self.journal_password, "confirmJournalPassword": self.journal_password}, headers=self.headers())
        self.assertEqual(response.status_code, 200, response.get_json())

    def payload(self, **changes):
        return {"authorName": "Người thương", "title": "Một chiều ở Hà Tĩnh", "content": "Thương nhiều.\nMột kỷ niệm nhỏ.",
                "location": {"label": "Hà Tĩnh", "latitude": 18.355, "longitude": 105.888}, **changes}

    def create(self, payload=None, images=None, client=None):
        client = client or self.client
        if images is None:
            return client.post("/api/journal", json=payload or self.payload(), headers=self.headers(client))
        response = client.post("/api/journal", data={"payload": json.dumps(payload or self.payload()), "images": images}, headers=self.headers(client), content_type="multipart/form-data")
        self.addCleanup(response.close)
        self.addCleanup(response.request.environ["wsgi.input"].close)
        return response

    def image(self):
        stream = io.BytesIO()
        Image.new("RGB", (24, 18), "pink").save(stream, "PNG")
        return stream.getvalue()

    def complete_upload(self, client=None):
        client = client or self.client
        content = self.image()
        response = client.post("/api/uploads", json={"scope": "journal", "name": "kỷ-niệm.png", "size": len(content), "mimeType": "image/png"}, headers=self.headers(client))
        self.assertEqual(response.status_code, 201, response.get_json())
        upload_id = response.get_json()["id"]
        endpoint = "/api/uploads/" + upload_id
        response = client.put(endpoint, data=content, content_type="application/octet-stream", headers={**self.headers(client), "Upload-Offset": "0"})
        self.assertEqual(response.status_code, 200, response.get_json())
        response = client.post(endpoint + "/finish", json={}, headers=self.headers(client))
        self.assertEqual(response.status_code, 200, response.get_json())
        return upload_id

    def test_encrypted_usernames_hashes_and_public_endpoints_never_leak_credentials(self):
        with self.auth.connection() as db:
            rows = db.execute("SELECT * FROM admin_accounts").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual({self.store.username(row) for row in rows}, {self.username1, self.username2})
        for row in rows:
            self.assertNotIn(self.username1, row["username_cipher"])
            self.assertNotIn(self.username2, row["username_cipher"])
            self.assertTrue(row["password_hash"].startswith("scrypt:"))
        database = self.auth.path.read_bytes()
        for secret in (self.username1, self.username2, self.password1, self.password2):
            self.assertNotIn(secret.encode(), database)
        for endpoint in ("/api/site", "/api/admin/session", "/api/journal"):
            response = self.client.get(endpoint)
            self.assertEqual(response.status_code, 200)
            for secret in (self.username1, self.username2, self.password1, self.password2, rows[0]["password_hash"]):
                self.assertNotIn(secret, response.get_data(as_text=True))
        for endpoint in ("/admin-encryption.key", "/admin-lookup.key", "/auth.sqlite3", "/site_features.py"):
            self.assertEqual(self.client.get(endpoint).status_code, 404)

    def test_admin_and_mailbox_permissions_are_independent_and_csrf_is_enforced(self):
        self.assertEqual(self.client.get("/api/admin/settings").status_code, 401)
        response = self.client.post("/api/auth", json={"password": self.mail_password}, headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/admin/settings").status_code, 401)
        self.assertEqual(self.client.post("/api/admin/login", json={"username": self.username1, "password": self.password1}).status_code, 403)
        self.assertEqual(self.client.post("/api/admin/login", json={"username": self.username1, "password": self.password1}, headers={"Origin": "https://wrong.invalid", "X-CSRF-Token": self.headers()["X-CSRF-Token"]}).status_code, 403)
        self.login()
        self.assertEqual(self.client.put("/api/admin/settings/content", json={"heading": "Tên mới"}).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/settings").status_code, 200)
        other = self.app.test_client()
        self.login(other)
        self.assertEqual(other.get("/api/letters").status_code, 401)

    def test_account_edit_requires_current_actor_password_revokes_sessions_and_setup_does_not_reset(self):
        account = self.login()["account"]
        other_tab = self.app.test_client()
        self.login(other_tab)
        new_username, new_password = "changed-" + secrets.token_hex(6), secrets.token_urlsafe(24)
        body = {"username": new_username, "newPassword": new_password, "confirmPassword": new_password,
                "currentPassword": secrets.token_urlsafe(20)}
        endpoint = "/api/admin/accounts/" + account["id"]
        self.assertEqual(self.client.put(endpoint, json=body, headers=self.headers()).status_code, 401)
        body["currentPassword"] = self.password1
        changed = self.client.put(endpoint, json=body, headers=self.headers())
        self.assertEqual(changed.status_code, 200)
        self.assertTrue(changed.get_json()["reauthenticate"])
        self.assertFalse(self.client.get("/api/admin/session").get_json()["authenticated"])
        self.assertFalse(other_tab.get("/api/admin/session").get_json()["authenticated"])
        with mock.patch.dict(os.environ, self.setup_environment):
            self.assertFalse(setup_admins(self.app))
        old = self.client.post("/api/admin/login", json={"username": self.username1, "password": self.password1}, headers=self.headers())
        self.assertEqual(old.status_code, 401)
        self.login(username=new_username, password=new_password)
        accounts = self.client.get("/api/admin/accounts").get_json()["accounts"]
        self.assertIn(new_username, [row["username"] for row in accounts])
        duplicate = self.client.put(endpoint, json={"currentPassword": new_password, "username": self.username2}, headers=self.headers())
        self.assertEqual(duplicate.status_code, 409)

    def test_settings_merge_validation_and_password_changes_are_durable(self):
        self.configure_journal()
        original = self.client.get("/api/site").get_json()
        changed = self.client.put("/api/admin/settings/profiles", json={"tuan": {"displayName": "Tên hiển thị mới"}}, headers=self.headers())
        self.assertEqual(changed.status_code, 200)
        self.client.put("/api/admin/settings/content", json={"heading": "CHÚNG MÌNH"}, headers=self.headers())
        public = self.client.get("/api/site").get_json()
        self.assertEqual(public["profiles"]["tuan"]["displayName"], "Tên hiển thị mới")
        self.assertEqual(public["profiles"]["thu"], original["profiles"]["thu"])
        self.assertEqual(public["content"]["heading"], "CHÚNG MÌNH")
        for group, body in (("profiles", {"tuan": {"birthday": "2026-02-30"}}), ("content", {"musicSrc": "javascript:bad"}),
                            ("content", {"backgroundImage": "main/img/../secret.png"}), ("security", {"mailboxIdleSeconds": 0}),
                            ("security", {"newJournalPassword": "short", "confirmJournalPassword": "short"})):
            self.assertEqual(self.client.put("/api/admin/settings/" + group, json=body, headers=self.headers()).status_code, 400)
        updated_app = create_app(self.config)
        self.assertEqual(updated_app.test_client().get("/api/site").get_json()["content"]["heading"], "CHÚNG MÌNH")
        login = self.client.post("/api/auth", json={"password": self.mail_password}, headers=self.headers())
        self.assertEqual(login.status_code, 200)
        fresh = secrets.token_urlsafe(24)
        result = self.client.put("/api/admin/settings/security", json={"newMailboxPassword": fresh, "confirmMailboxPassword": fresh,
                                 "mailboxIdleSeconds": 600, "mailboxCloseSeconds": 45}, headers=self.headers())
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.client.get("/api/letters").status_code, 401)
        self.assertTrue(self.client.get("/api/admin/session").get_json()["authenticated"])
        self.assertEqual(self.app.extensions["site_settings_reader"](), {"mailboxIdleSeconds": 600, "mailboxCloseSeconds": 45})

    def test_admin_login_rate_limit_survives_browser_reset_and_application_restart(self):
        for number in range(6):
            response = self.client.post("/api/admin/login", json={"username": self.username1, "password": secrets.token_urlsafe(20)}, headers=self.headers())
            self.assertEqual(response.status_code, 429 if number == 5 else 401)
        other = create_app(self.config).test_client()
        denied = other.post("/api/admin/login", json={"username": self.username1, "password": self.password1}, headers=self.headers(other))
        self.assertEqual(denied.status_code, 429)
        self.clock[0] += 901
        self.login(other)

    def test_missing_existing_identity_key_stops_initialization_without_overwriting_data(self):
        key = self.store.directory / "admin-encryption.key"
        key.unlink()
        with self.assertRaisesRegex(RuntimeError, "key files are missing"):
            create_app(self.config)
        self.assertFalse(key.exists())
        with self.auth.connection() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM admin_accounts").fetchone()[0], 2)

    def test_public_read_but_posting_requires_real_session_and_server_sets_identity(self):
        self.assertEqual(self.create().status_code, 401)
        self.assertEqual(self.client.get("/api/journal").get_json()["posts"], [])
        response = self.client.post("/api/auth", json={"password": self.mail_password}, headers=self.headers())
        self.assertEqual(response.status_code, 200)
        saved = self.create(self.payload(id="forged", createdAt="forged"))
        self.assertEqual(saved.status_code, 201)
        post = saved.get_json()["post"]
        self.assertNotEqual(post["id"], "forged")
        self.assertTrue(post["createdAt"].endswith("Z"))
        self.assertEqual(post["content"], self.payload()["content"])
        public = self.app.test_client()
        self.assertEqual(public.get("/api/journal/" + post["id"]).get_json()["post"]["id"], post["id"])
        self.assertFalse(public.get("/api/journal").get_json()["canPost"])

    def test_fresh_journal_password_always_required_and_edit_delete_preserve_private_history(self):
        self.configure_journal()
        post = self.create().get_json()["post"]
        endpoint = "/api/journal/" + post["id"]
        original = dict(post)
        for password in (None, secrets.token_urlsafe(20)):
            edit = self.client.put(endpoint, json=self.payload(password=password, title="Không được lưu"), headers=self.headers())
            self.assertEqual(edit.status_code, 401)
            self.assertEqual(self.client.delete(endpoint, json={"password": password}, headers=self.headers()).status_code, 401)
            self.assertEqual(self.client.get(endpoint).get_json()["post"], original)
        changed = self.client.put(endpoint, json=self.payload(password=self.journal_password, title="Đã chỉnh sửa", expectedUpdatedAt=post["updatedAt"]), headers=self.headers())
        self.assertEqual(changed.status_code, 200)
        self.assertGreater(changed.get_json()["post"]["updatedAt"], post["updatedAt"])
        stale = self.client.put(endpoint, json=self.payload(password=self.journal_password, expectedUpdatedAt=post["updatedAt"]), headers=self.headers())
        self.assertEqual(stale.status_code, 409)
        deleted = self.client.delete(endpoint, json={"password": self.journal_password}, headers=self.headers())
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get(endpoint).status_code, 404)
        self.assertEqual(self.client.get("/api/journal").get_json()["total"], 0)
        history = self.client.get("/api/journal/history").get_json()["entries"]
        self.assertEqual([item["action"] for item in history], ["delete", "edit"])
        self.assertEqual(history[1]["before"]["title"], original["title"])
        self.assertEqual(history[1]["after"]["title"], "Đã chỉnh sửa")
        self.assertEqual(history[0]["postId"], post["id"])
        self.assertTrue(history[0]["after"]["deletedAt"])
        self.assertEqual(history[0]["actor"]["type"], "admin")
        self.assertNotIn(self.journal_password, json.dumps(history))
        outsider = self.app.test_client()
        self.assertEqual(outsider.get("/api/journal/history").status_code, 401)
        grant = outsider.post("/api/journal/history/unlock", json={"password": self.journal_password}, headers=self.headers(outsider))
        self.assertEqual(grant.status_code, 200)
        self.assertEqual(outsider.get("/api/journal/history").get_json()["total"], 2)
        self.clock[0] += 301
        self.assertEqual(outsider.get("/api/journal/history").status_code, 401)

    def test_unset_journal_password_denies_even_admin_edit_delete(self):
        self.login()
        post = self.create().get_json()["post"]
        endpoint = "/api/journal/" + post["id"]
        self.assertEqual(self.client.put(endpoint, json=self.payload(password=secrets.token_urlsafe(20)), headers=self.headers()).status_code, 409)
        self.assertEqual(self.client.delete(endpoint, json={"password": secrets.token_urlsafe(20)}, headers=self.headers()).status_code, 409)
        self.assertEqual(self.client.get(endpoint).status_code, 200)

    def test_search_real_vietnam_dates_accents_fields_and_pagination(self):
        self.login()
        self.clock[0] = datetime(2026, 10, 22, 18, 0, tzinfo=timezone.utc).timestamp()
        first = self.create(self.payload(title="Cà phê", authorName="Anh Thư", content="Bình yên", location={"label": "Hà Tĩnh"})).get_json()["post"]
        self.clock[0] += 86400
        self.login()
        second = self.create(self.payload(title="Ngày mới")).get_json()["post"]
        for query in ("CA PHE", "anh thu", "binh yen", "ha tinh", first["id"], "23/10/2026", "2026-10-23"):
            response = self.client.get("/api/journal", query_string={"q": query})
            self.assertEqual(response.status_code, 200)
            self.assertIn(first["id"], [post["id"] for post in response.get_json()["posts"]], query)
        filtered = self.client.get("/api/journal?from=2026-10-23&to=2026-10-23").get_json()
        self.assertEqual([item["id"] for item in filtered["posts"]], [first["id"]])
        page1 = self.client.get("/api/journal?pageSize=1").get_json()
        page2 = self.client.get("/api/journal?pageSize=1&page=2").get_json()
        self.assertTrue(page1["hasMore"])
        self.assertEqual(page1["posts"][0]["id"], second["id"])
        self.assertEqual(page2["posts"][0]["id"], first["id"])
        for parameters in ("from=2026-02-30", "from=2026-10-24&to=2026-10-23", "page=0", "pageSize=31"):
            self.assertEqual(self.client.get("/api/journal?" + parameters).status_code, 400)

    def test_upload_validation_removed_images_private_and_password_rotation_revokes_grants(self):
        self.configure_journal()
        response = self.create(images=[(io.BytesIO(self.image()), "image.png", "image/png")])
        self.assertEqual(response.status_code, 201, response.get_json())
        post = response.get_json()["post"]
        image = post["images"][0]
        self.assertNotIn("storageKey", image)
        outsider = self.app.test_client()
        with outsider.get(image["url"]) as public_image:
            self.assertEqual(public_image.status_code, 200)
            Image.open(io.BytesIO(public_image.data)).verify()
            self.assertEqual(public_image.data, self.image(), "Stored attachments retain original bytes")
        edit = self.client.put("/api/journal/" + post["id"], json=self.payload(password=self.journal_password, keepImageIds=[]), headers=self.headers())
        self.assertEqual(edit.status_code, 200)
        self.assertEqual(outsider.get(image["url"]).status_code, 401)
        grant = outsider.post("/api/journal/history/unlock", json={"password": self.journal_password}, headers=self.headers(outsider))
        self.assertEqual(grant.status_code, 200)
        with outsider.get(image["url"]) as historic_image:
            self.assertEqual(historic_image.status_code, 200)
        fresh = secrets.token_urlsafe(24)
        self.assertEqual(self.client.put("/api/admin/settings/security", json={"newJournalPassword": fresh, "confirmJournalPassword": fresh}, headers=self.headers()).status_code, 200)
        self.assertEqual(outsider.get(image["url"]).status_code, 401)
        self.assertEqual(outsider.get("/api/journal/history").status_code, 401)
        for uploads, expected in (([(io.BytesIO(b"<script>fake</script>"), "fake.png", "image/png")], 400),
                                  ([(io.BytesIO(self.image()), "fake.jpg", "image/jpeg")], 400)):
            self.assertEqual(self.create(images=uploads).status_code, expected)
        self.assertEqual(len(list(self.store.images.iterdir())), 1)
        many = self.create(images=[(io.BytesIO(self.image()), "i.png", "image/png") for _ in range(7)])
        self.assertEqual(many.status_code, 201, many.get_json())
        self.assertEqual(len(many.get_json()["post"]["images"]), 7)

    def test_failed_history_transaction_keeps_post_and_does_not_orphan_new_uploads(self):
        self.configure_journal()
        post = self.create().get_json()["post"]
        # A database trigger rejects the history insert after the post/files changed.
        with self.auth.connection() as db:
            db.execute("CREATE TRIGGER reject_history BEFORE INSERT ON journal_history BEGIN SELECT RAISE(ABORT,'simulated transaction failure'); END")
        with self.assertLogs(self.app.logger, level="ERROR"):
            result = self.client.put("/api/journal/" + post["id"], data={"payload": json.dumps(self.payload(password=self.journal_password, title="Không lưu")),
                                    "images": [(io.BytesIO(self.image()), "sample.png", "image/png")]}, headers=self.headers(), content_type="multipart/form-data")
        self.addCleanup(result.close)
        self.addCleanup(result.request.environ["wsgi.input"].close)
        self.assertEqual(result.status_code, 500)
        self.assertEqual(self.client.get("/api/journal/" + post["id"]).get_json()["post"], post)
        self.assertEqual(list(self.store.images.iterdir()), [])
        self.assertEqual(self.client.get("/api/journal/history").get_json()["total"], 0)

    def test_location_validation_optional_manual_rich_metadata_and_no_business_quota(self):
        self.login()
        for location in ({"label": "Tại nhà"}, {"label": ""}, {"label": "Vị trí", "latitude": 0, "longitude": 0}):
            self.assertEqual(self.create(self.payload(location=location)).status_code, 201)
        for location in ({"latitude": 18}, {"label": "", "latitude": 95, "longitude": 105}, {"label": "", "latitude": True, "longitude": 105},
                         {"label": "", "latitude": 0, "longitude": 0, "accuracy": -1}):
            self.assertEqual(self.create(self.payload(location=location)).status_code, 400)
        location = {"label": "Tên đã sửa thủ công", "latitude": 0, "longitude": 0, "accuracy": 27,
                    "lookupAddress": "Địa chỉ tra cứu", "lookupDistanceMeters": 3, "source": "geoapify", "approximate": False}
        response = self.create(self.payload(location=location))
        saved = response.get_json()["post"]["location"]
        for key, value in location.items():
            self.assertEqual(saved[key], value)
        self.assertIn("Geoapify", saved["attribution"])
        # A legacy quota configuration no longer imposes an application limit.
        self.app.config["JOURNAL_MAX_BYTES"] = 1
        response = self.create(images=[(io.BytesIO(self.image()), "sample.png", "image/png")])
        self.assertEqual(response.status_code, 201, response.get_json())

    def test_concurrent_creates_from_multiple_app_instances_and_restart_keep_all_data(self):
        apps = [self.app, create_app(self.config)]
        def create_one(number):
            client = apps[number % 2].test_client()
            self.login(client)
            return self.create(self.payload(title=f"Kỷ niệm {number}"), client=client).status_code
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(list(pool.map(create_one, range(8))), [201] * 8)
        client = create_app(self.config).test_client()
        posts = client.get("/api/journal?pageSize=30").get_json()["posts"]
        self.assertEqual(len(posts), 8)
        self.assertEqual(len({post["id"] for post in posts}), 8)

    def test_completed_upload_claim_and_public_range_follow_history_permissions(self):
        self.configure_journal()
        upload_id = self.complete_upload()
        outsider = self.app.test_client()
        response = self.create(self.payload(uploadIds=[upload_id]))
        self.assertEqual(response.status_code, 201, response.get_json())
        post = response.get_json()["post"]
        image = post["images"][0]
        self.assertEqual(image["id"], upload_id)
        self.assertEqual(image["kind"], "image")
        self.assertNotIn("storageArea", image)
        with outsider.get(image["url"], headers={"Range": "bytes=2-5"}) as ranged:
            self.assertEqual(ranged.status_code, 206)
            self.assertEqual(ranged.data, self.image()[2:6])
        self.assertEqual(self.create(self.payload(uploadIds=[upload_id])).status_code, 409)
        edit = self.client.put("/api/journal/" + post["id"], json=self.payload(password=self.journal_password, keepImageIds=[]), headers=self.headers())
        self.assertEqual(edit.status_code, 200, edit.get_json())
        self.assertEqual(outsider.get(image["url"]).status_code, 401)
        with self.client.get(image["url"]) as historic:
            self.assertEqual(historic.status_code, 200)

    def test_failed_history_save_preserves_completed_upload_for_retry(self):
        self.configure_journal()
        post = self.create().get_json()["post"]
        upload_id = self.complete_upload()
        with self.auth.connection() as db:
            db.execute("CREATE TRIGGER reject_history BEFORE INSERT ON journal_history BEGIN SELECT RAISE(ABORT,'simulated transaction failure'); END")
        payload = self.payload(password=self.journal_password, uploadIds=[upload_id], title="Thử lại")
        with self.assertLogs(self.app.logger, level="ERROR"):
            failed = self.client.put("/api/journal/" + post["id"], json=payload, headers=self.headers())
        self.assertEqual(failed.status_code, 500)
        self.assertEqual(self.client.get("/api/uploads/" + upload_id).get_json()["state"], "complete")
        self.assertEqual(self.client.get("/api/journal/" + post["id"]).get_json()["post"], post)
        with self.auth.connection() as db:
            db.execute("DROP TRIGGER reject_history")
        saved = self.client.put("/api/journal/" + post["id"], json=payload, headers=self.headers())
        self.assertEqual(saved.status_code, 200, saved.get_json())
        self.assertEqual(saved.get_json()["post"]["images"][0]["id"], upload_id)
        self.assertEqual(self.client.get("/api/uploads/" + upload_id).get_json()["state"], "claimed")

    def test_verified_journal_editor_can_stage_media_but_final_save_rechecks_password(self):
        self.configure_journal()
        post = self.create().get_json()["post"]
        editor = self.app.test_client()
        rejected = editor.post("/api/uploads", json={"scope": "journal", "name": "photo.png", "size": 10, "mimeType": "image/png"}, headers=self.headers(editor))
        self.assertEqual(rejected.status_code, 401)
        grant = editor.post("/api/journal/history/unlock", json={"password": self.journal_password}, headers=self.headers(editor))
        self.assertEqual(grant.status_code, 200)
        upload_id = self.complete_upload(editor)
        endpoint = "/api/journal/" + post["id"]
        no_password = editor.put(endpoint, json=self.payload(uploadIds=[upload_id]), headers=self.headers(editor))
        self.assertEqual(no_password.status_code, 401)
        saved = editor.put(endpoint, json=self.payload(uploadIds=[upload_id], password=self.journal_password), headers=self.headers(editor))
        self.assertEqual(saved.status_code, 200, saved.get_json())
        self.assertEqual(saved.get_json()["post"]["images"][0]["id"], upload_id)
        self.clock[0] += 301
        self.assertEqual(editor.get("/api/uploads/" + upload_id).status_code, 401)


if __name__ == "__main__":
    unittest.main()
