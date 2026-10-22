"""Meaningful API/security regression checks; all data and credentials are ephemeral."""
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import re
import secrets
import struct
import tempfile
import time
import unittest
from unittest import mock
from urllib.parse import urljoin
import zlib

from PIL import Image
from werkzeug.security import generate_password_hash

from server import create_app, MAX_IMAGE_BYTES, ROOT


class BackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = secrets.token_urlsafe(24)
        cls.password_hash = generate_password_hash(cls.password, method="scrypt:32768:8:1")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="lovedays-backend-test-")
        self.clock = [time.time()]
        self.config = {"TESTING": True, "DATA_DIR": self.temporary.name,
                       "PASSWORD_HASH": self.password_hash, "TIME_PROVIDER": lambda: self.clock[0]}
        self.app = create_app(self.config)
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/session").get_json()["csrfToken"]

    def tearDown(self):
        self.temporary.cleanup()

    def headers(self, csrf=None):
        return {"Origin": "http://localhost", "X-CSRF-Token": csrf or self.csrf}

    def login(self, client=None):
        client = client or self.client
        token = client.get("/api/session").get_json()["csrfToken"]
        response = client.post("/api/auth", json={"password": self.password}, headers=self.headers(token))
        self.assertEqual(response.status_code, 200, response.get_json())
        if client is self.client:
            self.csrf = response.get_json()["csrfToken"]
        return response.get_json()

    def payload(self, **changes):
        return {"senderId": "tuan", "senderName": "Anh Tuấn", "recipientId": "thu",
                "recipientName": "Lê Phạm Anh Thư", "type": "love-letter",
                "title": "Một ngày bình yên", "content": "Cảm ơn vì đã ở đây.\nThương em.", **changes}

    @staticmethod
    def image_data(format="PNG", color="pink"):
        stream = io.BytesIO()
        Image.new("RGB", (18, 12), color).save(stream, format=format)
        return stream.getvalue()

    def create(self, payload=None, images=None):
        payload = payload or self.payload()
        if images is None:
            return self.client.post("/api/letters", json=payload, headers=self.headers())
        response = self.client.post("/api/letters", data={"payload": json.dumps(payload), "images": images}, headers=self.headers(), content_type="multipart/form-data")
        self.addCleanup(response.close)
        self.addCleanup(response.request.environ["wsgi.input"].close)
        return response

    def test_unauthenticated_reads_and_writes_are_denied(self):
        self.assertEqual(self.client.get("/api/letters").status_code, 401)
        self.assertEqual(self.client.get("/api/letters/unknown").status_code, 401)
        self.assertEqual(self.client.get("/api/images/unknown").status_code, 401)
        self.assertEqual(self.create().status_code, 401)
        self.assertEqual(self.client.delete("/api/letters/unknown", headers=self.headers()).status_code, 401)

    def test_csrf_and_origin_apply_to_login_and_every_write(self):
        for headers in ({}, {"Origin": "http://localhost"}, {"Origin": "https://attacker.invalid", "X-CSRF-Token": self.csrf}):
            self.assertEqual(self.client.post("/api/auth", json={"password": self.password}, headers=headers).status_code, 403)
        self.login()
        self.assertEqual(self.client.post("/api/letters", json=self.payload(), headers={"Origin": "http://localhost"}).status_code, 403)
        self.assertEqual(self.client.post("/api/logout", headers={"Origin": "https://attacker.invalid", "X-CSRF-Token": self.csrf}).status_code, 403)
        self.assertEqual(self.client.get("/api/letters", headers={"Sec-Fetch-Site": "cross-site"}).status_code, 403)

    def test_signed_http_only_cookies_and_csrf_rotate(self):
        original = self.csrf
        response = self.client.post("/api/auth", json={"password": self.password}, headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.csrf = response.get_json()["csrfToken"]
        self.assertNotEqual(self.csrf, original)
        cookies = response.headers.getlist("Set-Cookie")
        self.assertTrue(any("lovedays_session=" in value and "HttpOnly" in value and "SameSite=Strict" in value for value in cookies))
        self.assertTrue(all(self.password not in value for value in cookies))
        self.assertEqual(self.client.post("/api/logout", headers=self.headers(original)).status_code, 403)
        logged_out = self.client.post("/api/logout", headers=self.headers()).get_json()
        self.assertFalse(logged_out["authenticated"])
        self.assertEqual(self.client.get("/api/letters").status_code, 401)

    def test_render_origin_fallback_preserves_custom_domain_and_csrf(self):
        for explicit, expected in (("", "https://love-days.onrender.com"), ("https://love.example.com", "https://love.example.com")):
            with mock.patch.dict("os.environ", {"LOVEDAYS_PUBLIC_ORIGIN": explicit, "RENDER_EXTERNAL_URL": "https://love-days.onrender.com"}):
                app = create_app(self.config)
            self.assertEqual(app.config["PUBLIC_ORIGIN"], expected)
            client = app.test_client()
            token = client.get("/api/session").get_json()["csrfToken"]
            response = client.post("/api/auth", json={"password": self.password}, headers={"Origin": "https://attacker.invalid", "X-CSRF-Token": token})
            self.assertEqual(response.status_code, 403)
            response = client.post("/api/auth", json={"password": self.password}, headers={"Origin": expected})
            self.assertEqual(response.status_code, 403)
            response = client.post("/api/auth", json={"password": self.password}, headers={"Origin": expected, "X-CSRF-Token": token})
            self.assertEqual(response.status_code, 200)

    def test_sixth_failure_closes_and_lockout_survives_reload_cookie_reset_restart(self):
        wrong = secrets.token_urlsafe(18)
        for attempt in range(1, 7):
            response = self.client.post("/api/auth", json={"password": wrong}, headers=self.headers())
            body = response.get_json()
            self.assertEqual(response.status_code, 429 if attempt == 6 else 401)
            self.assertEqual(body["attemptsRemaining"], 6 - attempt)
            self.assertEqual(body["closePopup"], attempt == 6)
            self.assertEqual(self.client.get("/api/session").get_json()["attemptsRemaining"], 6 - attempt)
        fresh_app = create_app(self.config)
        fresh_client = fresh_app.test_client()
        state = fresh_client.get("/api/session").get_json()
        self.assertEqual(state["attemptsRemaining"], 0)
        response = fresh_client.post("/api/auth", json={"password": self.password}, headers=self.headers(state["csrfToken"]))
        self.assertEqual(response.status_code, 429)
        self.assertGreater(int(response.headers["Retry-After"]), 0)
        self.clock[0] += 901
        self.assertEqual(fresh_client.get("/api/session").get_json()["attemptsRemaining"], 6)
        self.login(fresh_client)

    def test_absolute_session_expiry_is_server_enforced(self):
        state = self.login()
        self.assertEqual(state["expiresIn"], 1800)
        self.assertTrue(state["expiresAt"].endswith("Z"))
        self.clock[0] += 1200
        refreshed = self.client.get("/api/session").get_json()
        self.assertTrue(refreshed["authenticated"])
        self.assertEqual(refreshed["expiresIn"], 600)
        self.clock[0] += 601
        self.assertEqual(self.client.get("/api/letters").status_code, 401)
        self.assertFalse(self.client.get("/api/session").get_json()["authenticated"])

    def test_idle_expiry_and_password_change_revoke_sessions(self):
        self.login()
        self.clock[0] += 1801
        self.assertEqual(self.client.get("/api/letters").status_code, 401)
        self.login()
        self.app.extensions["auth_store"].override_hash = None
        self.app.extensions["auth_store"].set_password(generate_password_hash(secrets.token_urlsafe(24)))
        self.assertEqual(self.client.get("/api/letters").status_code, 401)

    def test_unconfigured_server_returns_useful_message(self):
        config = {**self.config, "DATA_DIR": str(Path(self.temporary.name) / "unconfigured"), "PASSWORD_HASH": None}
        client = create_app(config).test_client()
        state = client.get("/api/session").get_json()
        self.assertFalse(state["passwordConfigured"])
        response = client.post("/api/auth", json={"password": secrets.token_urlsafe(12)}, headers=self.headers(state["csrfToken"]))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["error"], "setup_required")

    def test_crud_preserves_server_identity_and_creation_time(self):
        self.login()
        response = self.create(self.payload(id="untrusted", createdAt="untrusted"))
        self.assertEqual(response.status_code, 201)
        first = response.get_json()["letter"]
        self.assertNotEqual(first["id"], "untrusted")
        self.assertTrue(first["createdAt"].endswith("Z"))
        self.clock[0] += 1
        self.create(self.payload(type="diary", title="Nhật ký"))
        listed = self.client.get("/api/letters").get_json()["letters"]
        self.assertEqual(listed[0]["type"], "diary")
        self.assertEqual(len(listed), 2)
        changed = self.client.put("/api/letters/" + first["id"], json=self.payload(type="message", title="Lời nhắn"), headers=self.headers()).get_json()["letter"]
        self.assertEqual(changed["createdAt"], first["createdAt"])
        self.assertNotEqual(changed["updatedAt"], first["updatedAt"])
        self.assertEqual(self.client.get("/api/letters/" + first["id"]).get_json()["letter"]["title"], "Lời nhắn")
        deleted = self.client.delete("/api/letters/" + first["id"], headers=self.headers())
        self.assertEqual(deleted.get_json()["deletedId"], first["id"])
        self.assertEqual(self.client.get("/api/letters/" + first["id"]).status_code, 404)

    def test_input_validation_rejects_wrong_types_and_limits(self):
        self.login()
        for change in ({"type": "love"}, {"senderId": []}, {"type": {}}, {"recipientId": "other"}, {"senderName": ""}, {"title": "x" * 161}, {"content": "x" * 20001}, {"content": "\x00"}, {"content": "\ud800"}, {"keepImageIds": ["../private"]}):
            self.assertEqual(self.create(self.payload(**change)).status_code, 400, change)
        self.assertEqual(self.client.get("/api/letters").get_json()["letters"], [])

    def test_all_supported_image_formats_are_decoded_and_reencoded(self):
        self.login()
        uploads = [(io.BytesIO(self.image_data(format)), "sample" + extension, mime) for format, extension, mime in (("JPEG", ".jpg", "image/jpeg"), ("PNG", ".png", "image/png"), ("WEBP", ".webp", "image/webp"))]
        response = self.create(images=uploads)
        self.assertEqual(response.status_code, 201, response.get_json())
        letter = response.get_json()["letter"]
        stored = json.loads(self.app.extensions["letter_store"].path.read_text(encoding="utf-8"))["letters"][0]
        for order, metadata in enumerate(stored["images"]):
            self.assertTrue({"id", "storageKey", "originalName", "mimeType", "size", "alt", "order"} <= metadata.keys())
            self.assertEqual(metadata["order"], order)
            public = letter["images"][order]
            self.assertNotIn("storageKey", public)
            image = self.client.get(public["url"])
            self.assertEqual(image.status_code, 200)
            self.assertEqual(image.headers["Cache-Control"], "no-store, private")
            self.assertEqual(len(image.data), metadata["size"])
            Image.open(io.BytesIO(image.data)).verify()
            image.close()
            outsider = self.app.test_client().get(public["url"])
            self.assertEqual(outsider.status_code, 401)

    def test_trailing_payload_and_exif_are_not_served(self):
        self.login()
        image = Image.new("RGB", (8, 8), "pink")
        exif = Image.Exif()
        exif[270] = "sensitive-camera-metadata"
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", exif=exif)
        uploaded = buffer.getvalue() + b"<script>trailing-payload</script>"
        response = self.create(images=[(io.BytesIO(uploaded), "photo.jpg", "image/jpeg")])
        self.assertEqual(response.status_code, 201)
        public_image = self.client.get(response.get_json()["letter"]["images"][0]["url"])
        self.assertNotIn(b"trailing-payload", public_image.data)
        self.assertNotIn(b"sensitive-camera-metadata", public_image.data)
        self.assertFalse(Image.open(io.BytesIO(public_image.data)).getexif())
        public_image.close()

    def test_fake_malformed_oversized_and_too_many_uploads_rejected(self):
        self.login()
        cases = [([(io.BytesIO(b"<svg>not a raster image</svg>"), "fake.png", "image/png")], 400),
                 ([(io.BytesIO(self.image_data()), "wrong.jpg", "image/jpeg")], 400),
                 ([(io.BytesIO(self.image_data()[:20]), "broken.png", "image/png")], 400),
                 ([(io.BytesIO(b"x" * (MAX_IMAGE_BYTES + 1)), "large.png", "image/png")], 413),
                 ([(io.BytesIO(self.image_data()), "photo.png", "image/png") for _ in range(6)], 400)]
        for uploads, expected in cases:
            response = self.create(images=uploads)
            self.assertEqual(response.status_code, expected, response.get_json())
        self.assertEqual(list(self.app.extensions["letter_store"].images.iterdir()), [])

    def test_decompression_bomb_dimensions_rejected_before_pixel_allocation(self):
        self.login()
        raw = bytearray(self.image_data())
        # Replace only PNG IHDR dimensions and CRC; no huge bitmap is allocated by the test.
        raw[16:24] = struct.pack(">II", 100000, 100000)
        raw[29:33] = struct.pack(">I", zlib.crc32(raw[12:29]) & 0xFFFFFFFF)
        response = self.create(images=[(io.BytesIO(raw), "huge.png", "image/png")])
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "invalid_image")
        self.assertEqual(list(self.app.extensions["letter_store"].images.iterdir()), [])

    def test_forged_session_cookie_never_authenticates(self):
        self.login()
        self.client.set_cookie("lovedays_session", secrets.token_urlsafe(48))
        self.assertEqual(self.client.get("/api/letters").status_code, 401)
        self.assertFalse(self.client.get("/api/session").get_json()["authenticated"])

    def test_update_image_order_keep_remove_and_delete_cleanup(self):
        self.login()
        first = self.create(images=[(io.BytesIO(self.image_data()), "one.png", "image/png"), (io.BytesIO(self.image_data(color="red")), "two.png", "image/png")]).get_json()["letter"]
        images = first["images"]
        ordered = self.client.put("/api/letters/" + first["id"], json=self.payload(keepImageIds=[images[1]["id"], images[0]["id"]]), headers=self.headers()).get_json()["letter"]
        self.assertEqual([item["id"] for item in ordered["images"]], [images[1]["id"], images[0]["id"]])
        self.assertEqual([item["order"] for item in ordered["images"]], [0, 1])
        response = self.client.put("/api/letters/" + first["id"], json=self.payload(keepImageIds=[images[1]["id"]]), headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(images[0]["url"]).status_code, 404)
        self.assertEqual(len(list(self.app.extensions["letter_store"].images.iterdir())), 1)
        self.client.delete("/api/letters/" + first["id"], headers=self.headers())
        self.assertEqual(list(self.app.extensions["letter_store"].images.iterdir()), [])

    def test_cannot_reuse_attachment_from_another_letter(self):
        self.login()
        first = self.create(images=[(io.BytesIO(self.image_data()), "photo.png", "image/png")]).get_json()["letter"]
        other = self.create().get_json()["letter"]
        response = self.client.put("/api/letters/" + other["id"], json=self.payload(keepImageIds=[first["images"][0]["id"]]), headers=self.headers())
        self.assertEqual(response.status_code, 400)

    def test_stale_updates_are_rejected_and_timestamps_are_monotonic(self):
        self.login()
        first = self.create().get_json()["letter"]
        url = "/api/letters/" + first["id"]
        saved = self.client.put(url, json=self.payload(title="Bản mới", expectedUpdatedAt=first["updatedAt"]), headers=self.headers())
        self.assertEqual(saved.status_code, 200)
        updated = saved.get_json()["letter"]
        self.assertGreater(updated["updatedAt"], first["updatedAt"])
        stale = self.client.put(url, json=self.payload(title="Bản đã cũ", expectedUpdatedAt=first["updatedAt"]), headers=self.headers())
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.get_json()["error"], "edit_conflict")
        self.assertEqual(self.client.get(url).get_json()["letter"]["title"], "Bản mới")

    def test_failed_json_commit_removes_staged_attachments(self):
        self.login()
        store = self.app.extensions["letter_store"]
        before = store.path.read_bytes()
        with mock.patch.object(store, "write", side_effect=OSError("simulated disk failure")), self.assertLogs(self.app.logger, level="ERROR"):
            response = self.create(images=[(io.BytesIO(self.image_data()), "photo.png", "image/png")])
        self.assertEqual(response.status_code, 500)
        self.assertEqual(store.path.read_bytes(), before)
        self.assertEqual(list(store.images.iterdir()), [])

    def test_corrupt_json_is_preserved_and_never_reset(self):
        self.login()
        path = self.app.extensions["letter_store"].path
        corrupt = b'{"schemaVersion":1,"letters":[BROKEN'
        path.write_bytes(corrupt)
        with self.assertLogs(self.app.logger, level="ERROR"):
            self.assertEqual(self.client.get("/api/letters").status_code, 503)
            self.assertEqual(self.create().status_code, 503)
        create_app(self.config)
        self.assertEqual(path.read_bytes(), corrupt)

    def test_private_files_source_docs_and_traversal_are_never_public(self):
        for resource in ("/server.py", "/requirements.txt", "/.gitignore", "/letters.json", "/auth.sqlite3", "/secret.key", "/uploads/a.png", "/docs/letters.example.json", "/tests/test_backend.py", "/img/../server.py", "/img/%2e%2e/server.py", "/img/..%5cserver.py", "/.lovedays-private/letters.json"):
            self.assertEqual(self.client.get(resource).status_code, 404, resource)
        for resource in ("/main/img/../../server.py", "/main/img/%2e%2e/%2e%2e/server.py", "/main/img/..%5c..%5cserver.py", "/main/js/server.py", "/main/css/letters.json"):
            self.assertEqual(self.client.get(resource).status_code, 404, resource)
        for resource in ("/", "/main/js/app.js", "/main/js/profiles.js", "/main/js/scroll.js", "/main/js/loading.js", "/main/js/letters.js", "/main/js/mobile.js", "/main/css/style.css", "/main/css/effects.css", "/main/css/letters.css", "/main/img/heart.png", "/main/img/traitim.gif", "/main/music/nhactinhyeu.mp3", "/app.js", "/style.css", "/fonts/Lora-Variable.ttf"):
            with self.client.get(resource) as response:
                self.assertEqual(response.status_code, 200, resource)
        with self.client.get("/main/css/effects.css") as response:
            font_reference = re.search(r'url\(["\']?([^"\')]+)', response.get_data(as_text=True))
            self.assertIsNotNone(font_reference)
            font_url = urljoin("/main/css/effects.css", font_reference.group(1))
        with self.client.get(font_url) as response:
            self.assertEqual(response.status_code, 200, font_url)
            self.assertIn("font", response.mimetype)

    def test_private_data_directory_cannot_be_inside_webroot(self):
        with self.assertRaises(ValueError):
            create_app({**self.config, "DATA_DIR": str(ROOT / ".lovedays-private")})

    def test_concurrent_writes_from_independent_app_instances_lose_no_letters(self):
        second = create_app(self.config)
        def create_one(index):
            app = self.app if index % 2 == 0 else second
            with app.test_client() as client:
                state = self.login(client)
                response = client.post("/api/letters", json=self.payload(title=f"Thư {index}"), headers=self.headers(state["csrfToken"]))
                return response.status_code
        with ThreadPoolExecutor(max_workers=6) as executor:
            statuses = list(executor.map(create_one, range(18)))
        self.assertEqual(statuses, [201] * 18)
        self.login()
        letters = self.client.get("/api/letters").get_json()["letters"]
        self.assertEqual(len(letters), 18)
        self.assertEqual(len({letter["id"] for letter in letters}), 18)
        self.assertEqual({letter["title"] for letter in letters}, {f"Thư {index}" for index in range(18)})


if __name__ == "__main__":
    unittest.main()
