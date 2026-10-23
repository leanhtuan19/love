"""Real pointer/touch regressions for the ten-tap letter trigger.

Run: python -m unittest discover -s tests -p test_gestures.py -v
Uses Chrome/Chromium through Playwright and isolated temporary private storage.
Touch checks emulate Chromium mobile input; they do not replace device Safari tests.
"""
import unittest
from urllib.parse import urlsplit

import test_browser as browser_helpers


@unittest.skipIf(browser_helpers.sync_playwright is None, "Install playwright to run browser checks")
class GestureTests(unittest.TestCase):
    # Reuse infrastructure without inheriting and re-running the legacy suite.
    setUpClass = classmethod(browser_helpers.BrowserTests.setUpClass.__func__)
    tearDownClass = classmethod(browser_helpers.BrowserTests.tearDownClass.__func__)
    setUp = browser_helpers.BrowserTests.setUp
    tearDown = browser_helpers.BrowserTests.tearDown
    wait = browser_helpers.BrowserTests.wait

    def page(self, touch=False, width=390, height=844, prefix=""):
        context = self.browser.new_context(
            viewport={"width": width, "height": height}, has_touch=touch,
            is_mobile=touch, reduced_motion="reduce")
        self.contexts.append(context)
        page = context.new_page()
        page.route("https://graph.facebook.com/**", lambda route: route.abort())
        if prefix:
            # Simulate mounting the same WSGI app below a repository base path.
            # The URL visible to the browser retains /love/ for all resources.
            page.route(self.origin + prefix + "**", lambda route: route.continue_(
                url=self.origin + route.request.url[len(self.origin + prefix) - 1:]))
        page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        self.paths = []
        self.responses = []
        page.on("request", lambda request: self.paths.append(urlsplit(request.url).path))
        page.on("response", lambda response: self.responses.append((urlsplit(response.url).path, response.status)))
        page.goto(self.origin + prefix, wait_until="domcontentloaded")
        self.wait(page, "() => !document.querySelector('#love-loader') && !!document.querySelector('#secret-dialog')")
        return page

    @staticmethod
    def is_open(page):
        return page.locator("#secret-dialog").evaluate("e => e.open")

    def taps(self, page, count, touch=False, varied=False):
        selectors = [".page-subtitle", ".page-header h1", ".section-label"] if varied else [".page-subtitle"]
        for index in range(count):
            target = page.locator(selectors[index % len(selectors)])
            if touch:
                target.tap()
            else:
                target.click()

    def assert_opens_on_tenth(self, page, touch=False):
        self.taps(page, 9, touch=touch)
        self.assertFalse(self.is_open(page), "Nine valid taps must not open the letter")
        self.taps(page, 1, touch=touch)
        self.wait(page, "() => document.querySelector('#secret-dialog').open")

    def close(self, page):
        page.keyboard.press("Escape")
        self.wait(page, "() => !document.querySelector('#secret-dialog').open")

    def test_mouse_nine_then_tenth_different_positions_single_popup_and_close_reset(self):
        page = self.page(width=1440, height=900)
        # Body background outside the central card is part of the website too.
        page.mouse.click(5, 5)
        self.taps(page, 8, varied=True)
        self.assertFalse(self.is_open(page))
        # Public site configuration and published journal entries load on the
        # page; the private mailbox remains untouched until its trigger opens.
        self.assertNotIn("/api/session", self.paths)
        self.assertNotIn("/api/letters", self.paths)
        self.taps(page, 1)
        self.wait(page, "() => document.querySelector('#secret-dialog').open")
        self.wait(page, "() => !document.querySelector('#secret-password').disabled")
        self.assertEqual(page.locator("#secret-dialog").count(), 1)
        self.assertEqual(self.paths.count("/api/session"), 1)
        self.assertNotIn("/api/letters", self.paths)
        for _ in range(12):
            page.locator(".secret-gate-description").click()
        self.assertEqual(self.paths.count("/api/session"), 1)
        self.assertEqual(page.locator("dialog[open]").count(), 1)
        self.assertTrue(page.evaluate("document.body.classList.contains('dialog-open')"))
        self.close(page)
        self.assertFalse(page.evaluate("document.body.classList.contains('dialog-open')"))
        self.assert_opens_on_tenth(page)

    def test_mobile_touch_compatibility_clicks_not_double_counted_and_no_zoom(self):
        page = self.page(touch=True)
        self.taps(page, 9, touch=True, varied=True)
        self.assertFalse(self.is_open(page))
        self.assertEqual(page.evaluate("visualViewport.scale"), 1)
        self.taps(page, 1, touch=True)
        self.wait(page, "() => document.querySelector('#secret-dialog').open")
        self.assertEqual(self.paths.count("/api/session"), 1)
        self.assertEqual(page.evaluate("visualViewport.scale"), 1)
        for width in [320, 390, 430, 768]:
            page.set_viewport_size({"width": width, "height": 740})
            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            self.assertTrue(page.locator("#secret-dialog").evaluate("e => e.scrollWidth <= e.clientWidth"))
        self.close(page)
        self.assert_opens_on_tenth(page, touch=True)

    def test_mobile_heart_svg_and_column_whitespace_share_one_counter(self):
        page = self.page(touch=True)
        page.emulate_media(reduced_motion="no-preference")
        page.wait_for_timeout(1500)

        def tap_heart_area(index):
            if index % 2:
                bounds = page.locator(".heart-column").bounding_box()
                # The top of the column is outside its centered heart button.
                x, y = bounds["x"] + bounds["width"] / 2, bounds["y"] + 2
            else:
                bounds = page.locator("#heart .heart-icon").bounding_box()
                x, y = bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2
            # Coordinates avoid waiting for the animated SVG to become stable.
            page.touchscreen.tap(x, y)

        for index in range(9):
            tap_heart_area(index)
        self.assertFalse(self.is_open(page))
        self.assertEqual(page.evaluate("visualViewport.scale"), 1)
        tap_heart_area(9)
        self.wait(page, "() => document.querySelector('#secret-dialog').open")
        self.wait(page, "() => !document.querySelector('#secret-password').disabled")
        self.assertEqual(self.paths.count("/api/session"), 1)
        self.assertEqual(page.locator("#secret-dialog").count(), 1)
        for _ in range(9):
            page.locator(".secret-gate-description").tap()
        self.assertEqual(self.paths.count("/api/session"), 1)
        self.assertEqual(page.locator("dialog[open]").count(), 1)
        self.close(page)
        for index in range(9):
            tap_heart_area(index)
        self.assertFalse(self.is_open(page))
        tap_heart_area(9)
        self.wait(page, "() => document.querySelector('#secret-dialog').open")
        self.assertEqual(page.evaluate("visualViewport.scale"), 1)

    def test_gap_resets_chain_but_total_sequence_can_exceed_two_seconds(self):
        page = self.page()
        self.taps(page, 5)
        page.wait_for_timeout(1300)
        self.taps(page, 5)
        self.assertFalse(self.is_open(page))
        self.taps(page, 4)
        self.assertFalse(self.is_open(page))
        self.taps(page, 1)
        self.wait(page, "() => document.querySelector('#secret-dialog').open")
        self.close(page)
        for _ in range(9):
            self.taps(page, 1)
            page.wait_for_timeout(300)
        self.assertFalse(self.is_open(page))
        self.taps(page, 1)
        self.wait(page, "() => document.querySelector('#secret-dialog').open")

    def test_synthetic_events_right_click_drag_and_hold_do_not_count(self):
        page = self.page(width=1280, height=900)
        for kind in ["synthetic", "right-click", "drag", "hold"]:
            with self.subTest(kind=kind):
                target = page.locator(".page-header h1")
                bounds = target.bounding_box()
                x, y = bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2
                if kind == "synthetic":
                    target.evaluate("""e => {
                        for (let i = 0; i < 20; i++) {
                            e.click();
                            e.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, pointerId: 1, pointerType: 'mouse', isPrimary: true, button: 0}));
                            e.dispatchEvent(new PointerEvent('pointerup', {bubbles: true, pointerId: 1, pointerType: 'mouse', isPrimary: true, button: 0}));
                        }
                    }""")
                elif kind == "right-click":
                    page.mouse.click(x, y, button="right")
                    page.keyboard.press("Escape")
                else:
                    page.mouse.move(x, y)
                    page.mouse.down()
                    if kind == "drag":
                        # Returning to the start must not turn a drag into a tap.
                        page.mouse.move(x + 45, y, steps=3)
                        page.mouse.move(x, y, steps=3)
                    else:
                        page.wait_for_timeout(600)
                    page.mouse.up()
                self.assert_opens_on_tenth(page)
                self.close(page)

    def test_touch_multitouch_cancel_and_real_vertical_scroll_do_not_count(self):
        page = self.page(touch=True, height=600)
        cdp = page.context.new_cdp_session(page)
        for kind in ["multitouch", "cancel", "scroll"]:
            with self.subTest(kind=kind):
                page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
                page.wait_for_timeout(80)
                bounds = page.locator(".page-subtitle").bounding_box()
                x, y = bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2
                first = {"x": x, "y": y, "id": 1}
                cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [first]})
                if kind == "multitouch":
                    second = {"x": x + 50, "y": y, "id": 2}
                    cdp.send("Input.dispatchTouchEvent", {"type": "touchStart", "touchPoints": [first, second]})
                    # Exercise an actual outward pinch as well as two contacts.
                    for spread in [15, 30, 45]:
                        cdp.send("Input.dispatchTouchEvent", {
                            "type": "touchMove", "touchPoints": [
                                {"x": x - spread, "y": y, "id": 1},
                                {"x": x + 50 + spread, "y": y, "id": 2}]})
                    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
                    page.wait_for_timeout(80)
                    self.assertEqual(page.evaluate("visualViewport.scale"), 1)
                elif kind == "cancel":
                    cdp.send("Input.dispatchTouchEvent", {"type": "touchCancel", "touchPoints": []})
                else:
                    for offset in [20, 40, 70, 100]:
                        cdp.send("Input.dispatchTouchEvent", {"type": "touchMove", "touchPoints": [{"x": x, "y": y - offset, "id": 1}]})
                    cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
                    self.wait(page, "() => window.scrollY > 0")
                page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
                page.wait_for_timeout(120)
                self.assert_opens_on_tenth(page, touch=True)
                self.close(page)
        cdp.detach()

    def test_heart_opens_on_tenth_and_other_functional_buttons_reset_chain(self):
        page = self.page(width=1440, height=1100)
        # The heart preserves its message behavior and also triggers the letter.
        initial_message = page.locator("#heart-message").inner_text()
        page.locator("#heart").click()
        self.assertNotEqual(page.locator("#heart-message").inner_text(), initial_message)
        for _ in range(8):
            page.locator("#heart").click()
        self.assertFalse(self.is_open(page))
        page.locator("#heart").click()
        self.wait(page, "() => document.querySelector('#secret-dialog').open")
        self.wait(page, "() => !document.querySelector('#secret-password').disabled")
        self.assertEqual(self.paths.count("/api/session"), 1)
        self.assertEqual(page.locator("#secret-dialog").count(), 1)
        self.close(page)
        self.taps(page, 9)
        page.locator('[data-profile="tuan"]').click()
        self.assertTrue(page.locator("#profile-dialog").evaluate("e => e.open"))
        self.assertEqual(page.locator("#profile-name").inner_text(), "Lê Anh Tuấn")
        self.assertFalse(self.is_open(page))
        for _ in range(10):
            page.locator("#profile-name").click()
        page.keyboard.press("Escape")
        self.wait(page, "() => !document.querySelector('#profile-dialog').open")
        self.assert_opens_on_tenth(page)
        self.close(page)
        self.taps(page, 9)
        page.locator("#music-toggle").click()
        self.wait(page, "() => !document.querySelector('#love-audio').paused")
        self.assertEqual(page.locator("#music-toggle").get_attribute("aria-pressed"), "true")
        self.assert_opens_on_tenth(page)
        self.close(page)
        page.locator("#music-toggle").click()
        self.wait(page, "() => document.querySelector('#love-audio').paused")

    def test_links_forms_editables_and_explicit_ignore_zones_do_not_count(self):
        page = self.page(width=1440, height=1100)
        page.locator("#wrapper").evaluate("""wrapper => {
            const fixture = document.createElement('div');
            fixture.id = 'gesture-test-controls';
            fixture.innerHTML = '<a href="#gesture-test-controls">Link</a><form><label>Label<input aria-label="test input"></label><textarea aria-label="test textarea"></textarea></form><div role="button" tabindex="0">Role button</div><div contenteditable="true">Editable</div><nav>Navigation</nav><div data-secret-ignore>Ignored region</div>';
            wrapper.prepend(fixture);
        }""")
        for selector in ["a", "label", "input", "textarea", "[role=button]", "[contenteditable]", "nav", "[data-secret-ignore]"]:
            with self.subTest(selector=selector):
                page.locator("#gesture-test-controls " + selector).click()
                self.assert_opens_on_tenth(page)
                self.close(page)

    def test_repository_subpath_loads_assets_and_keeps_session_api_in_mount(self):
        page = self.page(prefix="/love/", width=390)
        self.assertEqual(page.evaluate("document.styleSheets.length"), 4)
        self.assertGreater(float(page.locator("#heart").evaluate("e => getComputedStyle(e).width").replace("px", "")), 20)
        self.assert_opens_on_tenth(page)
        self.wait(page, "() => !document.querySelector('#secret-password').disabled")
        self.assertIn("/love/api/session", self.paths)
        self.assertNotIn("/api/session", self.paths)
        page.locator("#secret-password").fill(self.password)
        page.locator("#secret-auth-submit").click()
        self.wait(page, "() => !document.querySelector('#secret-workspace').hidden")
        self.wait(page, "() => !!document.querySelector('#secret-list-summary').textContent")
        self.assertIn("/love/api/auth", self.paths)
        self.assertIn("/love/api/letters", self.paths)
        failures = [(path, status) for path, status in self.responses if status >= 400 and path.startswith("/love/")]
        self.assertEqual(failures, [])
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))


if __name__ == "__main__":
    unittest.main()
