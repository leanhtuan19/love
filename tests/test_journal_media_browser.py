"""Real Chrome regressions for resumable media, location races and map links."""
import io
import json
import os
from pathlib import Path
import time
import unittest

from PIL import Image
from werkzeug.security import generate_password_hash

import test_browser as helpers


@unittest.skipIf(helpers.sync_playwright is None, "Install Playwright to run browser checks")
class JournalMediaBrowserTests(unittest.TestCase):
    setUpClass = classmethod(helpers.BrowserTests.setUpClass.__func__)
    tearDownClass = classmethod(helpers.BrowserTests.tearDownClass.__func__)
    setUp = helpers.BrowserTests.setUp
    tearDown = helpers.BrowserTests.tearDown
    page = helpers.BrowserTests.page
    wait = helpers.BrowserTests.wait

    def authenticate(self, page):
        token = page.request.get(self.origin + "/api/session").json()["csrfToken"]
        result = page.request.post(self.origin + "/api/auth", data={"password": self.password},
                                   headers={"X-CSRF-Token": token, "Origin": self.origin})
        self.assertEqual(result.status, 200)

    def editor(self, page):
        page.locator("#journal-new").click()
        form = page.locator("#journal-compose")
        form.locator("[name=authorName]").fill("Người viết có dấu")
        form.locator("[name=title]").fill("Nhiều ảnh và video")
        form.locator("[name=content]").fill("Dòng thứ nhất\n" + "NộiDungDài" * 100)
        return form

    def pending_count(self, page, pending, count):
        deadline = time.monotonic() + 10
        while len(pending) < count and time.monotonic() < deadline:
            page.wait_for_timeout(25)
        self.assertGreaterEqual(len(pending), count)

    def test_many_images_large_original_video_playback_and_coordinate_zero(self):
        page = self.page(width=320, height=740, touch=True)
        self.authenticate(page)
        form = self.editor(page)
        tiny = io.BytesIO(); Image.new("RGB", (12, 10), "pink").save(tiny, "PNG")
        # A valid >5 MB original verifies both removed old caps and multiple chunks.
        large = io.BytesIO(); Image.frombytes("RGB", (1500, 1500), os.urandom(1500 * 1500 * 3)).save(large, "PNG")
        self.assertGreater(len(large.getvalue()), 5 * 1024 * 1024)
        form.locator("[name=images]").set_input_files([
            {"name": f"anh-{index}.png", "mimeType": "image/png", "buffer": tiny.getvalue()}
            for index in range(6)
        ])
        form.locator("[name=images]").set_input_files([
            {"name": "anh-goc-lon.png", "mimeType": "image/png", "buffer": large.getvalue()},
        ])
        form.locator("[name=images]").set_input_files(str(Path(__file__).parent / "fixtures" / "sample.webm"))
        self.assertEqual(page.locator(".love-media-item").count(), 8)
        form.locator("[name=locationLabel]").fill("Nhãn thủ công & <đúng vị trí>")
        form.locator(".journal-coordinates summary").click()
        form.locator("[name=latitude]").fill("0")
        form.locator("[name=longitude]").fill("0")
        form.locator("button[type=submit]").click()
        self.wait(page, "() => !!document.querySelector('.journal-post-content')", timeout=35)
        self.assertEqual(page.locator(".journal-post-author").inner_text(), "Người viết có dấu")
        self.assertEqual(page.locator(".journal-gallery .journal-image-button").count(), 8)
        post_id = page.locator("#journal-dialog-body > .journal-id").inner_text().removeprefix("ID: ")
        data = page.request.get(self.origin + "/api/journal/" + post_id).json()["post"]
        saved = next(item for item in data["images"] if item["originalName"] == "anh-goc-lon.png")
        response = page.request.get(self.origin + "/api/journal/images/" + saved["id"])
        self.assertEqual(response.body(), large.getvalue())
        video = page.locator(".journal-gallery video")
        self.assertEqual(video.get_attribute("preload"), "none")
        video.evaluate("v => { v.muted = true; v.play().catch(() => {}); }")
        self.wait(page, "() => document.querySelector('.journal-gallery video').currentTime > 0", timeout=15)
        page.locator(".journal-post-location").click()
        google = page.get_by_role("link", name="Mở bằng Google Maps", exact=True)
        apple = page.get_by_role("link", name="Mở bằng Apple Maps", exact=True)
        self.assertIn("query=0%2C0", google.get_attribute("href"))
        self.assertIn("coordinate=0%2C0", apple.get_attribute("href"))
        self.assertNotIn("query=Nhãn", google.get_attribute("href"))
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        page.keyboard.press("Escape")
        self.assertTrue(page.locator("#journal-dialog").evaluate("d => d.open"))
        video.evaluate("v => {window.previousPublicVideo=v;v.muted=true;v.loop=true;v.play().catch(()=>{});}")
        self.wait(page, "() => !window.previousPublicVideo.paused")
        page.locator('#journal-dialog [data-journal-close]').click()
        self.assertTrue(page.evaluate('window.previousPublicVideo.paused'))

    def test_location_reverse_races_preserve_manual_name_and_newest_gps(self):
        page = self.page(width=390, height=844)
        self.editor(page)
        page.evaluate("() => { window.gpsSequence=0; navigator.geolocation.getCurrentPosition = (success) => { const n=++window.gpsSequence; success({coords:{latitude:n,longitude:n+10,accuracy:7}}); }; }")
        pending = []
        page.route("**/api/location/reverse", lambda route: pending.append(route))
        locate = page.get_by_role("button", name="Lấy vị trí hiện tại")
        locate.click()
        self.wait(page, "() => document.querySelector('[name=latitude]').value === '1'")
        self.pending_count(page, pending, 1)
        page.locator("[name=locationLabel]").fill("Tên mình tự sửa")
        pending[0].fulfill(status=200, content_type="application/json", body=json.dumps({"location": {"lookupAddress": "Địa chỉ cũ", "lookupDistanceMeters": 4, "source": "geoapify", "approximate": False}, "message": "Đã tra cứu"}))
        self.wait(page, "() => document.querySelector('.journal-location-attribution').textContent.includes('Geoapify')")
        self.assertEqual(page.locator("[name=locationLabel]").input_value(), "Tên mình tự sửa")
        locate.click(); self.wait(page, "() => document.querySelector('[name=latitude]').value === '2'")
        self.pending_count(page, pending, 2)
        locate.click(); self.wait(page, "() => document.querySelector('[name=latitude]').value === '3'")
        self.pending_count(page, pending, 3)
        pending[2].fulfill(status=200, content_type="application/json", body=json.dumps({"location": {"lookupAddress": "Địa chỉ mới", "lookupDistanceMeters": 8, "source": "geoapify"}, "message": "Đã tra cứu mới"}))
        try:
            pending[1].fulfill(status=200, content_type="application/json", body=json.dumps({"location": {"lookupAddress": "Địa chỉ trả chậm", "source": "geoapify"}}))
        except Exception:
            pass  # AbortController may have already canceled this older request.
        self.wait(page, "() => document.querySelector('.journal-location-attribution').textContent.includes('8 m')")
        self.assertEqual(page.locator("[name=latitude]").input_value(), "3")
        self.assertEqual(page.locator("[name=locationLabel]").input_value(), "Tên mình tự sửa")

    def test_queue_network_retry_resumes_offset_and_keeps_completed_files(self):
        page = self.page()
        self.authenticate(page)
        self.editor(page)
        image = io.BytesIO(); Image.frombytes("RGB", (800, 800), os.urandom(800 * 800 * 3)).save(image, "PNG")
        page.locator("[name=images]").set_input_files([
            {"name": "thu-lai.png", "mimeType": "application/octet-stream", "buffer": image.getvalue()},
        ])
        offsets = []
        def upload(route):
            if route.request.method != "PUT":
                route.continue_(); return
            offset = int(route.request.headers["upload-offset"]); offsets.append(offset)
            if len(offsets) == 2:
                route.abort("connectionfailed")
            else:
                route.continue_()
        page.route("**/api/uploads/*", upload)
        page.locator("#journal-compose button[type=submit]").click()
        self.wait(page, "() => !!document.querySelector('.love-media-status.is-error')")
        self.assertEqual(page.locator("#journal-compose [name=title]").input_value(), "Nhiều ảnh và video")
        page.locator(".love-media-retry").click()
        self.wait(page, "() => document.querySelector('.love-media-status').textContent.includes('Đã tải xong')")
        self.assertEqual(offsets[:3], [0, 1024 * 1024, 1024 * 1024])
        page.locator("#journal-compose button[type=submit]").click()
        self.wait(page, "() => !!document.querySelector('.journal-post-content')")
        self.assertEqual(len(page.request.get(self.origin + "/api/journal").json()["posts"]), 1)

    def test_edit_video_uses_fresh_journal_password_without_mailbox_session(self):
        password = "test-journal-password-" + os.urandom(8).hex()
        with self.app.extensions["auth_store"].transaction() as db:
            db.execute("INSERT INTO settings(key,value) VALUES('journal_password_hash',?)", (generate_password_hash(password, method="scrypt:32768:8:1"),))
        page = self.page(width=390, height=844)
        self.authenticate(page)
        self.editor(page).locator("button[type=submit]").click()
        self.wait(page, "() => !!document.querySelector('.journal-post-content')")
        token = page.request.get(self.origin + "/api/session").json()["csrfToken"]
        self.assertEqual(page.request.post(self.origin + "/api/logout", data={}, headers={"Origin": self.origin, "X-CSRF-Token": token}).status, 200)
        page.locator("#journal-dialog").get_by_role("button", name="Chỉnh sửa", exact=True).click()
        form = page.locator("#journal-compose")
        form.locator("[name=images]").set_input_files(str(Path(__file__).parent / "fixtures" / "sample.webm"))
        form.locator("[name=password]").fill("wrong-password-for-journal")
        form.locator("button[type=submit]").click()
        self.wait(page, "() => document.querySelector('#journal-dialog-status').classList.contains('is-error')")
        self.assertEqual(page.locator(".love-media-item").count(), 1)
        self.assertEqual(form.locator("[name=password]").input_value(), "")
        form.locator("[name=password]").fill(password)
        form.locator("button[type=submit]").click()
        self.wait(page, "() => !!document.querySelector('.journal-gallery video')")
        self.assertFalse(page.request.get(self.origin + "/api/session").json()["authenticated"])


if __name__ == "__main__":
    unittest.main()
