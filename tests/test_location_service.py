"""Provider calls are mocked; no real API keys or device coordinates are used."""
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock
from urllib.error import URLError

from server import create_app
from location_service import choose_result


class LocationServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="lovedays-location-")
        self.addCleanup(self.temporary.cleanup)
        self.clock = [time.time()]
        self.config = {"TESTING": True, "DATA_DIR": self.temporary.name, "PASSWORD_HASH": None,
                       "SQLITE_JOURNAL_MODE": "DELETE", "TIME_PROVIDER": lambda: self.clock[0],
                       "GEOAPIFY_API_KEY": "disposable-provider-key-for-mocked-tests"}
        self.app = create_app(self.config)
        self.client = self.app.test_client()

    def headers(self, client=None):
        client = client or self.client
        return {"Origin": "http://localhost", "X-CSRF-Token": client.get("/api/session").get_json()["csrfToken"]}

    def reverse(self, body=None, client=None):
        client = client or self.client
        return client.post("/api/location/reverse", json=body or {"latitude": 0, "longitude": 0, "accuracy": 42}, headers=self.headers(client))

    def provider(self, results):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({"results": results}).encode()
        return mock.patch("location_service.urlopen", return_value=response)

    def result(self, **changes):
        return {"result_type": "building", "distance": 4, "housenumber": "19", "street": "Đường Bình Yên",
                "city": "Hà Tĩnh", "country": "Việt Nam", **changes}

    def test_nearest_including_zero_and_gps_accuracy_remains_separate(self):
        with self.provider([self.result(distance=70), self.result(distance=0)]) as request:
            response = self.reverse()
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertEqual(result["status"], "resolved")
        location = result["location"]
        self.assertEqual((location["latitude"], location["longitude"]), (0, 0))
        self.assertEqual(location["lookupDistanceMeters"], 0)
        self.assertEqual(location["accuracy"], 42)
        self.assertEqual(location["label"], "")
        self.assertIn("Đường Bình Yên", location["lookupAddress"])
        self.assertIn("Geoapify", location["attribution"])
        self.assertEqual(request.call_args.kwargs["timeout"], 5)
        self.assertNotIn(self.config["GEOAPIFY_API_KEY"], response.get_data(as_text=True))

    def test_10_to_100m_is_reference_and_further_results_are_area_only(self):
        with self.provider([self.result(distance=100)]):
            within = self.reverse().get_json()
        self.assertEqual(within["status"], "resolved")
        self.assertTrue(within["location"]["approximate"])
        # A different coordinate prevents a cache hit from the preceding lookup.
        with self.provider([self.result(distance=101, name="Một cửa hàng")]):
            far = self.reverse({"latitude": 1, "longitude": 0}).get_json()
        self.assertEqual(far["status"], "approximate")
        self.assertEqual(far["location"]["lookupAddress"], "Hà Tĩnh, Việt Nam")
        self.assertNotIn("Đường Bình Yên", far["location"]["lookupAddress"])
        self.assertNotIn("cửa hàng", far["location"]["lookupAddress"])

    def test_business_name_does_not_become_precise_user_address(self):
        for result_type in ("amenity", "building"):
            result = choose_result([{"result_type": result_type, "distance": 2, "name": "Shop beside you",
                                     "formatted": "Shop beside you, Ha Tinh", "city": "Hà Tĩnh"}], 0, 0)
            self.assertEqual(result["status"], "approximate")
            self.assertEqual(result["lookupAddress"], "Hà Tĩnh")

    def test_missing_distance_can_be_computed_and_missing_results_falls_back(self):
        result = self.result(distance=None, lat=0, lon=0)
        self.assertEqual(choose_result([result], 0, 0)["lookupDistanceMeters"], 0)
        with self.provider([]):
            response = self.reverse()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "unavailable")
        self.assertEqual(response.get_json()["location"]["latitude"], 0)

    def test_missing_key_timeout_or_invalid_provider_response_preserves_coordinates(self):
        service = self.app.extensions["reverse_geocoder"]
        service.key = ""
        with mock.patch("location_service.urlopen") as request:
            self.assertEqual(self.reverse().get_json()["status"], "unavailable")
            request.assert_not_called()
        service.key = "mocked-key"
        for error in (TimeoutError(), URLError("network unavailable")):
            with mock.patch("location_service.urlopen", side_effect=error):
                response = self.reverse()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_json()["location"]["accuracy"], 42)
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"not valid JSON"
        with mock.patch("location_service.urlopen", return_value=response):
            self.assertEqual(self.reverse().get_json()["status"], "unavailable")

    def test_cache_survives_restart_but_accuracy_is_current_request(self):
        with self.provider([self.result()]) as request:
            self.assertEqual(self.reverse().status_code, 200)
            self.assertEqual(self.reverse({"latitude": 0, "longitude": 0, "accuracy": 2}).get_json()["location"]["accuracy"], 2)
            self.assertEqual(request.call_count, 1)
        other = create_app(self.config).test_client()
        with mock.patch("location_service.urlopen") as request:
            result = self.reverse(client=other).get_json()
            self.assertEqual(result["status"], "resolved")
            request.assert_not_called()
        self.clock[0] += 86401
        with self.provider([self.result()]) as request:
            self.assertEqual(self.reverse(client=other).status_code, 200)
            self.assertEqual(request.call_count, 1)

    def test_durable_rate_limit_survives_browser_and_app_reset(self):
        self.app.extensions["reverse_geocoder"].rate_limit = 2
        self.app.extensions["reverse_geocoder"].key = ""
        self.assertEqual(self.reverse().status_code, 200)
        self.assertEqual(self.reverse().status_code, 200)
        other_app = create_app({**self.config, "GEOCODE_REQUESTS_PER_MINUTE": 2})
        denied = self.reverse(client=other_app.test_client())
        self.assertEqual(denied.status_code, 429)
        self.assertGreater(denied.get_json()["retryAfter"], 0)
        self.clock[0] += 61
        other_app.extensions["reverse_geocoder"].key = ""
        self.assertEqual(self.reverse(client=other_app.test_client()).status_code, 200)

    def test_csrf_and_invalid_coordinates_and_accuracy(self):
        self.assertEqual(self.client.post("/api/location/reverse", json={"latitude": 0, "longitude": 0}).status_code, 403)
        for body in ({"latitude": True, "longitude": 0}, {"latitude": 91, "longitude": 0},
                     {"latitude": 0, "longitude": None}, {"latitude": 0, "longitude": 0, "accuracy": -1},
                     {"latitude": 0, "longitude": 0, "accuracy": True}):
            self.assertEqual(self.reverse(body).status_code, 400)


if __name__ == "__main__":
    unittest.main()
