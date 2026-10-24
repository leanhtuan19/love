"""Explicit, server-side Geoapify lookups with durable cache and request throttling.

Coordinates remain the device coordinates. Provider distance is never GPS accuracy.
Geoapify permits storing results with attribution; its reverse endpoint has no
radius parameter, so returned distances are filtered here (10m preferred, 100m
maximum for a detailed address).
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import hmac
import json
import math
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import g, jsonify, request


ATTRIBUTION = "Powered by Geoapify · © OpenStreetMap contributors"
ATTRIBUTION_URL = "https://www.geoapify.com/"
DETAIL_TYPES = {"building", "street", "amenity", "address"}


def coordinates(latitude, longitude):
    return (type(latitude) in (int, float) and type(longitude) in (int, float)
            and math.isfinite(latitude) and math.isfinite(longitude)
            and -90 <= latitude <= 90 and -180 <= longitude <= 180)


def nonnegative(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def normalize_location(location, core):
    """Validate both old three-field locations and richer new location metadata."""
    allowed = {"label", "latitude", "longitude", "accuracy", "lookupAddress", "lookupDistanceMeters",
               "source", "attribution", "attributionUrl", "approximate"}
    if not isinstance(location, dict) or set(location) - allowed:
        raise core.ApiError(400, "invalid_location", "Địa điểm chưa hợp lệ.")
    latitude, longitude = location.get("latitude"), location.get("longitude")
    if (latitude is None) != (longitude is None) or (latitude is not None and not coordinates(latitude, longitude)):
        raise core.ApiError(400, "invalid_location", "Cần tọa độ vĩ độ và kinh độ hợp lệ, hoặc nhập địa điểm thủ công.")
    result = {"latitude": latitude, "longitude": longitude}
    for name, maximum in (("label", 240), ("lookupAddress", 500), ("attribution", 1000)):
        value = location.get(name, "")
        if not isinstance(value, str) or len(value) > maximum or "\x00" in value:
            raise core.ApiError(400, "invalid_location", "Tên và thông tin địa điểm chưa hợp lệ.")
        result[name] = value.strip()
    for name in ("accuracy", "lookupDistanceMeters"):
        value = location.get(name)
        if value is not None and not nonnegative(value):
            raise core.ApiError(400, "invalid_location", "Độ chính xác và khoảng cách cần là số mét không âm.")
        result[name] = value
    result["source"] = location.get("source", "manual")
    if result["source"] not in {"manual", "geolocation", "geoapify"}:
        raise core.ApiError(400, "invalid_location", "Nguồn địa điểm chưa hợp lệ.")
    result["approximate"] = location.get("approximate", False)
    if type(result["approximate"]) is not bool:
        raise core.ApiError(400, "invalid_location", "Trạng thái địa chỉ gần đúng chưa hợp lệ.")
    url = location.get("attributionUrl", "")
    if url not in ("", ATTRIBUTION_URL):
        raise core.ApiError(400, "invalid_location", "Liên kết ghi nguồn địa điểm chưa hợp lệ.")
    result["attributionUrl"] = url
    # Retain provider attribution even when the visible label is manually edited.
    if result["source"] == "geoapify" or result["lookupAddress"]:
        result["attribution"] = result["attribution"] or ATTRIBUTION
        result["attributionUrl"] = ATTRIBUTION_URL
    return result


def distance_to(result, latitude, longitude):
    value = result.get("distance")
    if nonnegative(value):
        return float(value)
    lat, lon = result.get("lat"), result.get("lon")
    if not coordinates(lat, lon):
        return None
    a, b = math.radians(latitude), math.radians(lat)
    delta_a, delta_b = b - a, math.radians(lon - longitude)
    value = math.sin(delta_a / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(delta_b / 2) ** 2
    return 6371008.8 * 2 * math.asin(min(1, math.sqrt(value)))


def join_parts(values):
    parts = []
    for value in values:
        if isinstance(value, str) and value.strip() and value.strip() not in parts:
            parts.append(value.strip())
    return ", ".join(parts)[:500]


def address_for(result):
    """Do not present a nearby business name as the user's precise address."""
    road = " ".join(str(result.get(key, "")).strip() for key in ("housenumber", "street") if result.get(key))
    address = join_parts((road, result.get("suburb"), result.get("district"), result.get("city"),
                          result.get("county"), result.get("state"), result.get("country")))
    if road:
        return address
    if result.get("result_type") not in {"amenity", "unknown"} and not result.get("name"):
        formatted = result.get("formatted")
        if isinstance(formatted, str) and formatted.strip():
            return formatted.strip()[:500]
    return ""


def choose_result(results, latitude, longitude):
    candidates = []
    for result in results:
        if not isinstance(result, dict):
            continue
        distance = distance_to(result, latitude, longitude)
        address = address_for(result)
        if result.get("result_type") in DETAIL_TYPES and address and distance is not None and distance <= 100:
            candidates.append((distance, address, result))
    if candidates:
        # Distances <= 10m are included and naturally precede the 10-100m band.
        distance, address, result = min(candidates, key=lambda item: item[0])
        status, approximate = "resolved", distance > 10
        message = "Đã tìm địa chỉ gần vị trí GPS; bạn có thể sửa tên trước khi đăng."
        if approximate:
            message = "Địa chỉ tham khảo trong 100 m; hãy kiểm tra hoặc sửa tên trước khi đăng."
    else:
        areas = []
        for result in results:
            if not isinstance(result, dict):
                continue
            area = join_parts(result.get(key) for key in ("suburb", "district", "city", "county", "state", "country"))
            if area:
                distance = distance_to(result, latitude, longitude)
                areas.append((distance if distance is not None else math.inf, area, result))
        if not areas:
            return {"status": "unavailable", "message": "Chưa tìm được địa chỉ phù hợp trong 100 m. Tọa độ được giữ; hãy nhập địa điểm thủ công.",
                    "lookupAddress": "", "lookupDistanceMeters": None, "approximate": True, "source": "geolocation", "attribution": "", "attributionUrl": ""}
        distance, address, result = min(areas, key=lambda item: item[0])
        distance = distance if math.isfinite(distance) else None
        status, approximate = "approximate", True
        message = "Chưa có địa chỉ chi tiết phù hợp trong 100 m; đang hiển thị khu vực gần đúng. Bạn có thể nhập tên địa điểm."
    attribution = ATTRIBUTION
    datasource = result.get("datasource")
    if isinstance(datasource, dict) and isinstance(datasource.get("attribution"), str):
        attribution += " · " + datasource["attribution"][:700]
    return {"status": status, "message": message, "lookupAddress": address, "lookupDistanceMeters": distance,
            "approximate": approximate, "source": "geoapify", "attribution": attribution, "attributionUrl": ATTRIBUTION_URL}


class ReverseGeocoder:
    def __init__(self, app, auth, now, lookup_key, core):
        self.app, self.auth, self.now, self.lookup_key, self.core = app, auth, now, lookup_key, core
        self.key = app.config.get("GEOAPIFY_API_KEY", os.environ.get("LOVEDAYS_GEOAPIFY_API_KEY", ""))
        self.timeout = float(app.config.get("GEOCODE_TIMEOUT_SECONDS", 5))
        self.ttl = int(app.config.get("GEOCODE_CACHE_SECONDS", 86400))
        self.rate_limit = int(app.config.get("GEOCODE_REQUESTS_PER_MINUTE", 12))
        with auth.transaction() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS geocode_cache(key TEXT PRIMARY KEY, data TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS geocode_rates(key TEXT PRIMARY KEY, count INTEGER NOT NULL, started REAL NOT NULL);
            """)

    def limited(self):
        keys = ["browser:" + g.browser_id, "ip:" + hmac.new(self.lookup_key, (request.remote_addr or "unknown").encode(), hashlib.sha256).hexdigest()]
        timestamp = self.now()
        with self.auth.transaction() as db:
            for key in keys:
                row = db.execute("SELECT count,started FROM geocode_rates WHERE key=?", (key,)).fetchone()
                if row and row["started"] + 60 > timestamp and row["count"] >= self.rate_limit:
                    raise self.core.ApiError(429, "location_rate_limited", "Bạn lấy vị trí quá nhanh. Hãy đợi một chút hoặc nhập địa điểm thủ công.", retryAfter=max(1, math.ceil(row["started"] + 60 - timestamp)))
            for key in keys:
                row = db.execute("SELECT count,started FROM geocode_rates WHERE key=?", (key,)).fetchone()
                fresh = not row or row["started"] + 60 <= timestamp
                db.execute("INSERT INTO geocode_rates VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET count=excluded.count,started=excluded.started",
                           (key, 1 if fresh else row["count"] + 1, timestamp if fresh else row["started"]))
            db.execute("DELETE FROM geocode_rates WHERE started<?", (timestamp - 120,))
            db.execute("DELETE FROM geocode_cache WHERE expires<=?", (timestamp,))

    def reverse(self, latitude, longitude):
        fallback = {"status": "unavailable", "message": "Chưa thể tra cứu địa chỉ. Tọa độ vẫn được giữ; bạn có thể nhập địa điểm thủ công.",
                    "lookupAddress": "", "lookupDistanceMeters": None, "approximate": True, "source": "geolocation", "attribution": "", "attributionUrl": ""}
        if not self.key:
            return fallback
        cache_key = hashlib.sha256(json.dumps([latitude, longitude], separators=(",", ":")).encode()).hexdigest()
        with self.auth.connection() as db:
            cached = db.execute("SELECT data FROM geocode_cache WHERE key=? AND expires>?", (cache_key, self.now())).fetchone()
        if cached:
            return json.loads(cached[0])
        query = urlencode({"lat": latitude, "lon": longitude, "limit": 10, "lang": "vi", "format": "json", "apiKey": self.key})
        provider_request = Request("https://api.geoapify.com/v1/geocode/reverse?" + query, headers={"Accept": "application/json", "User-Agent": "LoveDays/1.0"})
        try:
            # A bounded provider response avoids untrusted network data exhausting RAM.
            with urlopen(provider_request, timeout=self.timeout) as response:
                raw = response.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    return fallback
                document = json.loads(raw)
            results = document.get("results") if isinstance(document, dict) else None
            if not isinstance(results, list):
                return fallback
            result = choose_result(results, latitude, longitude)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, TypeError):
            # Never log the provider URL: it contains the server-only API key.
            return fallback
        with self.auth.transaction() as db:
            db.execute("INSERT INTO geocode_cache VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET data=excluded.data,expires=excluded.expires",
                       (cache_key, json.dumps(result, ensure_ascii=False, allow_nan=False), self.now() + self.ttl))
        return result


def install_location(app, store, core):
    service = ReverseGeocoder(app, store.auth, store.now, store.lookup_key, core)
    app.extensions["reverse_geocoder"] = service

    @app.post("/api/location/reverse")
    def reverse_location():
        request.max_content_length = 4096
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or set(body) - {"latitude", "longitude", "accuracy"} or not coordinates(body.get("latitude"), body.get("longitude")):
            raise core.ApiError(400, "invalid_location", "Tọa độ tra cứu địa điểm không hợp lệ.")
        accuracy = body.get("accuracy")
        if accuracy is not None and not nonnegative(accuracy):
            raise core.ApiError(400, "invalid_location", "Độ chính xác GPS cần là số mét không âm.")
        service.limited()
        result = deepcopy(service.reverse(body["latitude"], body["longitude"]))
        status, message = result.pop("status"), result.pop("message")
        location = {"label": "", "latitude": body["latitude"], "longitude": body["longitude"], "accuracy": accuracy, **result}
        return jsonify(location=location, status=status, message=message)

    return service
