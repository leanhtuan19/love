"""Persistent site settings, encrypted administrator identities and shared journal.

Installed by server.create_app; cookies/CSRF/origin checks reuse its browser layer.
Runtime keys, SQLite and uploads remain outside the public checkout.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import wraps
import getpass
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import unicodedata
from urllib.parse import urlsplit
import uuid

from cryptography.fernet import Fernet, InvalidToken
from filelock import FileLock
from flask import g, jsonify, request, send_file
from itsdangerous import BadSignature
from werkzeug.security import check_password_hash, generate_password_hash

from location_service import install_location, normalize_location


VN = timezone(timedelta(hours=7))
HASH_METHOD = "scrypt:32768:8:3"
USERNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{2,79}$")
DEFAULT_PROFILES = {
    "tuan": {"name": "Lê Anh Tuấn", "displayName": "Anh Tuấn", "partner": "Anh Thư",
             "introduction": "", "birthday": "2007-06-19", "gender": "Nam", "hometown": "Hà Tĩnh",
             "hobbies": "", "avatar": "main/img/avatar-tuan.png"},
    "thu": {"name": "Lê Phạm Anh Thư", "displayName": "Anh Thư", "partner": "Anh Tuấn",
            "introduction": "", "birthday": "2004-01-10", "gender": "Nữ", "hometown": "Hà Tĩnh",
            "hobbies": "", "avatar": "main/img/avatar-thu.jpg"},
}
DEFAULT_CONTENT = {
    "title": "Love Days · Anh Tuấn & Anh Thư", "heading": "LOVE DAYS", "kicker": "Chuyện của chúng mình",
    "introduction": "Thêm một ngày, thêm một chút yêu thương.", "anniversary": "2026-08-14",
    "loveNote": "I love you so much", "heartMessage": "Yêu thương vẫn đong đầy.",
    "heartMessages": ["Thêm một ngày, thêm một chút thương.", "Cảm ơn vì đã luôn ở đây.",
                      "Mãi cùng nhau nhé.", "Yêu thương vẫn đong đầy."],
    "musicTitle": "Giai điệu của\nchúng mình", "musicDescription": "Một bản tình ca. Mãi ngân nga.", "recordLabel": "LOVE DAYS",
    "musicEyebrow": "Our love, on repeat", "musicSrc": "main/music/nhactinhyeu.mp3", "backgroundImage": "",
    "footer": "Mỗi ngày bên nhau đều là một ngày đặc biệt",
    "loaderText": "Đang mở một chút yêu thương…", "loaderCaption": "Mỗi khoảnh khắc đều dành cho nhau",
    "clockLabel": "Chúng mình đã bên nhau", "profileEyebrow": "Về người mình thương",
    "profileNote": "Một phần thật đặc biệt trong câu chuyện của chúng mình.",
}
DEFAULT_SECURITY = {"mailboxIdleSeconds": 300, "mailboxCloseSeconds": 30}


def compact(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def folded(value):
    return "".join(character for character in unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
                   if unicodedata.category(character) != "Mn")


class SiteStore:
    def __init__(self, app, auth, now, signer, core):
        self.app, self.auth, self.now, self.signer, self.core = app, auth, now, signer, core
        self.directory = auth.path.parent
        self.images = self.directory / "journal-images"
        self.images.mkdir(mode=0o700, exist_ok=True)
        with auth.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS feature_migrations(version INTEGER PRIMARY KEY, applied REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS site_settings(group_name TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS admin_accounts(
                    id TEXT PRIMARY KEY, username_cipher TEXT NOT NULL, username_lookup TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL, version TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS admin_sessions(
                    id TEXT PRIMARY KEY, browser_id TEXT NOT NULL, account_id TEXT NOT NULL, version TEXT NOT NULL, expires REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS admin_session_browser ON admin_sessions(browser_id);
                CREATE TABLE IF NOT EXISTS feature_failures(key TEXT PRIMARY KEY, count INTEGER NOT NULL, started REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS journal_posts(id TEXT PRIMARY KEY, data TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS journal_history(
                    id TEXT PRIMARY KEY, post_id TEXT NOT NULL, action TEXT NOT NULL,
                    created_at TEXT NOT NULL, actor TEXT NOT NULL, before_data TEXT NOT NULL, after_data TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS journal_history_post ON journal_history(post_id);
                CREATE TABLE IF NOT EXISTS journal_images(id TEXT PRIMARY KEY, post_id TEXT NOT NULL, metadata TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS journal_grants(id TEXT PRIMARY KEY, browser_id TEXT NOT NULL, version TEXT NOT NULL, expires REAL NOT NULL);
            """)
            for group, value in (("profiles", DEFAULT_PROFILES), ("content", DEFAULT_CONTENT), ("security", DEFAULT_SECURITY)):
                db.execute("INSERT OR IGNORE INTO site_settings VALUES(?,?)", (group, compact(value)))
            db.execute("INSERT OR IGNORE INTO feature_migrations VALUES(1,?)", (now(),))
            # Metadata stays compatible with old images; new attachments may be
            # streamed image/video files in the shared private media directory.
            db.execute("INSERT OR IGNORE INTO feature_migrations VALUES(2,?)", (now(),))
        # Never replace missing encryption keys when there are identities to decrypt.
        # Initialization is serialized across workers; each FileLock is newly constructed.
        with FileLock(str(self.directory / "feature-setup.lock"), timeout=15):
            with auth.connection() as db:
                existing = db.execute("SELECT COUNT(*) FROM admin_accounts").fetchone()[0]
            encryption = self.directory / "admin-encryption.key"
            lookup = self.directory / "admin-lookup.key"
            if existing and (not encryption.is_file() or not lookup.is_file()):
                raise RuntimeError("Administrator key files are missing; restore them from the private backup")
            if not encryption.exists():
                core.atomic_write(encryption, Fernet.generate_key())
            if not lookup.exists():
                core.atomic_write(lookup, secrets.token_bytes(48))
            if encryption.is_symlink() or lookup.is_symlink():
                raise RuntimeError("Administrator key files may not be symlinks")
            self.fernet = Fernet(encryption.read_bytes())
            self.lookup_key = lookup.read_bytes()
            if len(self.lookup_key) < 32:
                raise RuntimeError("Administrator lookup key is invalid")
            if os.name != "nt":
                encryption.chmod(0o600)
                lookup.chmod(0o600)
        # Similar password work for nonexistent accounts; this is never returned.
        self.dummy_hash = generate_password_hash(secrets.token_urlsafe(24), method=HASH_METHOD)

    def group(self, name, db=None):
        if db is None:
            with self.auth.connection() as connection:
                return self.group(name, connection)
        row = db.execute("SELECT value FROM site_settings WHERE group_name=?", (name,)).fetchone()
        if not row:
            raise RuntimeError("Site setting group is missing")
        return json.loads(row[0])

    def lookup(self, username):
        return hmac.new(self.lookup_key, unicodedata.normalize("NFKC", username).casefold().encode("utf-8"), hashlib.sha256).hexdigest()

    def username(self, row):
        try:
            return self.fernet.decrypt(row["username_cipher"].encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, UnicodeError) as error:
            raise RuntimeError("Administrator identity cannot be decrypted; restore matching private keys") from error

    def account(self, row):
        return {"id": row["id"], "username": self.username(row), "updatedAt": row["updated_at"]}

    def cookie(self, name, age):
        try:
            value = self.signer.loads(request.cookies.get(name, ""), max_age=age, salt=name)
            return value if isinstance(value, str) and self.core.OPAQUE_ID.fullmatch(value) else None
        except BadSignature:
            return None

    def failure_keys(self, scope, username=None):
        address = hmac.new(self.lookup_key, (request.remote_addr or "unknown").encode(), hashlib.sha256).hexdigest()
        keys = [scope + ":browser:" + g.browser_id, scope + ":ip:" + address]
        if username:
            keys.append(scope + ":identity:" + self.lookup(username))
        return keys

    def rate(self, db, scope, username=None):
        count, retry = 0, 0
        window, maximum = self.app.config["LOGIN_WINDOW_SECONDS"], self.app.config["MAX_LOGIN_FAILURES"]
        for key in self.failure_keys(scope, username):
            row = db.execute("SELECT * FROM feature_failures WHERE key=?", (key,)).fetchone()
            if row and row["started"] + window > self.now():
                count = max(count, row["count"])
                if row["count"] >= maximum:
                    retry = max(retry, math.ceil(row["started"] + window - self.now()))
        return max(0, maximum - count), retry

    def check_rate(self, db, scope, username=None):
        remaining, retry = self.rate(db, scope, username)
        if retry:
            raise self.core.ApiError(429, "rate_limited", "Đã thử sai quá nhiều lần. Vui lòng đợi rồi thử lại.", retryAfter=retry, attemptsRemaining=remaining)

    def failure(self, db, scope, username=None):
        timestamp, window = self.now(), self.app.config["LOGIN_WINDOW_SECONDS"]
        for key in self.failure_keys(scope, username):
            row = db.execute("SELECT * FROM feature_failures WHERE key=?", (key,)).fetchone()
            fresh = not row or row["started"] + window <= timestamp
            db.execute("INSERT INTO feature_failures VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET count=excluded.count,started=excluded.started",
                       (key, 1 if fresh else row["count"] + 1, timestamp if fresh else row["started"]))
        remaining, retry = self.rate(db, scope, username)
        # A rejected password must not roll its durable attempt counter back.
        db.commit()
        raise self.core.ApiError(429 if retry else 401, "rate_limited" if retry else "incorrect_password",
                                 "Đã thử sai quá nhiều lần. Vui lòng đợi rồi thử lại." if retry else "Thông tin xác thực chưa đúng.",
                                 retryAfter=retry, attemptsRemaining=remaining)

    def clear_failures(self, db, scope, username=None):
        for key in self.failure_keys(scope, username):
            db.execute("DELETE FROM feature_failures WHERE key=?", (key,))

    def journal_hash(self, db):
        row = db.execute("SELECT value FROM settings WHERE key='journal_password_hash'").fetchone()
        return row[0] if row else None

    def verify_journal(self, db, password):
        self.check_rate(db, "journal")
        hashed = self.journal_hash(db)
        if not hashed:
            raise self.core.ApiError(409, "journal_password_required", "Quản trị viên cần thiết lập mật khẩu nhật ký trong Cài đặt.")
        if not self.core.valid_text(password, 256) or not check_password_hash(hashed, password):
            self.failure(db, "journal")
        self.clear_failures(db, "journal")

    def settings(self, db):
        return {"profiles": self.group("profiles", db), "content": self.group("content", db),
                "security": {**self.group("security", db), "mailboxPasswordConfigured": bool(self.auth.password_hash(db)),
                             "journalPasswordConfigured": bool(self.journal_hash(db))}}


def migrate(app):
    """create_app installs all idempotent feature migrations before serving requests."""
    return app.extensions["site_features"]


def setup_admins(app):
    """First-run-only setup. Never reset existing identities on redeploy."""
    store = migrate(app)
    with store.auth.connection() as db:
        if db.execute("SELECT COUNT(*) FROM admin_accounts").fetchone()[0]:
            print("Administrator accounts already exist; setup left them unchanged.")
            return False
    accounts = []
    for number in (1, 2):
        username = os.environ.get(f"LOVEDAYS_ADMIN_{number}_USERNAME")
        password = os.environ.get(f"LOVEDAYS_ADMIN_{number}_PASSWORD")
        if username is None and password is None:
            username = input(f"Administrator {number} username: ").strip()
            password = getpass.getpass(f"Administrator {number} password: ")
            confirmation = getpass.getpass("Confirm password: ")
            if password != confirmation:
                raise ValueError("Administrator passwords do not match")
        if not isinstance(username, str) or not USERNAME.fullmatch(username) or not isinstance(password, str) or not 8 <= len(password) <= 256 or "\x00" in password:
            raise ValueError("Provide a 3-80 character username and an 8-256 character password for each administrator")
        accounts.append((username, password))
    if store.lookup(accounts[0][0]) == store.lookup(accounts[1][0]):
        raise ValueError("Administrator usernames must be different")
    timestamp = store.core.utc_timestamp(store.now())
    with store.auth.transaction() as db:
        # Recheck under the write transaction: two simultaneous setups cannot reset users.
        if db.execute("SELECT COUNT(*) FROM admin_accounts").fetchone()[0]:
            print("Administrator accounts already exist; setup left them unchanged.")
            return False
        for username, password in accounts:
            db.execute("INSERT INTO admin_accounts VALUES(?,?,?,?,?,?,?)",
                       (str(uuid.uuid4()), store.fernet.encrypt(username.encode()).decode("ascii"), store.lookup(username),
                        generate_password_hash(password, method=HASH_METHOD), uuid.uuid4().hex, timestamp, timestamp))
    print("Two administrator accounts initialized. Credentials were not written to source files.")
    return True


def install_features(app, auth, now, signer, core):
    store = SiteStore(app, auth, now, signer, core)
    app.extensions["site_features"] = store
    app.extensions["site_settings_reader"] = lambda: store.group("security")
    install_location(app, store, core)
    admin_ttl, grant_ttl = 3600, 300

    @app.before_request
    def feature_sessions():
        if not request.path.startswith("/api/"):
            return
        g.admin_account, g.history_allowed = None, False
        g.new_admin_session, g.new_history_grant = None, None
        g.clear_admin_session, g.clear_history_grant = False, False
        with auth.transaction() as db:
            session_id = store.cookie("lovedays_admin", admin_ttl)
            record = db.execute("SELECT a.*,s.expires,s.browser_id,s.version AS session_version FROM admin_sessions s JOIN admin_accounts a ON a.id=s.account_id WHERE s.id=?", (session_id,)).fetchone() if session_id else None
            if record and record["browser_id"] == g.browser_id and record["version"] == record["session_version"] and record["expires"] > now():
                g.admin_account = record
            elif request.cookies.get("lovedays_admin"):
                g.clear_admin_session = True
            grant_id = store.cookie("lovedays_journal", grant_ttl)
            grant = db.execute("SELECT * FROM journal_grants WHERE id=?", (grant_id,)).fetchone() if grant_id else None
            hashed = store.journal_hash(db)
            if grant and hashed and grant["browser_id"] == g.browser_id and grant["expires"] > now() and grant["version"] == hashlib.sha256(hashed.encode()).hexdigest():
                g.history_allowed = True
            elif request.cookies.get("lovedays_journal"):
                g.clear_history_grant = True
            db.execute("DELETE FROM admin_sessions WHERE expires<=?", (now(),))
            db.execute("DELETE FROM journal_grants WHERE expires<=?", (now(),))
            db.execute("DELETE FROM feature_failures WHERE started<=?", (now() - app.config["LOGIN_WINDOW_SECONDS"],))

    @app.after_request
    def feature_cookies(response):
        if not request.path.startswith("/api/"):
            return response
        for name, fresh, clear, ttl in (("lovedays_admin", getattr(g, "new_admin_session", None), getattr(g, "clear_admin_session", False), admin_ttl),
                                        ("lovedays_journal", getattr(g, "new_history_grant", None), getattr(g, "clear_history_grant", False), grant_ttl)):
            options = dict(httponly=True, secure=app.config["COOKIE_SECURE"], samesite="Strict", path="/")
            if fresh:
                response.set_cookie(name, signer.dumps(fresh, salt=name), max_age=ttl, **options)
            elif clear:
                response.delete_cookie(name, **options)
        return response

    def require_admin(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not g.admin_account:
                raise core.ApiError(401, "admin_required", "Vui lòng đăng nhập quản trị để mở Cài đặt.")
            return view(*args, **kwargs)
        return wrapped

    def json_body():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise core.ApiError(400, "invalid_payload", "Dữ liệu gửi lên chưa hợp lệ.")
        return body

    def admin_payload(db):
        remaining, retry = store.rate(db, "admin")
        return {"authenticated": bool(g.admin_account), "csrfToken": g.csrf,
                "configured": bool(db.execute("SELECT 1 FROM admin_accounts LIMIT 1").fetchone()),
                "account": store.account(g.admin_account) if g.admin_account else None,
                "attemptsRemaining": remaining, "retryAfter": retry}

    @app.get("/api/site")
    def site_public():
        with auth.connection() as db:
            return jsonify(profiles=store.group("profiles", db), content=store.group("content", db), limits=core.LIMITS)

    @app.get("/api/admin/session")
    def admin_session():
        with auth.connection() as db:
            return jsonify(admin_payload(db))

    @app.post("/api/admin/login")
    def admin_login():
        request.max_content_length = 4096
        body = json_body()
        username, password = body.get("username"), body.get("password")
        if not isinstance(username, str) or not USERNAME.fullmatch(username) or not core.valid_text(password, 256):
            raise core.ApiError(400, "invalid_credentials", "Vui lòng nhập tên đăng nhập và mật khẩu hợp lệ.")
        with auth.transaction() as db:
            store.check_rate(db, "admin", username)
            record = db.execute("SELECT * FROM admin_accounts WHERE username_lookup=?", (store.lookup(username),)).fetchone()
            if not check_password_hash(record["password_hash"] if record else store.dummy_hash, password) or not record:
                store.failure(db, "admin", username)
            store.clear_failures(db, "admin", username)
            db.execute("DELETE FROM admin_sessions WHERE browser_id=?", (g.browser_id,))
            g.new_admin_session = secrets.token_urlsafe(32)
            db.execute("INSERT INTO admin_sessions VALUES(?,?,?,?,?)", (g.new_admin_session, g.browser_id, record["id"], record["version"], now() + admin_ttl))
            g.admin_account = record
            return jsonify(admin_payload(db))

    @app.post("/api/admin/logout")
    def admin_logout():
        with auth.transaction() as db:
            db.execute("DELETE FROM admin_sessions WHERE browser_id=?", (g.browser_id,))
            g.admin_account, g.clear_admin_session = None, True
            return jsonify(admin_payload(db))

    @app.get("/api/admin/settings")
    @require_admin
    def get_settings():
        with auth.connection() as db:
            return jsonify(store.settings(db))

    def text(value, maximum, allow_empty=False):
        if not isinstance(value, str) or len(value) > maximum or "\x00" in value or (not allow_empty and not core.valid_text(value, maximum)):
            raise core.ApiError(400, "invalid_setting", "Giá trị cài đặt còn trống hoặc vượt giới hạn cho phép.")
        try:
            value.encode("utf-8")
        except UnicodeError:
            raise core.ApiError(400, "invalid_setting", "Văn bản phải dùng Unicode hợp lệ.")
        return value.strip()

    def date_value(value):
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise core.ApiError(400, "invalid_date", "Ngày cần có định dạng năm-tháng-ngày.")
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            raise core.ApiError(400, "invalid_date", "Ngày đã nhập không tồn tại.")

    def asset(value, kind="image", allow_empty=False):
        value = text(value, 1000, allow_empty)
        if not value and allow_empty:
            return value
        parsed = urlsplit(value)
        if kind == "image" and parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
            return value
        prefix = "/main/img/" if kind == "image" else "/main/music/"
        path = "/" + value.lstrip("/")
        suffixes = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"} if kind == "image" else {".mp3", ".ogg", ".wav"}
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or not path.startswith(prefix) or "\\" in path or "%" in path or any(part in (".", "..", "") for part in path[1:].split("/")) or Path(path).suffix.lower() not in suffixes:
            raise core.ApiError(400, "invalid_asset", "Dùng ảnh HTTPS hoặc tài nguyên phù hợp trong thư mục main của website.")
        return value

    def password_change(body, field, confirm):
        if not body.get(field):
            if body.get(confirm):
                raise core.ApiError(400, "password_mismatch", "Vui lòng nhập mật khẩu mới ở cả hai ô.")
            return None
        value = body[field]
        if not core.valid_text(value, 256) or len(value) < 8 or value != body.get(confirm):
            raise core.ApiError(400, "password_mismatch", "Mật khẩu mới cần từ 8 đến 256 ký tự và hai ô phải giống nhau.")
        return generate_password_hash(value, method=HASH_METHOD)

    @app.put("/api/admin/settings/<group>")
    @require_admin
    def put_settings(group):
        request.max_content_length = 128 * 1024
        body = json_body()
        if group not in ("profiles", "content", "security"):
            raise core.ApiError(404, "not_found", "Không tìm thấy nhóm cài đặt.")
        with auth.transaction() as db:
            current = store.group(group, db)
            if group == "profiles":
                if set(body) - set(DEFAULT_PROFILES):
                    raise core.ApiError(400, "invalid_setting", "Hồ sơ không hợp lệ.")
                allowed = set(next(iter(DEFAULT_PROFILES.values())))
                for person_id, changes in body.items():
                    if not isinstance(changes, dict) or set(changes) - allowed:
                        raise core.ApiError(400, "invalid_setting", "Trường thông tin cá nhân không hợp lệ.")
                    for key, value in changes.items():
                        if key == "birthday":
                            date_value(value)
                        elif key == "avatar":
                            value = asset(value)
                        else:
                            value = text(value, 1000 if key in ("introduction", "hobbies") else 80,
                                         key in ("introduction", "hobbies", "gender", "hometown", "partner"))
                        current[person_id][key] = value
            elif group == "content":
                if set(body) - set(DEFAULT_CONTENT):
                    raise core.ApiError(400, "invalid_setting", "Trường nội dung không hợp lệ.")
                for key, value in body.items():
                    if key == "anniversary":
                        date_value(value)
                    elif key == "heartMessages":
                        if not isinstance(value, list) or not 1 <= len(value) <= 30:
                            raise core.ApiError(400, "invalid_setting", "Cần từ 1 đến 30 lời nhắn trái tim.")
                        value = [text(item, 400) for item in value]
                    elif key in ("backgroundImage", "musicSrc"):
                        value = asset(value, "audio" if key == "musicSrc" else "image", key == "backgroundImage")
                    else:
                        value = text(value, 2000)
                    current[key] = value
            else:
                allowed = {"mailboxIdleSeconds", "mailboxCloseSeconds", "newMailboxPassword", "confirmMailboxPassword", "newJournalPassword", "confirmJournalPassword"}
                if set(body) - allowed:
                    raise core.ApiError(400, "invalid_setting", "Trường bảo mật không hợp lệ.")
                for key, low, high in (("mailboxIdleSeconds", 30, 86400), ("mailboxCloseSeconds", 0, 3600)):
                    if key in body:
                        value = body[key]
                        if type(value) is not int or not low <= value <= high:
                            raise core.ApiError(400, "invalid_setting", "Thời gian tự khóa nằm ngoài giới hạn cho phép.")
                        current[key] = value
                mailbox_hash = password_change(body, "newMailboxPassword", "confirmMailboxPassword")
                journal_hash = password_change(body, "newJournalPassword", "confirmJournalPassword")
                if mailbox_hash:
                    if auth.override_hash:
                        raise core.ApiError(409, "environment_password_override", "Máy chủ đang đặt mật khẩu qua biến môi trường. Hãy gỡ giá trị override trước khi đổi trong Cài đặt.")
                    db.execute("INSERT INTO settings VALUES('password_hash',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (mailbox_hash,))
                    db.execute("DELETE FROM sessions")
                    g.authenticated, g.clear_session = False, True
                if journal_hash:
                    db.execute("INSERT INTO settings VALUES('journal_password_hash',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (journal_hash,))
                    db.execute("DELETE FROM journal_grants")
                    g.history_allowed, g.clear_history_grant = False, True
            db.execute("UPDATE site_settings SET value=? WHERE group_name=?", (compact(current), group))
            return jsonify(store.settings(db))

    @app.get("/api/admin/accounts")
    @require_admin
    def get_accounts():
        with auth.connection() as db:
            return jsonify(accounts=[store.account(row) for row in db.execute("SELECT * FROM admin_accounts ORDER BY created_at,id")])

    @app.put("/api/admin/accounts/<account_id>")
    @require_admin
    def put_account(account_id):
        request.max_content_length = 4096
        body = json_body()
        if set(body) - {"currentPassword", "username", "newPassword", "confirmPassword"}:
            raise core.ApiError(400, "invalid_account", "Trường tài khoản không hợp lệ.")
        with auth.transaction() as db:
            store.check_rate(db, "admin-current")
            # Reauthentication always concerns the account performing the action.
            actor = db.execute("SELECT * FROM admin_accounts WHERE id=?", (g.admin_account["id"],)).fetchone()
            if not core.valid_text(body.get("currentPassword"), 256) or not check_password_hash(actor["password_hash"], body["currentPassword"]):
                store.failure(db, "admin-current")
            store.clear_failures(db, "admin-current")
            target = db.execute("SELECT * FROM admin_accounts WHERE id=?", (account_id,)).fetchone()
            if not target:
                raise core.ApiError(404, "not_found", "Không tìm thấy tài khoản quản trị.")
            username = body.get("username", store.username(target))
            if not isinstance(username, str) or not USERNAME.fullmatch(username):
                raise core.ApiError(400, "invalid_username", "Tên đăng nhập cần 3-80 ký tự gồm chữ, số, dấu chấm, gạch dưới, @ hoặc gạch ngang.")
            duplicate = db.execute("SELECT id FROM admin_accounts WHERE username_lookup=? AND id<>?", (store.lookup(username), account_id)).fetchone()
            if duplicate:
                raise core.ApiError(409, "username_exists", "Tên đăng nhập này đã được sử dụng.")
            hashed = password_change(body, "newPassword", "confirmPassword") or target["password_hash"]
            timestamp = core.utc_timestamp(now())
            db.execute("UPDATE admin_accounts SET username_cipher=?,username_lookup=?,password_hash=?,version=?,updated_at=? WHERE id=?",
                       (store.fernet.encrypt(username.encode()).decode("ascii"), store.lookup(username), hashed, uuid.uuid4().hex, timestamp, account_id))
            db.execute("DELETE FROM admin_sessions WHERE account_id=?", (account_id,))
            changed = db.execute("SELECT * FROM admin_accounts WHERE id=?", (account_id,)).fetchone()
            own = account_id == actor["id"]
            if own:
                g.admin_account, g.clear_admin_session = None, True
            return jsonify(account=store.account(changed), reauthenticate=own)

    def public_post(post):
        result = deepcopy(post)
        for image in result["images"]:
            image.pop("storageKey", None)
            image.pop("storageArea", None)
            image.setdefault("kind", "image")
            image["url"] = "/api/journal/images/" + image["id"]
        return result

    def public_history(row):
        return {"id": row["id"], "postId": row["post_id"], "action": row["action"], "createdAt": row["created_at"],
                "actor": json.loads(row["actor"]), "before": public_post(json.loads(row["before_data"])),
                "after": public_post(json.loads(row["after_data"]))}

    def pagination():
        try:
            page, size = int(request.args.get("page", 1)), int(request.args.get("pageSize", 9))
            if page < 1 or not 1 <= size <= 30 or page > 1000000:
                raise ValueError
            return page, size
        except ValueError:
            raise core.ApiError(400, "invalid_pagination", "Trang và số bài mỗi trang chưa hợp lệ.")

    @app.get("/api/journal")
    def list_posts():
        page, size = pagination()
        query = request.args.get("q", "").strip()
        if len(query) > 200:
            raise core.ApiError(400, "invalid_search", "Từ khóa tìm kiếm tối đa 200 ký tự.")
        lower = date_value(request.args["from"]) if request.args.get("from") else None
        upper = date_value(request.args["to"]) if request.args.get("to") else None
        if lower and upper and lower > upper:
            raise core.ApiError(400, "invalid_date_range", "Ngày bắt đầu cần trước hoặc bằng ngày kết thúc.")
        query_date = None
        for pattern in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                query_date = datetime.strptime(query, pattern).date()
                break
            except ValueError:
                pass
        with auth.connection() as db:
            posts = [json.loads(row[0]) for row in db.execute("SELECT data FROM journal_posts WHERE deleted=0")]
            configured = bool(store.journal_hash(db))
        found = []
        for post in posts:
            day = datetime.fromisoformat(post["createdAt"].replace("Z", "+00:00")).astimezone(VN).date()
            if (lower and day < lower) or (upper and day > upper):
                continue
            haystack = " ".join(str(post[field]) for field in ("id", "authorName", "title", "content")) + " " + post["location"]["label"]
            if query and not (query_date == day if query_date else folded(query) in folded(haystack)):
                continue
            found.append(post)
        found.sort(key=lambda post: (post["createdAt"], post["id"]), reverse=True)
        offset, total = (page - 1) * size, len(found)
        return jsonify(posts=[public_post(post) for post in found[offset:offset + size]], total=total, page=page, pageSize=size,
                       hasMore=offset + size < total, canPost=bool(g.authenticated or g.admin_account),
                       canViewHistory=bool(g.admin_account or g.history_allowed), journalPasswordConfigured=configured)

    @app.get("/api/journal/<post_id>")
    def get_post(post_id):
        with auth.connection() as db:
            row = db.execute("SELECT data FROM journal_posts WHERE id=? AND deleted=0", (post_id,)).fetchone()
        if not row:
            raise core.ApiError(404, "not_found", "Bài đăng không còn tồn tại hoặc đã bị xóa.")
        return jsonify(post=public_post(json.loads(row[0])))

    def parse_post():
        if request.mimetype == "multipart/form-data":
            try:
                body = json.loads(request.form.get("payload", ""), object_pairs_hook=core.json_without_duplicates)
            except (ValueError, TypeError):
                raise core.ApiError(400, "invalid_payload", "Nội dung bài đăng không hợp lệ.")
            if set(request.files) - {"images"}:
                raise core.ApiError(400, "invalid_images", "Trường tải ảnh không hợp lệ.")
            uploads = [upload for upload in request.files.getlist("images") if upload.filename]
        elif request.is_json:
            body, uploads = json_body(), []
        else:
            raise core.ApiError(415, "unsupported_content", "Vui lòng gửi JSON hoặc biểu mẫu tải ảnh.")
        if not isinstance(body, dict):
            raise core.ApiError(400, "invalid_payload", "Nội dung bài đăng không hợp lệ.")
        values = {}
        for key, maximum in (("authorName", 80), ("title", 160), ("content", 20000)):
            if not core.valid_text(body.get(key), maximum) or (key != "content" and any(character in body[key] for character in "\r\n")):
                raise core.ApiError(400, "invalid_post", "Vui lòng kiểm tra tên người đăng, tiêu đề và nội dung.")
            values[key] = body[key] if key == "content" else body[key].strip()
        values["location"] = normalize_location(body.get("location", {"label": ""}), core)
        keep = body.get("keepImageIds")
        if keep is not None and (not isinstance(keep, list) or any(not core.canonical_uuid(value) for value in keep) or len(set(keep)) != len(keep)):
            raise core.ApiError(400, "invalid_images", "Danh sách ảnh giữ lại không hợp lệ.")
        upload_ids = body.get("uploadIds", [])
        if not isinstance(upload_ids, list) or any(not core.canonical_uuid(value) for value in upload_ids) or len(set(upload_ids)) != len(upload_ids):
            raise core.ApiError(400, "invalid_media", "Danh sách tệp đính kèm chưa hợp lệ.")
        expected = body.get("expectedUpdatedAt")
        if expected is not None and (not isinstance(expected, str) or len(expected) > 40):
            raise core.ApiError(400, "invalid_payload", "Mốc cập nhật không hợp lệ.")
        return body, values, keep, uploads, upload_ids, expected

    def actor():
        if g.admin_account:
            return {"type": "admin", "id": g.admin_account["id"]}
        if g.authenticated:
            return {"type": "mailbox", "id": hmac.new(store.lookup_key, g.browser_id.encode(), hashlib.sha256).hexdigest()[:24]}
        return {"type": "journal-password", "id": hmac.new(store.lookup_key, g.browser_id.encode(), hashlib.sha256).hexdigest()[:24]}

    def advance(previous=None):
        timestamp = core.utc_timestamp(now())
        if previous and timestamp <= previous:
            timestamp = (datetime.fromisoformat(previous.replace("Z", "+00:00")) + timedelta(milliseconds=1)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        return timestamp

    def history(db, before, after, action):
        db.execute("INSERT INTO journal_history VALUES(?,?,?,?,?,?,?)", (str(uuid.uuid4()), before["id"], action, after["updatedAt"], compact(actor()), compact(before), compact(after)))

    @app.post("/api/journal")
    @app.put("/api/journal/<post_id>")
    def save_post(post_id=None):
        if not post_id and not (g.authenticated or g.admin_account):
            raise core.ApiError(401, "posting_auth_required", "Mở khóa hòm thư hoặc đăng nhập quản trị trước khi đăng bài.")
        body, values, keep, uploads, upload_ids, expected = parse_post()
        created = []
        processed = []
        try:
            with auth.transaction() as db:
                if post_id:
                    store.verify_journal(db, body.get("password"))
                row = db.execute("SELECT data FROM journal_posts WHERE id=? AND deleted=0", (post_id,)).fetchone() if post_id else None
                if post_id and not row:
                    raise core.ApiError(404, "not_found", "Bài đăng không còn tồn tại hoặc đã bị xóa.")
                before = json.loads(row[0]) if row else None
                if before and expected is not None and expected != before["updatedAt"]:
                    raise core.ApiError(409, "edit_conflict", "Bài đã được sửa ở nơi khác. Bản nháp vẫn được giữ; tải lại bài trước khi lưu.")
                old = {image["id"]: image for image in before["images"]} if before else {}
                keep = list(old) if keep is None else keep
                if any(image_id not in old for image_id in keep):
                    raise core.ApiError(400, "invalid_images", "Tệp giữ lại phải thuộc bài đang sửa.")
                for upload in uploads:
                    processed.append(core.sanitize_upload(upload, values["title"]))
                media = app.extensions.get("media_uploads")
                completed = media.resolve_uploads(upload_ids, "journal", db=db) if upload_ids else []
                timestamp = advance(before["updatedAt"] if before else None)
                post = {"id": post_id or str(uuid.uuid4()), **values, "createdAt": before["createdAt"] if before else timestamp,
                        "updatedAt": timestamp, "deletedAt": None,
                        "images": [deepcopy(old[image_id]) for image_id in keep] + [metadata for metadata, _ in processed] + completed}
                for order, image in enumerate(post["images"]):
                    image["order"] = order
                for metadata, encoded in processed:
                    core.write_attachment(store.images / metadata["storageKey"], encoded)
                    created.append(metadata["storageKey"])
                    db.execute("INSERT INTO journal_images VALUES(?,?,?)", (metadata["id"], post["id"], compact(metadata)))
                for metadata in completed:
                    db.execute("INSERT INTO journal_images VALUES(?,?,?)", (metadata["id"], post["id"], compact(metadata)))
                if upload_ids:
                    media.claim_uploads(upload_ids, "journal", post["id"], db=db)
                db.execute("INSERT INTO journal_posts VALUES(?,?,0) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (post["id"], compact(post)))
                if before:
                    history(db, before, post, "edit")
        except BaseException:
            for key in created:
                (store.images / key).unlink(missing_ok=True)
            raise
        finally:
            core.discard_uploads(processed)
        return jsonify(post=public_post(post)), 200 if post_id else 201

    @app.delete("/api/journal/<post_id>")
    def delete_post(post_id):
        request.max_content_length = 4096
        body = json_body()
        with auth.transaction() as db:
            store.verify_journal(db, body.get("password"))
            row = db.execute("SELECT data FROM journal_posts WHERE id=? AND deleted=0", (post_id,)).fetchone()
            if not row:
                raise core.ApiError(404, "not_found", "Bài đăng không còn tồn tại hoặc đã bị xóa.")
            before = json.loads(row[0])
            after = deepcopy(before)
            after["updatedAt"] = after["deletedAt"] = advance(before["updatedAt"])
            db.execute("UPDATE journal_posts SET data=?,deleted=1 WHERE id=?", (compact(after), post_id))
            history(db, before, after, "delete")
        return jsonify(deletedId=post_id)

    @app.post("/api/journal/history/unlock")
    def unlock_history():
        request.max_content_length = 4096
        body = json_body()
        with auth.transaction() as db:
            store.verify_journal(db, body.get("password"))
            db.execute("DELETE FROM journal_grants WHERE browser_id=?", (g.browser_id,))
            g.new_history_grant = secrets.token_urlsafe(32)
            db.execute("INSERT INTO journal_grants VALUES(?,?,?,?)", (g.new_history_grant, g.browser_id, hashlib.sha256(store.journal_hash(db).encode()).hexdigest(), now() + grant_ttl))
        return jsonify(authenticated=True, expiresAt=core.utc_timestamp(now() + grant_ttl))

    @app.get("/api/journal/history")
    def list_history():
        if not (g.admin_account or g.history_allowed):
            raise core.ApiError(401, "history_auth_required", "Đăng nhập quản trị hoặc nhập mật khẩu nhật ký để xem lịch sử.")
        page, size = pagination()
        post_id = request.args.get("postId")
        where, parameters = (" WHERE post_id=?", (post_id,)) if post_id else ("", ())
        with auth.connection() as db:
            total = db.execute("SELECT COUNT(*) FROM journal_history" + where, parameters).fetchone()[0]
            rows = db.execute("SELECT * FROM journal_history" + where + " ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?", parameters + (size, (page - 1) * size)).fetchall()
        return jsonify(entries=[public_history(row) for row in rows], total=total, page=page, pageSize=size, hasMore=page * size < total)

    @app.get("/api/journal/images/<image_id>")
    def journal_image(image_id):
        with auth.connection() as db:
            row = db.execute("SELECT i.metadata,p.data,p.deleted FROM journal_images i JOIN journal_posts p ON p.id=i.post_id WHERE i.id=?", (image_id,)).fetchone()
            if not row:
                raise core.ApiError(404, "not_found", "Không tìm thấy ảnh nhật ký.")
            public = not row["deleted"] and any(image["id"] == image_id for image in json.loads(row["data"])["images"])
            if not public and not (g.admin_account or g.history_allowed):
                raise core.ApiError(401, "history_auth_required", "Ảnh chỉ còn trong lịch sử riêng tư. Vui lòng xác thực lại.")
            metadata = json.loads(row["metadata"])
            if metadata.get("storageArea") == "media":
                path = app.extensions["media_uploads"].path(metadata)
            else:
                path = store.images / metadata["storageKey"]
                if not core.STORAGE_KEY.fullmatch(metadata["storageKey"]) or not path.is_file() or path.is_symlink():
                    raise core.ApiError(404, "not_found", "Không tìm thấy tệp nhật ký.")
        # Passing a path permits conditional/Range responses for mobile video
        # without buffering the complete attachment in the application process.
        return send_file(path, mimetype=metadata["mimeType"], download_name="memory" + path.suffix, conditional=True, max_age=0)

    return store
