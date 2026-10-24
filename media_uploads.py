"""Durable, browser-owned resumable media uploads outside the public checkout.

The chunk size is a transport bound, never a bound on attachment size/count.
Completed uploads stay private until an authenticated save claims their IDs.
"""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
import errno
import json
import math
import os
from pathlib import Path
import struct
import uuid

from filelock import FileLock, Timeout
from flask import g, has_request_context, jsonify, request
from PIL import Image, UnidentifiedImageError
from werkzeug.exceptions import ClientDisconnected


CHUNK_BYTES = 1024 * 1024
FORMATS = {"JPEG": ("image/jpeg", ".jpg"), "PNG": ("image/png", ".png"),
           "WEBP": ("image/webp", ".webp")}
TYPES = {"image/jpeg", "image/png", "image/webp", "video/mp4", "video/webm"}


def safe_filename(value):
    if not isinstance(value, str):
        return ""
    value = (value or "").replace("\\", "/").rsplit("/", 1)[-1]
    return "".join(character for character in value if character.isprintable()).strip()[:180]


def disk_error(error, core):
    if error.errno in {errno.ENOSPC, getattr(errno, "EDQUOT", -1)}:
        raise core.ApiError(507, "storage_full", "Máy chủ đã hết dung lượng lưu trữ. Các tệp đã tải thành công vẫn được giữ; hãy giải phóng dung lượng hoặc nâng cấp kho lưu trữ rồi thử lại.") from error
    raise error


def _mp4(path):
    """Walk ISO-BMFF boxes with seeks, including a video handler and sample data."""
    total = path.stat().st_size
    found = {"ftyp": False, "video": False, "mdat": False, "moov": False}
    brands = {b"isom", b"iso2", b"iso3", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1", b"dash", b"M4V ", b"MSNV"}
    with path.open("rb") as stream:
        def boxes(start, end, depth=0):
            if depth > 12:
                raise ValueError("Invalid MP4 nesting")
            offset = start
            while offset < end:
                if end - offset < 8:
                    raise ValueError("Truncated MP4 box")
                stream.seek(offset)
                size, kind = struct.unpack(">I4s", stream.read(8))
                header = 8
                if size == 1:
                    if end - offset < 16:
                        raise ValueError("Truncated MP4 size")
                    size, header = struct.unpack(">Q", stream.read(8))[0], 16
                elif size == 0:
                    size = end - offset
                if size < header or offset + size > end:
                    raise ValueError("Invalid MP4 box extent")
                payload = offset + header
                if kind == b"ftyp" and depth == 0:
                    if size - header < 8 or (size - header) % 4:
                        raise ValueError("Invalid MP4 brands")
                    major = stream.read(4)
                    stream.read(4)
                    compatible = major in brands
                    remaining = size - header - 8
                    while remaining and not compatible:
                        block = stream.read(min(remaining, 4096))
                        compatible = any(block[index:index + 4] in brands for index in range(0, len(block), 4))
                        remaining -= len(block)
                    found["ftyp"] = compatible
                elif kind == b"mdat" and depth == 0:
                    found["mdat"] = size > header
                elif kind == b"hdlr" and size - header >= 12:
                    stream.seek(payload + 8)
                    found["video"] |= stream.read(4) == b"vide"
                if kind in {b"moov", b"trak", b"mdia", b"minf", b"stbl"}:
                    found["moov"] |= kind == b"moov"
                    boxes(payload, offset + size, depth + 1)
                offset += size
        boxes(0, total)
    if not all(found.values()):
        raise ValueError("MP4 needs brands, movie metadata, video track and media data")


def _vint(stream, keep_marker=False):
    first = stream.read(1)
    if not first or first == b"\0":
        raise ValueError("Invalid EBML integer")
    first = first[0]
    length = 1
    marker = 128
    while not first & marker:
        length += 1
        marker >>= 1
    tail = stream.read(length - 1)
    if len(tail) != length - 1:
        raise ValueError("Truncated EBML integer")
    value = int.from_bytes(bytes([first if keep_marker else first & (marker - 1)]) + tail, "big")
    unknown = not keep_marker and value == (1 << (7 * length)) - 1
    return value, unknown


def _webm(path):
    total = path.stat().st_size
    found = {"header": False, "doctype": False, "segment": False, "video": False, "codec": False, "block": False}
    containers = {0x1A45DFA3, 0x18538067, 0x1654AE6B, 0xAE, 0x1F43B675, 0xA0}
    with path.open("rb") as stream:
        def elements(start, end, depth=0, parent=None, parent_unknown=False):
            if depth > 12:
                raise ValueError("Invalid WebM nesting")
            offset = start
            while offset < end:
                stream.seek(offset)
                kind, _ = _vint(stream, True)
                if parent == 0x1F43B675 and parent_unknown and kind in {
                        0x1F43B675, 0x1549A966, 0x1654AE6B, 0x1C53BB6B,
                        0x114D9B74, 0x1941A469, 0x1043A770, 0x1254C367}:
                    # A new Segment child terminates an unknown-size Cluster;
                    # it is a sibling, not a recursively nested Cluster.
                    return offset
                size, unknown = _vint(stream)
                payload = stream.tell()
                stop = end if unknown else payload + size
                if stop > end or stop < payload or unknown and kind not in {0x18538067, 0x1F43B675}:
                    raise ValueError("Invalid WebM element extent")
                if kind == 0x1A45DFA3 and depth == 0:
                    found["header"] = True
                elif kind == 0x4282 and size <= 32:
                    found["doctype"] = stream.read(size).lower() == b"webm"
                elif kind == 0x18538067 and depth == 0:
                    found["segment"] = True
                elif kind == 0x83 and 0 < size <= 8:
                    found["video"] |= int.from_bytes(stream.read(size), "big") == 1
                elif kind == 0x86 and size <= 64:
                    found["codec"] |= stream.read(size) in {b"V_VP8", b"V_VP9", b"V_AV1"}
                elif kind in {0xA3, 0xA1}:
                    found["block"] |= size >= 5
                if kind in containers:
                    consumed = elements(payload, stop, depth + 1, kind, unknown)
                    if unknown:
                        stop = consumed
                offset = stop
            return offset
        elements(0, total)
    if not all(found.values()):
        raise ValueError("WebM needs an EBML header, WebM type, video track and block")


def inspect_media(path, filename, declared_type, core):
    """Verify actual container/image structure without transcoding original bytes."""
    suffix = Path(filename).suffix.lower()
    try:
        with path.open("rb") as stream:
            signature = stream.read(16)
        if signature.startswith(b"\x1aE\xdf\xa3"):
            _webm(path)
            mime, extension, kind = "video/webm", ".webm", "video"
            details = {}
        elif len(signature) >= 8 and signature[4:8] == b"ftyp":
            _mp4(path)
            mime, extension, kind = "video/mp4", ".mp4", "video"
            details = {}
        else:
            with Image.open(path, formats=tuple(FORMATS)) as image:
                mime, extension = FORMATS[image.format]
                details = {"width": image.width, "height": image.height}
                image.verify()
            kind = "image"
        allowed = {".jpg", ".jpeg"} if mime == "image/jpeg" else {extension}
        if suffix not in allowed or declared_type not in {mime, "application/octet-stream", ""}:
            raise ValueError("Filename/type disagrees with the actual media")
        return {"mimeType": mime, "kind": kind, **details}, extension
    except (UnidentifiedImageError, KeyError, OSError, ValueError, SyntaxError, struct.error) as error:
        if isinstance(error, OSError) and error.errno in {errno.ENOSPC, getattr(errno, "EDQUOT", -1)}:
            disk_error(error, core)
        raise core.ApiError(400, "invalid_media", "Tệp không hợp lệ hoặc bị hỏng. Chỉ nhận ảnh JPEG, PNG, WebP và video MP4, WebM có nội dung đúng định dạng.") from error


class UploadStore:
    def __init__(self, app, auth, now, core):
        self.app, self.auth, self.now, self.core = app, auth, now, core
        self.directory = auth.path.parent / "media"
        self.incoming = auth.path.parent / "media-incoming"
        for directory in (self.directory, self.incoming):
            directory.mkdir(mode=0o700, exist_ok=True)
        with auth.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS media_uploads(
                    id TEXT PRIMARY KEY, browser_id TEXT NOT NULL, scope TEXT NOT NULL,
                    original_name TEXT NOT NULL, declared_size INTEGER NOT NULL,
                    declared_type TEXT NOT NULL, last_modified TEXT NOT NULL,
                    offset INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'uploading',
                    metadata TEXT, target_id TEXT, created REAL NOT NULL, updated REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS media_upload_owner ON media_uploads(browser_id,scope);
            """)

    @contextmanager
    def locked(self, upload_id):
        if not self.core.canonical_uuid(upload_id):
            raise self.core.ApiError(404, "upload_not_found", "Không tìm thấy tệp tải lên.")
        if has_request_context():
            # Do not create a disk lock file for arbitrary unauthenticated IDs.
            # Repeat the ownership/session check after acquiring the lock too.
            with self.auth.connection() as db:
                self.record(upload_id, db)
        try:
            # Construct inside the worker so uWSGI pre-fork never inherits it.
            with self.app.extensions["letter_store"].locked(), FileLock(str(self.incoming / (upload_id + ".lock")), timeout=15):
                yield
        except Timeout:
            raise self.core.ApiError(503, "upload_busy", "Tệp đang được xử lý. Vui lòng thử lại.")

    def authorize(self, scope):
        if not isinstance(scope, str) or scope not in {"letters", "journal"}:
            raise self.core.ApiError(400, "invalid_scope", "Khu vực đính kèm không hợp lệ.")
        if not (getattr(g, "authenticated", False) or scope == "journal" and
                (getattr(g, "admin_account", None) or getattr(g, "history_allowed", False))):
            raise self.core.ApiError(401, "unauthorized", "Vui lòng mở khóa hòm thư hoặc đăng nhập quản trị trước khi tải tệp.")

    def record(self, upload_id, db):
        row = db.execute("SELECT * FROM media_uploads WHERE id=? AND browser_id=?", (upload_id, g.browser_id)).fetchone()
        if not row:
            raise self.core.ApiError(404, "upload_not_found", "Không tìm thấy tệp tải lên của trình duyệt này.")
        self.authorize(row["scope"])
        return row

    def status(self, row):
        return {"id": row["id"], "offset": row["offset"], "size": row["declared_size"],
                "state": row["state"], "chunkSize": CHUNK_BYTES,
                "upload": self.public_metadata(json.loads(row["metadata"])) if row["metadata"] else None}

    @staticmethod
    def public_metadata(metadata):
        return {key: value for key, value in metadata.items() if key not in {"storageKey", "storageArea"}}

    def path(self, metadata):
        key = metadata.get("storageKey", "")
        if not isinstance(key, str) or not self.core.STORAGE_KEY.fullmatch(key):
            raise self.core.ApiError(404, "not_found", "Không tìm thấy tệp đính kèm.")
        path = self.directory / key
        if not path.is_file() or path.is_symlink():
            raise self.core.ApiError(404, "not_found", "Không tìm thấy tệp đính kèm.")
        return path

    def resolve_uploads(self, ids, scope, db=None, target_id=None):
        if not isinstance(ids, list) or any(not self.core.canonical_uuid(item) for item in ids) or len(set(ids)) != len(ids):
            raise self.core.ApiError(400, "invalid_uploads", "Danh sách tệp tải lên không hợp lệ.")
        if scope == "letters" and db is None:
            # The JSON replacement and SQLite commit cannot be one filesystem
            # transaction. Treat durable JSON references as authoritative even
            # if a worker died before its SQL claim committed. Always acquire
            # letters.lock BEFORE a SQLite write reservation.
            with self.app.extensions["letter_store"].locked():
                with self.auth.connection() as connection:
                    return self._resolve_uploads(ids, scope, connection, target_id)
        if db is None:
            with self.auth.connection() as connection:
                return self._resolve_uploads(ids, scope, connection, target_id)
        return self._resolve_uploads(ids, scope, db, target_id)

    def letter_reference(self, upload_id):
        return next((letter["id"] for letter in self.app.extensions["letter_store"].read()["letters"]
                     if any(item["id"] == upload_id for item in letter["images"])), None)

    def _resolve_uploads(self, ids, scope, db, target_id):
        # Letter saves hold letters.lock + BEGIN IMMEDIATE before adding JSON
        # references. A caller already holding that SQL write reservation can
        # read the atomically replaced JSON without acquiring locks backwards.
        references = ({image["id"]: letter["id"]
                       for letter in self.app.extensions["letter_store"].read()["letters"]
                       for image in letter["images"]} if scope == "letters" and ids else {})
        result = []
        for upload_id in ids:
            row = self.record(upload_id, db)
            if scope == "letters":
                reference = references.get(upload_id)
                if reference and reference != target_id:
                    raise self.core.ApiError(409, "upload_in_use", "Tệp đã thuộc một bức thư đã lưu và không thể dùng lại ở nội dung khác.")
            if row["scope"] != scope or row["state"] not in {"complete", "claimed"} or row["state"] == "claimed" and row["target_id"] != target_id:
                raise self.core.ApiError(409, "upload_not_ready", "Tệp chưa tải xong hoặc đã được gắn vào một nội dung khác.")
            metadata = json.loads(row["metadata"])
            self.path(metadata)
            result.append(metadata)
        return result

    def claim_uploads(self, ids, scope, target_id, db=None):
        if db is None:
            lock = self.app.extensions["letter_store"].locked() if scope == "letters" else nullcontext()
            with lock, self.auth.transaction() as connection:
                return self.claim_uploads(ids, scope, target_id, connection)
        self.resolve_uploads(ids, scope, db, target_id)
        for upload_id in ids:
            db.execute("UPDATE media_uploads SET state='claimed',target_id=?,updated=? WHERE id=?", (target_id, self.now(), upload_id))

    def cleanup(self, older_than_days=7, dry_run=False):
        """Explicit maintenance only: never expire successful uploads silently.

        A JSON reference or any journal image/history reference wins over SQL
        state, including recovery after an interrupted cross-resource commit.
        """
        if not isinstance(older_than_days, (int, float)) or isinstance(older_than_days, bool) or not math.isfinite(older_than_days) or older_than_days <= 0:
            raise ValueError("Retention must be a positive number of days")
        cutoff = self.now() - older_than_days * 86400
        with self.auth.connection() as db:
            candidates = [row["id"] for row in db.execute("SELECT id FROM media_uploads WHERE state!='claimed' AND updated<?", (cutoff,))]
        removed, protected = 0, 0
        for upload_id in candidates:
            with self.locked(upload_id), self.auth.transaction() as db:
                row = db.execute("SELECT * FROM media_uploads WHERE id=?", (upload_id,)).fetchone()
                if not row or row["state"] == "claimed" or row["updated"] >= cutoff:
                    continue
                if self.letter_reference(upload_id) or db.execute("SELECT 1 FROM journal_images WHERE id=?", (upload_id,)).fetchone():
                    protected += 1
                    continue
                if not dry_run:
                    if row["metadata"]:
                        metadata = json.loads(row["metadata"])
                        key = metadata.get("storageKey", "")
                        if not isinstance(key, str) or not self.core.STORAGE_KEY.fullmatch(key):
                            raise self.core.DataCorruption("Invalid upload metadata; cleanup stopped")
                        destination = self.directory / key
                    else:
                        extension = Path(row["original_name"]).suffix.lower()
                        if extension == ".jpeg":
                            extension = ".jpg"
                        destination = self.directory / (upload_id.replace("-", "") + extension)
                    if destination.is_symlink():
                        raise self.core.DataCorruption("Upload symlinks are not permitted; cleanup stopped")
                    destination.unlink(missing_ok=True)
                    part = self.incoming / (upload_id + ".part")
                    if part.is_symlink():
                        raise self.core.DataCorruption("Upload symlinks are not permitted; cleanup stopped")
                    part.unlink(missing_ok=True)
                    db.execute("DELETE FROM media_uploads WHERE id=?", (upload_id,))
                removed += 1
        # A worker can be killed after creating an empty .part but before its
        # INSERT commits. These old, untracked partials are safe to reclaim.
        for part in self.incoming.glob("*.part"):
            upload_id = part.stem
            if not self.core.canonical_uuid(upload_id) or part.is_symlink():
                continue
            try:
                if part.stat().st_mtime >= cutoff:
                    continue
                with self.locked(upload_id), self.auth.transaction() as db:
                    if db.execute("SELECT 1 FROM media_uploads WHERE id=?", (upload_id,)).fetchone():
                        continue
                    if not part.is_file() or part.is_symlink() or part.stat().st_mtime >= cutoff:
                        continue
                    if not dry_run:
                        part.unlink()
                    removed += 1
            except FileNotFoundError:
                continue
        return {"removed": removed, "protected": protected, "dryRun": bool(dry_run)}


def install_uploads(app, auth, now, core):
    store = UploadStore(app, auth, now, core)
    app.extensions["media_uploads"] = store

    @app.post("/api/uploads")
    def start_upload():
        request.max_content_length = 8192
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise core.ApiError(400, "invalid_upload", "Thông tin tệp chưa hợp lệ.")
        scope = body.get("scope")
        store.authorize(scope)
        name, size, mime = safe_filename(body.get("name")), body.get("size"), body.get("mimeType", "")
        if not name or type(size) is not int or size <= 0 or size > 9223372036854775807 or not isinstance(mime, str) or mime not in TYPES | {"", "application/octet-stream"}:
            raise core.ApiError(400, "invalid_upload", "Tên, loại hoặc dung lượng tệp không hợp lệ.")
        if Path(name).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".webm"}:
            raise core.ApiError(400, "invalid_media", "Chỉ nhận ảnh JPEG, PNG, WebP và video MP4, WebM.")
        upload_id = str(uuid.uuid4())
        part = store.incoming / (upload_id + ".part")
        try:
            with part.open("xb"):
                pass
            with auth.transaction() as db:
                db.execute("INSERT INTO media_uploads(id,browser_id,scope,original_name,declared_size,declared_type,last_modified,created,updated) VALUES(?,?,?,?,?,?,?,?,?)",
                           (upload_id, g.browser_id, scope, name, size, mime, str(body.get("lastModified", ""))[:80], now(), now()))
                row = store.record(upload_id, db)
                result = store.status(row)
        except OSError as error:
            part.unlink(missing_ok=True)
            disk_error(error, core)
        except BaseException:
            part.unlink(missing_ok=True)
            raise
        return jsonify(result), 201

    @app.get("/api/uploads/<upload_id>")
    def upload_status(upload_id):
        with store.locked(upload_id), auth.connection() as db:
            return jsonify(store.status(store.record(upload_id, db)))

    @app.put("/api/uploads/<upload_id>")
    def upload_chunk(upload_id):
        request.max_content_length = CHUNK_BYTES
        if request.mimetype != "application/octet-stream":
            raise core.ApiError(415, "invalid_chunk", "Đoạn tệp phải dùng application/octet-stream.")
        try:
            offset = int(request.headers.get("Upload-Offset", ""))
        except ValueError:
            raise core.ApiError(400, "invalid_offset", "Thiếu vị trí tiếp tục tải tệp.")
        size = request.content_length
        if size is None or size <= 0 or size > CHUNK_BYTES:
            raise core.ApiError(413, "chunk_too_large", "Hãy gửi từng đoạn tệp theo chunkSize của máy chủ.")
        with store.locked(upload_id), auth.transaction() as db:
            row = store.record(upload_id, db)
            if row["state"] != "uploading":
                raise core.ApiError(409, "upload_finished", "Tệp đã tải hoàn tất.", offset=row["offset"])
            if offset != row["offset"]:
                raise core.ApiError(409, "offset_mismatch", "Vị trí tải đã thay đổi. Hãy kiểm tra và tiếp tục từ vị trí máy chủ trả về.", offset=row["offset"])
            if offset + size > row["declared_size"]:
                raise core.ApiError(400, "invalid_chunk", "Đoạn tệp vượt quá kích thước tệp đã khai báo.")
            part = store.incoming / (upload_id + ".part")
            if part.is_symlink() or not part.is_file():
                raise core.ApiError(409, "upload_missing", "Phần tệp đang tải không còn. Hãy chọn tải lại tệp.")
            with part.open("r+b", buffering=0) as destination:
                # Reconcile a process crash between fsync and SQLite commit.
                destination.truncate(offset)
                destination.seek(offset)
                try:
                    remaining = size
                    while remaining:
                        chunk = request.stream.read(min(65536, remaining))
                        if not chunk:
                            raise core.ApiError(400, "upload_interrupted", "Kết nối bị ngắt. Tệp có thể tiếp tục tải lại.")
                        destination.write(chunk)
                        remaining -= len(chunk)
                    destination.flush()
                    os.fsync(destination.fileno())
                    db.execute("UPDATE media_uploads SET offset=?,updated=? WHERE id=?", (offset + size, now(), upload_id))
                    db.commit()
                except BaseException as error:
                    destination.truncate(offset)
                    destination.flush()
                    if isinstance(error, OSError):
                        disk_error(error, core)
                    if isinstance(error, ClientDisconnected):
                        raise core.ApiError(400, "upload_interrupted", "Kết nối bị ngắt. Hãy thử tiếp tục tải tệp.") from error
                    raise
        return jsonify(id=upload_id, offset=offset + size)

    @app.post("/api/uploads/<upload_id>/finish")
    def finish_upload(upload_id):
        request.max_content_length = 4096
        with store.locked(upload_id), auth.transaction() as db:
            row = store.record(upload_id, db)
            if row["state"] in {"complete", "claimed"}:
                return jsonify(upload=store.public_metadata(json.loads(row["metadata"])))
            if row["offset"] != row["declared_size"]:
                raise core.ApiError(409, "upload_incomplete", "Tệp chưa tải đủ. Hãy tiếp tục tải trước khi hoàn tất.", offset=row["offset"])
            part = store.incoming / (upload_id + ".part")
            # A process may die after rename but before SQLite commits. The
            # destination is deterministic so retry can recover the original.
            if not part.exists():
                extension = Path(row["original_name"]).suffix.lower()
                if extension == ".jpeg":
                    extension = ".jpg"
                part = store.directory / (upload_id.replace("-", "") + extension)
            if not part.is_file() or part.is_symlink() or part.stat().st_size != row["offset"]:
                raise core.ApiError(409, "upload_missing", "Phần tệp đang tải không còn đầy đủ. Hãy tải lại tệp.")
            details, extension = inspect_media(part, row["original_name"], row["declared_type"], core)
            metadata = {"id": upload_id, "storageKey": upload_id.replace("-", "") + extension,
                        "storageArea": "media", "originalName": row["original_name"],
                        "size": row["declared_size"], "alt": row["original_name"], "order": 0, **details}
            destination = store.directory / metadata["storageKey"]
            try:
                if part != destination:
                    os.replace(part, destination)
                db.execute("UPDATE media_uploads SET state='complete',metadata=?,updated=? WHERE id=?",
                           (json.dumps(metadata, ensure_ascii=False), now(), upload_id))
                db.commit()
            except BaseException as error:
                if part != destination and destination.exists() and not part.exists():
                    os.replace(destination, part)
                if isinstance(error, OSError):
                    disk_error(error, core)
                raise
        return jsonify(upload=store.public_metadata(metadata))

    @app.delete("/api/uploads/<upload_id>")
    def discard_upload(upload_id):
        with store.locked(upload_id), auth.transaction() as db:
            row = store.record(upload_id, db)
            if row["state"] == "claimed" or row["scope"] == "letters" and store.letter_reference(upload_id):
                raise core.ApiError(409, "upload_in_use", "Tệp đã thuộc một nội dung đã lưu và không thể hủy ở hàng đợi.")
            if row["metadata"]:
                store.path(json.loads(row["metadata"])).unlink(missing_ok=True)
            else:
                # Also cover cancellation immediately after a finish rename
                # whose SQL commit was interrupted by a worker restart.
                extension = Path(row["original_name"]).suffix.lower()
                if extension == ".jpeg":
                    extension = ".jpg"
                recovered = store.directory / (upload_id.replace("-", "") + extension)
                if not recovered.is_symlink():
                    recovered.unlink(missing_ok=True)
            (store.incoming / (upload_id + ".part")).unlink(missing_ok=True)
            db.execute("DELETE FROM media_uploads WHERE id=?", (upload_id,))
        return jsonify(deletedId=upload_id)
    return store
