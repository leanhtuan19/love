"""Browser regressions against isolated private storage and a random test password.

Run: python -m unittest discover -s tests -p test_browser.py -v
Requires Playwright and Chrome/Chromium. No production account or data is used.
"""
import io
import json
import logging
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time
import unittest
from urllib.parse import urlsplit

from PIL import Image
from werkzeug.security import generate_password_hash
from werkzeug.serving import WSGIRequestHandler, make_server

from server import create_app

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


class QuietRequests(WSGIRequestHandler):
    def log_request(self, *args, **kwargs):
        pass


@unittest.skipIf(sync_playwright is None, "Install playwright to run browser checks")
class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.password = secrets.token_urlsafe(26)
        cls.password_hash = generate_password_hash(cls.password, method="scrypt:32768:8:1")
        cls.playwright = sync_playwright().start()
        executable = os.environ.get("LOVEDAYS_BROWSER_EXECUTABLE")
        windows_chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        if not executable and windows_chrome.is_file():
            executable = str(windows_chrome)
        options = {"headless": True}
        if executable:
            options["executable_path"] = executable
        cls.browser = cls.playwright.chromium.launch(**options)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="lovedays-browser-test-")
        self.clock = [time.time()]
        self.app = create_app({"TESTING": True, "DATA_DIR": self.temporary.name,
                               "PASSWORD_HASH": self.password_hash,
                               "TIME_PROVIDER": lambda: self.clock[0]})
        self.app.logger.setLevel(logging.ERROR)
        self.server = make_server("127.0.0.1", 0, self.app, threaded=True,
                                  request_handler=QuietRequests)
        self.server.daemon_threads = False
        self.origin = "http://127.0.0.1:" + str(self.server.server_port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.contexts = []
        self.page_errors = []

    def tearDown(self):
        for context in self.contexts:
            context.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.temporary.cleanup()
        self.assertEqual(self.page_errors, [])

    def wait(self, page, predicate, timeout=12):
        # Python polling keeps the application's CSP intact. Playwright 1.49's
        # wait_for_function polling can use eval under newer Chrome versions.
        deadline = time.monotonic() + timeout
        last_error = None
        while time.monotonic() < deadline:
            try:
                if page.evaluate(predicate):
                    return
            except Exception as error:
                last_error = error
            page.wait_for_timeout(30)
        self.fail("Browser condition timed out: " + predicate +
                  ("; " + str(last_error) if last_error else ""))

    def page(self, width=390, height=844, touch=False, reduced=True, javascript=True):
        context = self.browser.new_context(viewport={"width": width, "height": height},
                                           has_touch=touch, java_script_enabled=javascript,
                                           reduced_motion="reduce" if reduced else "no-preference")
        self.contexts.append(context)
        page = context.new_page()
        # Remote avatars stay unchanged in source; network failures are deterministic here.
        page.route("https://graph.facebook.com/**", lambda route: route.abort())
        page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        page.goto(self.origin, wait_until="domcontentloaded")
        if javascript:
            self.wait(page, "() => !document.querySelector('#love-loader')")
            self.wait(page, "() => !!document.querySelector('#secret-dialog')")
        else:
            self.wait(page, "() => document.styleSheets.length >= 3")
        return page

    def gate(self, page):
        self.tap_page(page, 10)
        self.wait(page, "() => document.querySelector('#secret-dialog').open")
        self.wait(page, "() => !document.querySelector('#secret-password').disabled || !document.querySelector('#secret-workspace').hidden")

    @staticmethod
    def tap_page(page, count):
        page.evaluate("() => window.scrollTo({top:0,behavior:'instant'})")
        page.wait_for_timeout(60)
        for _ in range(count):
            page.mouse.click(20, 80)

    def login(self, page):
        self.gate(page)
        page.locator("#secret-password").fill(self.password)
        page.locator("#secret-auth-submit").click()
        self.wait(page, "() => !document.querySelector('#secret-workspace').hidden")
        self.wait(page, "() => !document.querySelector('#secret-new').disabled")
        self.wait(page, "() => document.querySelector('#secret-list').getAttribute('aria-busy') !== 'true' && !!document.querySelector('#secret-list-summary').textContent")

    def no_overflow(self, page):
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        self.assertTrue(page.locator("#secret-dialog").evaluate("e => e.scrollWidth <= e.clientWidth"))

    @staticmethod
    def picture(color="pink", format="PNG"):
        data = io.BytesIO()
        Image.new("RGB", (24, 18), color).save(data, format=format)
        return data.getvalue()

    def compose(self, page, title, recipient="thu", images=None):
        page.locator("#secret-new").click()
        page.locator("#secret-sender").select_option("tuan" if recipient == "thu" else "thu")
        self.assertEqual(page.locator("#secret-recipient").input_value(), recipient)
        page.locator("#secret-title").fill(title)
        page.locator("#secret-content").fill("Nội dung kiểm thử.\n<script>window.__executed=true</script>")
        if images:
            page.locator("#secret-images").set_input_files(images)
        page.locator("#secret-save").click()
        self.wait(page, "() => document.querySelector('#secret-compose').hidden")
        self.wait(page, "() => !document.querySelector('#secret-new').disabled")
        self.assertEqual(page.locator(".secret-reading-title").inner_text(), title)
        return page.context.request.get(self.origin + "/api/letters").json()["letters"][0]

    def test_touch_threshold_timeout_and_no_private_prefetch(self):
        page = self.page(touch=True)
        requests = []
        page.on("request", lambda request: requests.append(urlsplit(request.url).path))
        for _ in range(9):
            page.touchscreen.tap(20, 80)
        self.assertFalse(page.locator("#secret-dialog").evaluate("e=>e.open"))
        self.assertFalse(any(path.startswith("/api/") for path in requests))
        page.wait_for_timeout(1300)
        page.touchscreen.tap(20, 80)
        self.assertFalse(page.locator("#secret-dialog").evaluate("e=>e.open"))
        for _ in range(9):
            page.touchscreen.tap(20, 80)
        self.wait(page, "() => document.querySelector('#secret-dialog').open")
        self.wait(page, "() => !document.querySelector('#secret-password').disabled")
        self.assertEqual(page.locator("#secret-dialog").count(), 1)
        self.assertEqual(page.locator("#secret-password").get_attribute("type"), "password")
        self.assertNotIn("/api/letters", requests)
        self.assertEqual(requests.count("/api/session"), 1)
        page.keyboard.press("Escape")
        self.assertFalse(page.locator("#secret-dialog").evaluate("e=>e.open"))

    def test_sixth_wrong_password_closes_and_new_context_cannot_bypass(self):
        page = self.page()
        self.gate(page)
        wrong = secrets.token_urlsafe(20)
        for attempt in range(6):
            page.locator("#secret-password").fill(wrong)
            with page.expect_response(lambda r: urlsplit(r.url).path == "/api/auth") as result:
                page.locator("#secret-auth-submit").click()
            self.assertEqual(result.value.status, 429 if attempt == 5 else 401)
            if attempt < 5:
                self.wait(page, "() => !document.querySelector('#secret-password').disabled")
                self.assertTrue(page.locator("#secret-dialog").evaluate("e=>e.open"))
        self.wait(page, "() => !document.querySelector('#secret-dialog').open")
        page.reload(wait_until="domcontentloaded")
        self.wait(page, "() => !document.querySelector('#love-loader')")
        self.tap_page(page, 10)
        self.wait(page, "() => document.querySelector('#secret-dialog').open")
        page.wait_for_timeout(200)
        self.assertTrue(page.locator("#secret-password").is_disabled())
        independent = self.page()
        state = independent.context.request.get(self.origin + "/api/session").json()
        self.assertEqual(state["attemptsRemaining"], 0)
        self.assertGreater(state["retryAfter"], 0)

    def test_crud_image_order_filter_reload_second_context_and_delete(self):
        page = self.page(width=320)
        self.login(page)
        first = self.compose(page, "Thư đầu tiên", images=[
            {"name": "first.png", "mimeType": "image/png", "buffer": self.picture()},
            {"name": "second.jpg", "mimeType": "image/jpeg", "buffer": self.picture("blue", "JPEG")}])
        self.assertEqual([image["order"] for image in first["images"]], [0, 1])
        self.assertEqual([image["originalName"] for image in first["images"]], ["first.png", "second.jpg"])
        self.assertFalse(page.evaluate("!!window.__executed"))
        image_url = self.origin + first["images"][0]["url"]
        self.assertEqual(page.context.request.get(image_url).status, 200)
        page.locator(".secret-gallery-item").first.click()
        self.wait(page, "() => document.querySelector('#secret-lightbox').open")
        page.keyboard.press("Escape")
        self.wait(page, "() => !document.querySelector('#secret-lightbox').open")
        self.clock[0] += 1
        second = self.compose(page, "Thư gửi đến Tuấn", recipient="tuan")
        self.assertNotEqual(first["id"], second["id"])
        page.locator("#secret-filter").select_option("thu")
        self.assertEqual(page.locator(".secret-letter-row").count(), 1)
        self.assertEqual(page.locator(".secret-letter-row").get_attribute("data-letter-id"), first["id"])
        page.locator(".secret-letter-row").click()
        self.wait(page, "() => document.querySelector('.secret-reading-title').textContent==='Thư đầu tiên'")
        page.locator(".secret-letter-actions button").first.click()
        page.locator("#secret-title").fill("Đã sửa")
        page.locator("#secret-save").click()
        self.wait(page, "() => document.querySelector('#secret-compose').hidden")
        self.wait(page, "() => document.querySelector('.secret-reading-title').textContent==='Đã sửa'")
        edited = page.context.request.get(self.origin + "/api/letters/" + first["id"]).json()["letter"]
        self.assertEqual(edited["id"], first["id"])
        self.assertEqual(edited["createdAt"], first["createdAt"])
        self.assertGreater(edited["updatedAt"], first["updatedAt"])
        self.assertEqual([image["id"] for image in edited["images"]], [image["id"] for image in first["images"]])
        page.reload(wait_until="domcontentloaded")
        self.wait(page, "() => !!document.querySelector('#secret-dialog')")
        self.gate(page)
        self.wait(page, "() => !document.querySelector('#secret-workspace').hidden")
        self.wait(page, "() => document.querySelectorAll('.secret-letter-row').length===2")
        self.assertEqual(page.locator(".secret-letter-row").count(), 2)
        independent = self.page(width=1440)
        self.assertEqual(independent.context.request.get(image_url).status, 401)
        self.login(independent)
        self.assertEqual(independent.locator(".secret-letter-row").count(), 2)
        stored = json.loads((Path(self.temporary.name) / "letters.json").read_text(encoding="utf-8"))
        self.assertEqual(stored["schemaVersion"], 1)
        self.assertEqual(len(stored["letters"]), 2)
        page.locator('[data-letter-id="' + first["id"] + '"]').click()
        self.wait(page, "() => document.querySelector('.secret-reading-title').textContent==='Đã sửa'")
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator(".secret-letter-actions button").last.click()
        self.wait(page, "() => document.querySelectorAll('.secret-letter-row').length===1")
        self.assertEqual(page.context.request.get(image_url).status, 404)
        self.assertEqual(len(list((Path(self.temporary.name) / "images").iterdir())), 0)

    def test_session_expiry_relocks_workspace_and_keeps_unsent_draft(self):
        page = self.page()
        self.login(page)
        page.locator("#secret-new").click()
        page.locator("#secret-title").fill("Bản nháp đang viết")
        page.locator("#secret-content").fill("Nội dung chưa gửi")
        self.clock[0] += 1801
        page.wait_for_timeout(1100)
        page.evaluate("window.dispatchEvent(new Event('focus'))")
        self.wait(page, "() => !document.querySelector('#secret-gate').hidden")
        self.assertTrue(page.locator("#secret-workspace").is_hidden())
        self.assertEqual(page.context.request.get(self.origin + "/api/letters").status, 401)
        page.locator("#secret-password").fill(self.password)
        page.locator("#secret-auth-submit").click()
        self.wait(page, "() => !document.querySelector('#secret-workspace').hidden")
        page.locator("#secret-new").click()
        self.assertEqual(page.locator("#secret-title").input_value(), "Bản nháp đang viết")
        self.assertEqual(page.locator("#secret-content").input_value(), "Nội dung chưa gửi")

    def test_responsive_gate_workspace_compose_and_keyboard(self):
        page = self.page(width=280, height=568)
        self.login(page)
        for width in [280, 320, 390, 768, 1440]:
            page.set_viewport_size({"width": width, "height": 720})
            self.no_overflow(page)
        page.locator("#secret-new").click()
        page.locator("#secret-title").fill("Một tiêu đề tiếng Việt dài " * 5)
        page.locator("#secret-content").fill("Nội dung không có khoảng trắng: " + "X" * 500)
        for width in [280, 320, 390, 768, 1440]:
            page.set_viewport_size({"width": width, "height": 568})
            self.no_overflow(page)
        page.locator("#secret-close").focus()
        page.keyboard.press("Shift+Tab")
        self.assertTrue(page.evaluate("!!document.activeElement.closest('#secret-dialog')"))
        page.keyboard.press("Tab")
        self.assertEqual(page.evaluate("document.activeElement.id"), "secret-close")
        page.once("dialog", lambda dialog: dialog.accept())
        page.keyboard.press("Escape")
        self.wait(page, "() => !document.querySelector('#secret-dialog').open")
        self.assertEqual(page.evaluate("document.activeElement.id"), "heart")
        self.assertFalse(page.evaluate("document.body.classList.contains('dialog-open')"))

    def test_loading_fallback_fonts_and_no_javascript_base(self):
        page = self.page()
        page.locator('[data-profile="tuan"]').evaluate("e=>e.click()")
        self.wait(page, "() => document.fonts.check('500 24px \\\"Lora Love\\\"')")
        cdp = page.context.new_cdp_session(page)
        cdp.send("DOM.enable")
        cdp.send("CSS.enable")
        document = cdp.send("DOM.getDocument")
        node = cdp.send("DOM.querySelector", {"nodeId": document["root"]["nodeId"], "selector": "#profile-name"})["nodeId"]
        fonts = cdp.send("CSS.getPlatformFontsForNode", {"nodeId": node})["fonts"]
        self.assertTrue(any(font["isCustomFont"] and font["familyName"] == "Lora" for font in fonts), fonts)
        page.set_viewport_size({"width": 280, "height": 568})
        page.locator("#profile-name").evaluate("e=>e.textContent='Nguyễn Thị Phương Thảo Ở Miền Quê Hà Tĩnh'")
        self.assertTrue(page.locator("#profile-name").evaluate("e=>e.scrollWidth<=e.clientWidth && e.scrollHeight<=e.clientHeight"))
        plain = self.page(javascript=False, width=280)
        self.assertFalse(plain.locator("#love-loader").is_visible())
        self.assertTrue(plain.locator("#info").is_visible())
        self.assertTrue(plain.locator("audio").is_visible())
        self.assertFalse(plain.evaluate("document.documentElement.scrollWidth>innerWidth"))

    def test_stalled_script_cannot_leave_loading_overlay_blocking_content(self):
        context = self.browser.new_context(viewport={"width": 390, "height": 844},
                                           reduced_motion="reduce")
        self.contexts.append(context)
        page = context.new_page()
        held = []
        page.route("https://graph.facebook.com/**", lambda route: route.abort())
        page.route("**/app.js", lambda route: held.append(route))
        page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        page.add_init_script("document.addEventListener('DOMContentLoaded',()=>window.__domReady=true)")
        page.goto(self.origin, wait_until="commit")
        self.wait(page, "() => !!document.querySelector('#info')")
        self.assertTrue(held)
        self.wait(page, "() => !document.querySelector('#love-loader')", timeout=8)
        self.assertFalse(page.evaluate("!!window.__domReady"))
        self.assertTrue(page.locator(".profile").first.evaluate("e=>getComputedStyle(e).opacity==='1'"))
        self.assertTrue(page.locator("audio").is_visible())
        self.assertTrue(page.locator("audio").evaluate("e=>e.controls"))
        held[0].abort()
        self.wait(page, "() => !!window.__domReady")
        self.assertFalse(page.evaluate("document.documentElement.classList.contains('love-loading')"))


if __name__ == "__main__":
    unittest.main()
