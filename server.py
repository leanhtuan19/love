"""Private letter API and an explicit public-file allowlist. Python 3.9+.

Run ``python server.py init-password`` once, then ``python server.py serve``.
Letters and attachments always live outside the web root. No default password exists.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import wraps
import getpass
import hashlib
import hmac
import io
import json
import logging
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile
import threading
import time
from urllib.parse import urlsplit
import uuid
import warnings

from filelock import FileLock, Timeout as FileLockTimeout
from flask import Flask, g, jsonify, request, send_file
from itsdangerous import BadSignature, URLSafeTimedSerializer
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash


ROOT = Path(__file__).resolve().parent
PEOPLE = [
    {"id": "tuan", "name": "Lê Anh Tuấn"},
    {"id": "thu", "name": "Lê Phạm Anh Thư"},
]
PERSON_NAMES = {person["id"]: person["name"] for person in PEOPLE}
LETTER_TYPES = {"diary", "love-letter", "message"}
MAX_IMAGES = 5
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 12_000_000
LIMITS = {"maxImages": MAX_IMAGES, "maxImageBytes": MAX_IMAGE_BYTES,
          "maxTitleLength": 160, "maxContentLength": 20000, "maxNameLength": 80}
PUBLIC_FILES = {
    "index.html", "main/css/style.css", "main/css/effects.css", "main/css/letters.css",
    "main/js/app.js", "main/js/profiles.js", "main/js/scroll.js",
    "main/js/loading.js", "main/js/letters.js", "main/js/mobile.js",
    "fonts/Lora-Variable.ttf", "fonts/OFL-Lora.txt",
}
PUBLIC_ALIASES = {
    "style.css": "main/css/style.css", "effects.css": "main/css/effects.css",
    "letters.css": "main/css/letters.css", "app.js": "main/js/app.js",
    "profiles.js": "main/js/profiles.js", "scroll.js": "main/js/scroll.js",
    "loading.js": "main/js/loading.js", "letters.js": "main/js/letters.js",
}
IMAGE_FORMATS = {"JPEG": ("image/jpeg", ".jpg"), "PNG": ("image/png", ".png"),
                 "WEBP": ("image/webp", ".webp")}
STORAGE_KEY = re.compile(r"^[0-9a-f]{32}\.(?:jpg|png|webp)$")
OPAQUE_ID = re.compile(r"^[A-Za-z0-9_-]{43}$")
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class ApiError(Exception):
    def __init__(self, status, code, message, **extra):
        super().__init__(code)
        self.status, self.code, self.message, self.extra = status, code, message, extra


class DataCorruption(Exception):
    """Existing data must be repaired explicitly, never silently replaced."""


def canonical_uuid(value):
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value and uuid.UUID(value).version == 4
    except (ValueError, AttributeError):
        return False


def utc_timestamp(now):
    return datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def valid_text(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or "\x00" in value:
        return False
    try:
        value.encode("utf-8")
        return True
    except UnicodeEncodeError:
        return False


def atomic_write(path, value):
    """Commit only a completely written, flushed file on the same filesystem."""
    handle, temporary = tempfile.mkstemp(prefix=".pending-", dir=str(path.parent))
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            try:
                directory = os.open(str(path.parent), os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            except OSError:
                # The replacement already committed; do not falsely roll back its attachments.
                logging.getLogger(__name__).warning("Directory sync was unavailable after an atomic commit")
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def json_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


class LetterStore:
    def __init__(self, directory):
        self.directory = directory
        self.path = directory / "letters.json"
        self.images = directory / "images"
        self.images.mkdir(mode=0o700, exist_ok=True)
        # WSGI servers may import this store before forking their workers.
        # Neither an inherited RLock nor a FileLock may be reused by a child.
        self._process_locks = {}
        with self.locked():
            if not self.path.exists():
                self.write({"schemaVersion": 1, "letters": []})

    @contextmanager
    def locked(self):
        try:
            pid = os.getpid()
            locks = self._process_locks.get(pid)
            if locks is None:
                # Publish one pair per process, even when its first requests
                # arrive concurrently. Unselected pairs have never been held.
                locks = self._process_locks.setdefault(pid, (
                    threading.RLock(),
                    FileLock(str(self.directory / "letters.lock"), timeout=15),
                ))
            with locks[0], locks[1]:
                yield
        except FileLockTimeout:
            raise ApiError(503, "storage_busy", "Hộp thư đang bận. Vui lòng thử lại.")

    def read(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"), object_pairs_hook=json_without_duplicates)
            self.validate(data)
            return data
        except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
            raise DataCorruption("Letter storage is unreadable or invalid") from exc

    @staticmethod
    def validate(data):
        if not isinstance(data, dict) or type(data.get("schemaVersion")) is not int or data["schemaVersion"] != 1 or not isinstance(data.get("letters"), list):
            raise ValueError("Invalid document schema")
        ids, image_ids, keys = set(), set(), set()
        for letter in data["letters"]:
            if not isinstance(letter, dict) or not canonical_uuid(letter.get("id")) or letter["id"] in ids:
                raise ValueError("Invalid letter ID")
            ids.add(letter["id"])
            if letter.get("type") not in LETTER_TYPES:
                raise ValueError("Invalid letter type")
            for field in ("senderId", "recipientId"):
                if letter.get(field) not in PERSON_NAMES:
                    raise ValueError("Invalid person")
            for field, maximum in (("senderName", 80), ("recipientName", 80), ("title", 160), ("content", 20000)):
                value = letter.get(field)
                if not valid_text(value, maximum):
                    raise ValueError("Invalid letter text")
            for field in ("createdAt", "updatedAt"):
                if not isinstance(letter.get(field), str) or not letter[field].endswith("Z"):
                    raise ValueError("Invalid timestamp")
                datetime.fromisoformat(letter[field].replace("Z", "+00:00"))
            if not isinstance(letter.get("images"), list) or len(letter["images"]) > MAX_IMAGES:
                raise ValueError("Invalid image collection")
            for order, image in enumerate(letter["images"]):
                if not isinstance(image, dict) or not canonical_uuid(image.get("id")) or image["id"] in image_ids:
                    raise ValueError("Invalid image ID")
                image_ids.add(image["id"])
                key = image.get("storageKey")
                if not isinstance(key, str) or not STORAGE_KEY.fullmatch(key) or key in keys:
                    raise ValueError("Invalid storage key")
                keys.add(key)
                if image.get("mimeType") not in {value[0] for value in IMAGE_FORMATS.values()}:
                    raise ValueError("Invalid image type")
                if type(image.get("size")) is not int or not 0 < image["size"] <= MAX_IMAGE_BYTES:
                    raise ValueError("Invalid image size")
                if type(image.get("order")) is not int or image["order"] != order:
                    raise ValueError("Invalid image order")
                for field, maximum in (("originalName", 180), ("alt", 240)):
                    if not isinstance(image.get(field), str) or not image[field] or len(image[field]) > maximum or "\x00" in image[field]:
                        raise ValueError("Invalid image description")

    def write(self, data):
        self.validate(data)
        atomic_write(self.path, json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8"))

    def remove_images(self, images):
        for image in images:
            try:
                (self.images / image["storageKey"]).unlink(missing_ok=True)
            except OSError:
                logging.getLogger(__name__).warning("Attachment cleanup deferred: %s", image["id"])


class AuthStore:
    def __init__(self, directory, override_hash=None, journal_mode="WAL"):
        if not isinstance(journal_mode, str) or journal_mode.upper() not in {"WAL", "DELETE"}:
            raise ValueError("LOVEDAYS_SQLITE_JOURNAL_MODE must be WAL or DELETE")
        journal_mode = journal_mode.upper()
        self.path = directory / "auth.sqlite3"
        self.override_hash = override_hash
        with self.connection() as db:
            # WAL requires local shared memory. Network-backed hosts such as
            # PythonAnywhere need SQLite's rollback journal instead.
            db.execute(f"PRAGMA journal_mode={journal_mode}")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS browsers (id TEXT PRIMARY KEY, csrf TEXT NOT NULL, created REAL NOT NULL, seen REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, browser_id TEXT NOT NULL, created REAL NOT NULL, seen REAL NOT NULL, version TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS failures (key TEXT PRIMARY KEY, count INTEGER NOT NULL, started REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS session_browser ON sessions(browser_id);
            """)
        if os.name != "nt":
            self.path.chmod(0o600)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(str(self.path), timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def password_hash(self, db):
        if self.override_hash:
            return self.override_hash
        row = db.execute("SELECT value FROM settings WHERE key='password_hash'").fetchone()
        return row[0] if row else None

    def set_password(self, password_hash):
        with self.transaction() as db:
            db.execute("INSERT INTO settings(key,value) VALUES('password_hash',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (password_hash,))
            db.execute("DELETE FROM sessions")


def sanitize_upload(upload, title):
    raw = upload.stream.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ApiError(413, "image_too_large", "Mỗi ảnh được tối đa 5 MB.")
    filename = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    filename = "".join(character for character in filename if character.isprintable()).strip()[:180]
    suffix = Path(filename).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise ApiError(400, "invalid_image", "Chỉ nhận ảnh JPEG, PNG hoặc WebP.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw), formats=tuple(IMAGE_FORMATS)) as source:
                detected = source.format
                if detected not in IMAGE_FORMATS or source.width * source.height > MAX_IMAGE_PIXELS or max(source.size) > 8000:
                    raise ValueError("Image dimensions exceed limit")
                mime, extension = IMAGE_FORMATS[detected]
                allowed_suffixes = {".jpg", ".jpeg"} if detected == "JPEG" else {extension}
                if suffix not in allowed_suffixes or upload.mimetype not in (mime, "application/octet-stream"):
                    raise ValueError("Image format does not match its declared type")
                if getattr(source, "n_frames", 1) != 1:
                    raise ValueError("Animated images are not supported")
                source.verify()
            with Image.open(io.BytesIO(raw), formats=tuple(IMAGE_FORMATS)) as source:
                source.load()
                oriented = ImageOps.exif_transpose(source)
                mode = "RGB" if detected == "JPEG" else ("RGBA" if "A" in oriented.getbands() or "transparency" in oriented.info else "RGB")
                # A fresh pixel-only image omits EXIF, XMP, comments, profiles and trailing payloads.
                clean = Image.new(mode, oriented.size)
                clean.paste(oriented.convert(mode))
                output = io.BytesIO()
                options = {"quality": 88} if detected in ("JPEG", "WEBP") else {"compress_level": 6}
                clean.save(output, format=detected, **options)
                encoded = output.getvalue()
                width, height = clean.size
                clean.close()
        if not encoded or len(encoded) > MAX_IMAGE_BYTES:
            raise ApiError(413, "image_too_large", "Ảnh sau xử lý vượt 5 MB. Hãy chọn ảnh nhỏ hơn.")
    except ApiError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ApiError(400, "invalid_image", "Ảnh không hợp lệ, bị hỏng hoặc có kích thước quá lớn.") from exc
    image_id = str(uuid.uuid4())
    metadata = {"id": image_id, "storageKey": uuid.uuid4().hex + extension,
                "originalName": filename, "mimeType": mime, "size": len(encoded),
                "alt": ("Ảnh đính kèm: " + title)[:240], "order": 0, "width": width, "height": height}
    return metadata, encoded


def create_app(test_config=None):
    app = Flask(__name__, static_folder=None)
    workspace_key = hashlib.sha256(str(ROOT).casefold().encode()).hexdigest()[:16]
    app.config.from_mapping(
        DATA_DIR=os.environ.get("LOVEDAYS_DATA_DIR", str(Path.home() / ".lovedays-private" / workspace_key)),
        PASSWORD_HASH=os.environ.get("LOVEDAYS_PASSWORD_HASH"),
        SQLITE_JOURNAL_MODE=os.environ.get("LOVEDAYS_SQLITE_JOURNAL_MODE", "WAL"),
        COOKIE_SECURE=os.environ.get("LOVEDAYS_COOKIE_SECURE", "").lower() in ("1", "true", "yes"),
        PUBLIC_ORIGIN=os.environ.get("LOVEDAYS_PUBLIC_ORIGIN") or os.environ.get("RENDER_EXTERNAL_URL"),
        SESSION_TTL_SECONDS=1800, LOGIN_WINDOW_SECONDS=900, MAX_LOGIN_FAILURES=6,
        TIME_PROVIDER=time.time, MAX_CONTENT_LENGTH=MAX_IMAGES * MAX_IMAGE_BYTES + 512 * 1024,
        MAX_FORM_MEMORY_SIZE=128 * 1024, MAX_FORM_PARTS=12,
    )
    if test_config:
        app.config.update(test_config)
    data_dir = Path(app.config["DATA_DIR"]).expanduser().resolve()
    if data_dir == ROOT or ROOT in data_dir.parents:
        raise ValueError("LOVEDAYS_DATA_DIR must be outside the public project directory")
    data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    with FileLock(str(data_dir / "setup.lock"), timeout=15):
        secret_path = data_dir / "secret.key"
        if not secret_path.exists():
            atomic_write(secret_path, secrets.token_bytes(48))
        secret = secret_path.read_bytes()
        if len(secret) < 32:
            raise ValueError("Private signing key is invalid; do not replace it silently")
    signer = URLSafeTimedSerializer(secret, salt="lovedays-private-v1")
    store = LetterStore(data_dir)
    auth = AuthStore(data_dir, app.config["PASSWORD_HASH"], app.config["SQLITE_JOURNAL_MODE"])
    app.extensions.update(letter_store=store, auth_store=auth)

    def now():
        return float(app.config["TIME_PROVIDER"]())

    def decode_cookie(name, age):
        try:
            value = signer.loads(request.cookies.get(name, ""), max_age=age, salt=name)
            return value if isinstance(value, str) and OPAQUE_ID.fullmatch(value) else None
        except BadSignature:
            return None

    def failure_keys():
        # Forwarded headers are deliberately ignored unless a trusted proxy is configured externally.
        address = request.remote_addr or "unknown"
        digest = hmac.new(secret, address.encode(), hashlib.sha256).hexdigest()
        return ("browser:" + g.browser_id, "ip:" + digest)

    def rate_status(db):
        maximum, retry = 0, 0
        for key in failure_keys():
            row = db.execute("SELECT count,started FROM failures WHERE key=?", (key,)).fetchone()
            if row and row["started"] + app.config["LOGIN_WINDOW_SECONDS"] > now():
                maximum = max(maximum, row["count"])
                if row["count"] >= app.config["MAX_LOGIN_FAILURES"]:
                    retry = max(retry, math.ceil(row["started"] + app.config["LOGIN_WINDOW_SECONDS"] - now()))
        return max(0, app.config["MAX_LOGIN_FAILURES"] - maximum), retry

    def session_payload(db):
        remaining, retry = rate_status(db)
        return {"authenticated": g.authenticated, "csrfToken": g.csrf,
                "attemptsRemaining": remaining, "retryAfter": retry, "closePopup": retry > 0,
                "limits": LIMITS, "people": PEOPLE, "sharedAccess": True,
                "passwordConfigured": bool(auth.password_hash(db)),
                "expiresAt": utc_timestamp(g.session_expires_at) if g.authenticated else None,
                "expiresIn": max(0, math.ceil(g.session_expires_at - now())) if g.authenticated else 0}

    @app.before_request
    def protect_api():
        if not request.path.startswith("/api/"):
            return
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            raise ApiError(403, "cross_origin", "Yêu cầu phải đến từ chính trang này.")
        timestamp = now()
        g.new_browser = False
        g.new_session = None
        g.clear_session = False
        g.authenticated = False
        g.session_expires_at = None
        with auth.transaction() as db:
            browser_id = decode_cookie("lovedays_browser", 30 * 86400)
            browser = db.execute("SELECT * FROM browsers WHERE id=?", (browser_id,)).fetchone() if browser_id else None
            if not browser:
                browser_id, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                db.execute("INSERT INTO browsers VALUES(?,?,?,?)", (browser_id, csrf, timestamp, timestamp))
                g.new_browser = True
            else:
                csrf = browser["csrf"]
                db.execute("UPDATE browsers SET seen=? WHERE id=?", (timestamp, browser_id))
            g.browser_id, g.csrf = browser_id, csrf
            session_id = decode_cookie("lovedays_session", app.config["SESSION_TTL_SECONDS"])
            record = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone() if session_id else None
            password_hash = auth.password_hash(db)
            version = hashlib.sha256(password_hash.encode()).hexdigest() if password_hash else None
            if record and record["browser_id"] == browser_id and record["version"] == version and timestamp - record["created"] < app.config["SESSION_TTL_SECONDS"] and timestamp - record["seen"] < app.config["SESSION_TTL_SECONDS"]:
                g.authenticated = True
                g.session_expires_at = min(record["created"] + app.config["SESSION_TTL_SECONDS"], timestamp + app.config["SESSION_TTL_SECONDS"])
                db.execute("UPDATE sessions SET seen=? WHERE id=?", (timestamp, session_id))
            elif session_id:
                db.execute("DELETE FROM sessions WHERE id=?", (session_id,))
                g.clear_session = True
            db.execute("DELETE FROM sessions WHERE created<? OR seen<?", (timestamp - app.config["SESSION_TTL_SECONDS"], timestamp - app.config["SESSION_TTL_SECONDS"]))
            db.execute("DELETE FROM failures WHERE started<?", (timestamp - app.config["LOGIN_WINDOW_SECONDS"],))
            db.execute("DELETE FROM browsers WHERE seen<?", (timestamp - 31 * 86400,))
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("Origin")
            if not origin:
                referer = urlsplit(request.headers.get("Referer", ""))
                origin = f"{referer.scheme}://{referer.netloc}" if referer.scheme and referer.netloc else None
            expected = (app.config["PUBLIC_ORIGIN"] or request.host_url).rstrip("/")
            if not origin or origin.rstrip("/").lower() != expected.lower():
                raise ApiError(403, "cross_origin", "Yêu cầu phải đến từ chính trang này.")
            token = request.headers.get("X-CSRF-Token", "")
            if not token or not hmac.compare_digest(token.encode("utf-8"), g.csrf.encode("utf-8")):
                raise ApiError(403, "csrf_error", "Phiên xác thực đã đổi. Vui lòng tải lại hộp thư.")

    def authenticated(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not g.authenticated:
                raise ApiError(401, "unauthorized", "Vui lòng mở khóa để xem thư bí mật.")
            return view(*args, **kwargs)
        return wrapped

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; media-src 'self'; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Vary"] = "Cookie"
            if getattr(g, "new_browser", False):
                response.set_cookie("lovedays_browser", signer.dumps(g.browser_id, salt="lovedays_browser"), max_age=30 * 86400, httponly=True, secure=app.config["COOKIE_SECURE"], samesite="Strict", path="/")
            if getattr(g, "new_session", None):
                response.set_cookie("lovedays_session", signer.dumps(g.new_session, salt="lovedays_session"), max_age=app.config["SESSION_TTL_SECONDS"], httponly=True, secure=app.config["COOKIE_SECURE"], samesite="Strict", path="/")
            elif getattr(g, "clear_session", False):
                response.delete_cookie("lovedays_session", httponly=True, secure=app.config["COOKIE_SECURE"], samesite="Strict", path="/")
        return response

    @app.errorhandler(ApiError)
    def api_error(error):
        response = jsonify(error=error.code, message=error.message, **error.extra)
        if error.extra.get("retryAfter"):
            response.headers["Retry-After"] = str(error.extra["retryAfter"])
        return response, error.status

    @app.errorhandler(DataCorruption)
    def corrupt_data(error):
        app.logger.error("Existing letter data is invalid; data was preserved")
        return jsonify(error="storage_corrupt", message="Dữ liệu hộp thư cần được kiểm tra. Các thư hiện có vẫn được giữ nguyên."), 503

    @app.errorhandler(Exception)
    def unexpected_error(error):
        if isinstance(error, HTTPException):
            if request.path.startswith("/api/"):
                message = "Yêu cầu quá lớn. Tối đa 5 ảnh, mỗi ảnh 5 MB." if error.code == 413 else "Yêu cầu không hợp lệ hoặc không tìm thấy."
                return jsonify(error="request_too_large" if error.code == 413 else "request_error", message=message), error.code
            return error
        app.logger.exception("Private API operation failed")
        return jsonify(error="server_error", message="Hộp thư tạm thời chưa xử lý được. Vui lòng thử lại."), 500

    @app.get("/api/session")
    def get_session():
        with auth.connection() as db:
            return jsonify(session_payload(db))

    @app.post("/api/auth")
    def login():
        request.max_content_length = 4096
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or not valid_text(body.get("password"), 256):
            raise ApiError(400, "invalid_password", "Vui lòng nhập mật khẩu hợp lệ.")
        with auth.transaction() as db:
            remaining, retry = rate_status(db)
            if retry:
                raise ApiError(429, "rate_limited", "Đã nhập sai 6 lần. Hãy đợi trước khi thử lại.", attemptsRemaining=0, closePopup=True, retryAfter=retry)
            password_hash = auth.password_hash(db)
            if not password_hash:
                raise ApiError(503, "setup_required", "Hộp thư chưa được thiết lập mật khẩu trên máy chủ.")
            if not check_password_hash(password_hash, body["password"]):
                timestamp = now()
                for key in failure_keys():
                    row = db.execute("SELECT count,started FROM failures WHERE key=?", (key,)).fetchone()
                    count = row["count"] + 1 if row and row["started"] + app.config["LOGIN_WINDOW_SECONDS"] > timestamp else 1
                    started = row["started"] if row and row["started"] + app.config["LOGIN_WINDOW_SECONDS"] > timestamp else timestamp
                    db.execute("INSERT INTO failures VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET count=excluded.count,started=excluded.started", (key, count, started))
                remaining, retry = rate_status(db)
                # Commit failed attempts before raising an HTTP error.
                db.commit()
                raise ApiError(429 if retry else 401, "rate_limited" if retry else "incorrect_password", "Đã nhập sai 6 lần. Hãy đợi trước khi thử lại." if retry else "Mật khẩu chưa đúng. Bạn hãy thử lại.", attemptsRemaining=remaining, closePopup=bool(retry), retryAfter=retry)
            for key in failure_keys():
                db.execute("DELETE FROM failures WHERE key=?", (key,))
            g.csrf = secrets.token_urlsafe(32)
            db.execute("UPDATE browsers SET csrf=? WHERE id=?", (g.csrf, g.browser_id))
            db.execute("DELETE FROM sessions WHERE browser_id=?", (g.browser_id,))
            g.new_session = secrets.token_urlsafe(32)
            db.execute("INSERT INTO sessions VALUES(?,?,?,?,?)", (g.new_session, g.browser_id, now(), now(), hashlib.sha256(password_hash.encode()).hexdigest()))
            g.authenticated = True
            g.session_expires_at = now() + app.config["SESSION_TTL_SECONDS"]
            return jsonify(session_payload(db))

    @app.post("/api/logout")
    def logout():
        with auth.transaction() as db:
            db.execute("DELETE FROM sessions WHERE browser_id=?", (g.browser_id,))
            g.csrf = secrets.token_urlsafe(32)
            db.execute("UPDATE browsers SET csrf=? WHERE id=?", (g.csrf, g.browser_id))
            g.authenticated = False
            g.clear_session = True
            return jsonify(session_payload(db))

    def public_letter(letter):
        result = dict(letter)
        result["images"] = [{**{key: value for key, value in image.items() if key != "storageKey"}, "url": "/api/images/" + image["id"]} for image in letter["images"]]
        return result

    def parse_letter_input():
        if request.mimetype == "multipart/form-data":
            try:
                body = json.loads(request.form.get("payload", ""), object_pairs_hook=json_without_duplicates)
            except (ValueError, TypeError):
                raise ApiError(400, "invalid_payload", "Nội dung thư không hợp lệ.")
            if any(key != "images" for key in request.files):
                raise ApiError(400, "invalid_images", "Trường ảnh không hợp lệ.")
            uploads = [upload for upload in request.files.getlist("images") if upload.filename]
        elif request.is_json:
            body, uploads = request.get_json(silent=True), []
        else:
            raise ApiError(415, "unsupported_content", "Vui lòng gửi thư bằng JSON hoặc biểu mẫu tải ảnh.")
        if not isinstance(body, dict):
            raise ApiError(400, "invalid_payload", "Nội dung thư không hợp lệ.")
        expected_updated_at = body.get("expectedUpdatedAt")
        if expected_updated_at is not None and (not isinstance(expected_updated_at, str) or len(expected_updated_at) > 40):
            raise ApiError(400, "invalid_payload", "Mốc cập nhật của thư không hợp lệ.")
        if any(not isinstance(body.get(field), str) for field in ("senderId", "recipientId", "type")) or body["senderId"] not in PERSON_NAMES or body["recipientId"] not in PERSON_NAMES or body["type"] not in LETTER_TYPES:
            raise ApiError(400, "invalid_letter", "Người gửi, người nhận hoặc loại thư không hợp lệ.")
        values = {"senderId": body["senderId"], "recipientId": body["recipientId"], "type": body["type"], "recipientName": PERSON_NAMES[body["recipientId"]]}
        for field, maximum in (("senderName", 80), ("title", 160), ("content", 20000)):
            value = body.get(field, PERSON_NAMES[body["senderId"]] if field == "senderName" else None)
            if not valid_text(value, maximum) or (field != "content" and any(character in value for character in "\r\n")):
                raise ApiError(400, "invalid_letter", "Tên người gửi, tiêu đề hoặc nội dung chưa hợp lệ.")
            values[field] = value.strip() if field != "content" else value
        keep = body.get("keepImageIds")
        if keep is not None and (not isinstance(keep, list) or len(keep) > MAX_IMAGES or any(not canonical_uuid(item) for item in keep) or len(set(keep)) != len(keep)):
            raise ApiError(400, "invalid_images", "Danh sách ảnh giữ lại không hợp lệ.")
        if len(uploads) > MAX_IMAGES:
            raise ApiError(400, "too_many_images", "Mỗi thư được đính kèm tối đa 5 ảnh.")
        processed = [sanitize_upload(upload, values["title"]) for upload in uploads]
        return values, keep, processed, expected_updated_at

    @app.get("/api/letters")
    @authenticated
    def list_letters():
        with store.locked():
            data = store.read()
        ordered = sorted(enumerate(data["letters"]), key=lambda item: (item[1]["createdAt"], item[0]), reverse=True)
        return jsonify(letters=[public_letter(letter) for _, letter in ordered])

    @app.get("/api/letters/<letter_id>")
    @authenticated
    def read_letter(letter_id):
        with store.locked():
            data = store.read()
            letter = next((item for item in data["letters"] if item["id"] == letter_id), None)
        if not letter:
            raise ApiError(404, "not_found", "Không tìm thấy bức thư này.")
        return jsonify(letter=public_letter(letter))

    @app.route("/api/letters", methods=["POST"])
    @app.route("/api/letters/<letter_id>", methods=["PUT"])
    @authenticated
    def save_letter(letter_id=None):
        values, keep, processed, expected_updated_at = parse_letter_input()
        with store.locked():
            data = store.read()
            existing = next((item for item in data["letters"] if item["id"] == letter_id), None) if letter_id else None
            if letter_id and existing is None:
                raise ApiError(404, "not_found", "Không tìm thấy bức thư này.")
            if existing and expected_updated_at is not None and expected_updated_at != existing["updatedAt"]:
                raise ApiError(409, "edit_conflict", "Bức thư đã được cập nhật ở nơi khác. Bản nháp của bạn vẫn được giữ; hãy tải lại thư trước khi lưu.")
            old_images = existing["images"] if existing else []
            if keep is None:
                keep = [image["id"] for image in old_images]
            by_id = {image["id"]: image for image in old_images}
            if any(image_id not in by_id for image_id in keep):
                raise ApiError(400, "invalid_images", "Ảnh giữ lại phải thuộc chính bức thư này.")
            if len(keep) + len(processed) > MAX_IMAGES:
                raise ApiError(400, "too_many_images", "Tổng số ảnh giữ lại và ảnh mới được tối đa 5.")
            timestamp = utc_timestamp(now())
            if existing and timestamp <= existing["updatedAt"]:
                previous = datetime.fromisoformat(existing["updatedAt"].replace("Z", "+00:00"))
                timestamp = (previous + timedelta(milliseconds=1)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            letter = {"id": existing["id"] if existing else str(uuid.uuid4()), **values,
                      "createdAt": existing["createdAt"] if existing else timestamp, "updatedAt": timestamp,
                      "images": [dict(by_id[image_id]) for image_id in keep] + [metadata for metadata, _ in processed]}
            for order, image in enumerate(letter["images"]):
                image["order"] = order
            created_images = []
            try:
                for metadata, encoded in processed:
                    atomic_write(store.images / metadata["storageKey"], encoded)
                    created_images.append(metadata)
                if existing:
                    data["letters"][data["letters"].index(existing)] = letter
                else:
                    data["letters"].append(letter)
                store.write(data)
            except BaseException:
                store.remove_images(created_images)
                raise
            store.remove_images([image for image in old_images if image["id"] not in keep])
        return jsonify(letter=public_letter(letter)), 200 if existing else 201

    @app.delete("/api/letters/<letter_id>")
    @authenticated
    def delete_letter(letter_id):
        with store.locked():
            data = store.read()
            letter = next((item for item in data["letters"] if item["id"] == letter_id), None)
            if not letter:
                raise ApiError(404, "not_found", "Không tìm thấy bức thư này.")
            data["letters"].remove(letter)
            store.write(data)
            store.remove_images(letter["images"])
        return jsonify(deletedId=letter_id)

    @app.get("/api/images/<image_id>")
    @authenticated
    def read_image(image_id):
        with store.locked():
            data = store.read()
            metadata = next((image for letter in data["letters"] for image in letter["images"] if image["id"] == image_id), None)
            if not metadata:
                raise ApiError(404, "not_found", "Không tìm thấy ảnh đính kèm.")
            path = store.images / metadata["storageKey"]
            if not path.is_file() or path.is_symlink():
                raise ApiError(404, "not_found", "Không tìm thấy ảnh đính kèm.")
            # Open under the lock so a concurrent delete cannot expose or substitute another file.
            stream = path.open("rb")
        try:
            response = send_file(stream, mimetype=metadata["mimeType"], download_name="attachment" + path.suffix, conditional=False, max_age=0)
            response.call_on_close(stream.close)
            return response
        except BaseException:
            stream.close()
            raise

    @app.get("/")
    @app.get("/<path:resource>")
    def public_file(resource="index.html"):
        if any(character in resource for character in ("\\", "\x00", ":")) or any(part in ("..", ".", "") for part in resource.split("/")):
            raise ApiError(404, "not_found", "Không tìm thấy trang.")
        # Keep previously published script/style URLs working after the asset move.
        resource = PUBLIC_ALIASES.get(resource, resource)
        relative = Path(resource)
        allowed = resource in PUBLIC_FILES
        if relative.parts[:2] == ("main", "img"):
            allowed = relative.suffix.lower() in {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico"}
        elif relative.parts[:2] == ("main", "music"):
            allowed = relative.suffix.lower() in {".mp3", ".ogg", ".wav"}
        path = (ROOT / relative).resolve()
        if not allowed or ROOT not in path.parents or not path.is_file():
            raise ApiError(404, "not_found", "Không tìm thấy trang.")
        # Windows installations may not register .ttf in the system MIME database.
        mimetype = "font/ttf" if relative.suffix.lower() == ".ttf" else None
        return send_file(path, mimetype=mimetype, max_age=0)

    return app


def main():
    parser = argparse.ArgumentParser(description="Love Days private letters server")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("init-password", help="Set or replace the private password interactively")
    serve_parser = commands.add_parser("serve", help="Run the Waitress WSGI server")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", default=8001, type=int)
    args = parser.parse_args()
    app = create_app()
    if args.command == "init-password":
        if app.config["PASSWORD_HASH"]:
            parser.error("Remove LOVEDAYS_PASSWORD_HASH before changing the persisted password.")
        password = getpass.getpass("New private password: ")
        confirmation = getpass.getpass("Confirm password: ")
        if not 8 <= len(password) <= 256 or password != confirmation:
            parser.error("Passwords must match and contain 8 to 256 characters.")
        app.extensions["auth_store"].set_password(generate_password_hash(password, method="scrypt:32768:8:3"))
        print("Password saved as a salted scrypt hash. Previous login sessions were revoked.")
        return
    from waitress import serve
    host, port = getattr(args, "host", "127.0.0.1"), getattr(args, "port", 8001)
    print(f"Love Days: http://{host}:{port}")
    print("Private letter storage is outside the public project directory.")
    serve(app, host=host, port=port, threads=4, max_request_body_size=app.config["MAX_CONTENT_LENGTH"], channel_timeout=30)


if __name__ == "__main__":
    main()
