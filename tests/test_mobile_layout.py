"""Chromium mobile layout regressions, isolated from real credentials and data.

VisualViewport/keyboard events and enlarged text are simulated. These checks do
not claim to reproduce Safari's native keyboard or physical touch behavior.
"""
import io
import json
import unittest

import test_browser as browser_helpers
import test_features_browser as feature_helpers


@unittest.skipIf(browser_helpers.sync_playwright is None, "Install Playwright for layout checks")
class MobileLayoutTests(unittest.TestCase):
    setUpClass = classmethod(browser_helpers.BrowserTests.setUpClass.__func__)
    tearDownClass = classmethod(browser_helpers.BrowserTests.tearDownClass.__func__)
    setUp = feature_helpers.FeatureBrowserTests.setUp
    tearDown = browser_helpers.BrowserTests.tearDown
    wait = browser_helpers.BrowserTests.wait
    login_admin = feature_helpers.FeatureBrowserTests.login_admin
    group = feature_helpers.FeatureBrowserTests.group
    gate = browser_helpers.BrowserTests.gate
    tap_page = staticmethod(browser_helpers.BrowserTests.tap_page)
    login = browser_helpers.BrowserTests.login
    picture = staticmethod(browser_helpers.BrowserTests.picture)

    def page(self, width=390, height=844, mobile=True, mock_viewport=False, no_visual_viewport=False):
        context = self.browser.new_context(
            viewport={"width": width, "height": height}, has_touch=mobile,
            is_mobile=mobile, reduced_motion="reduce")
        self.contexts.append(context)
        if no_visual_viewport:
            context.add_init_script("Object.defineProperty(window,'visualViewport',{configurable:true,value:undefined});")
        if mock_viewport:
            context.add_init_script("""(() => {
              const viewport = new EventTarget();
              Object.assign(viewport, {width:innerWidth, height:innerHeight,
                offsetTop:0, offsetLeft:0, scale:1});
              Object.defineProperty(window, 'visualViewport', {configurable:true, value:viewport});
              window.__setVisualViewport = values => {
                Object.assign(viewport, values);
                viewport.dispatchEvent(new Event('resize'));
                viewport.dispatchEvent(new Event('scroll'));
              };
            })();""")
        page = context.new_page()
        page.route("https://graph.facebook.com/**", lambda route: route.abort())
        page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        page.goto(self.origin, wait_until="domcontentloaded")
        self.wait(page, "() => !document.querySelector('#love-loader') && !!document.querySelector('#secret-dialog') && !!document.querySelector('#journal-new')")
        return page

    def assert_fields(self, page, selector):
        fields = page.locator(selector).evaluate("""root => [...root.querySelectorAll(
          'input:not([type=hidden]),textarea,select,[contenteditable=true]')]
          .filter(e => e.getClientRects().length && !e.closest('[hidden]'))
          .map(e => ({name:e.name || e.id, font:parseFloat(getComputedStyle(e).fontSize),
            transform:getComputedStyle(e).transform}))""")
        self.assertTrue(fields, selector + " should contain editable fields")
        self.assertEqual([item for item in fields if item["font"] < 16], [], fields)
        self.assertEqual([item for item in fields if item["transform"] != "none"], [], fields)

    def assert_bounds(self, page, selector, close=None):
        geometry = page.locator(selector).evaluate("""e => {
          const r=e.getBoundingClientRect(), v=window.visualViewport;
          const rect={left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height};
          return {rect, viewport:{left:v?.offsetLeft || 0,top:v?.offsetTop || 0,
            width:v?.width || innerWidth,height:v?.height || innerHeight},
            scrollWidth:e.scrollWidth,clientWidth:e.clientWidth,
            docWidth:document.documentElement.scrollWidth,windowWidth:innerWidth};
        }""")
        rect, viewport = geometry["rect"], geometry["viewport"]
        self.assertGreaterEqual(rect["left"], viewport["left"] - 1, geometry)
        self.assertLessEqual(rect["right"], viewport["left"] + viewport["width"] + 1, geometry)
        self.assertGreaterEqual(rect["top"], viewport["top"] - 1, geometry)
        self.assertLessEqual(rect["bottom"], viewport["top"] + viewport["height"] + 1, geometry)
        self.assertLessEqual(geometry["scrollWidth"], geometry["clientWidth"] + 1, geometry)
        self.assertLessEqual(geometry["docWidth"], geometry["windowWidth"] + 1, geometry)
        if close:
            button = page.locator(close).bounding_box()
            self.assertIsNotNone(button)
            self.assertGreaterEqual(button["y"], viewport["top"] - 1, (button, geometry))
            self.assertLessEqual(button["y"] + button["height"], viewport["top"] + viewport["height"] + 1, (button, geometry))
            self.assertGreaterEqual(button["width"], 40)
            self.assertGreaterEqual(button["height"], 40)

    def seed_journal(self):
        with self.app.test_client() as client:
            csrf = client.get("/api/session").json["csrfToken"]
            response = client.post("/api/auth", json={"password": self.password}, headers={"Origin": "http://localhost", "X-CSRF-Token": csrf})
            self.assertEqual(response.status_code, 200)
            csrf = client.get("/api/session").json["csrfToken"]
            response = client.post("/api/journal", data={
                "payload": json.dumps({"authorName": "Tác giả " + "Tên" * 20,
                    "title": "Kỷ niệm " + "Dài" * 40,
                    "content": ("Dòng tiếng Việt có dấu\n" + "https://example.com/" + "x" * 350 + "\n") * 16,
                    "location": {"label": "Địa điểm " + "Dài" * 40, "latitude": None, "longitude": None}}),
                "images": [(io.BytesIO(self.picture(color)), "anh-" + color + ".png") for color in ["pink", "red", "white"]],
            }, headers={"Origin": "http://localhost", "X-CSRF-Token": csrf}, content_type="multipart/form-data")
            self.assertEqual(response.status_code, 201, response.json)
            return response.json["post"]

    def test_all_representative_widths_and_landscape_keep_fields_and_popups_inside(self):
        page = self.page(width=320, height=740)
        self.assertEqual(page.locator('meta[name=viewport]').count(), 1)
        viewports = [(w, 844) for w in (320, 360, 375, 390, 414, 430, 768)] + [(844, 390), (740, 320)]
        for width, height in viewports:
            with self.subTest(width=width, height=height):
                page.set_viewport_size({"width": width, "height": height})
                page.wait_for_timeout(80)
                self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), width + 1)
                self.assert_fields(page, "#journal-search")
                page.locator("[data-profile=tuan]").click()
                page.locator("#profile-name").evaluate("e => e.textContent = 'LêAnhTuấn'.repeat(35)")
                self.assert_bounds(page, "#profile-dialog", "#profile-close")
                page.locator("#profile-dialog").evaluate("e => e.scrollTop=e.scrollHeight")
                self.assert_bounds(page, "#profile-dialog", "#profile-close")
                page.locator("#profile-close").click()
                page.locator("#journal-new").click()
                page.locator('#journal-compose [name=content]').fill("TiếngViệtKhôngKhoảngTrắng" * 150)
                self.assert_fields(page, "#journal-dialog")
                self.assert_bounds(page, "#journal-dialog", "#journal-dialog [data-journal-close]")
                page.locator("#journal-dialog").evaluate("e => e.scrollTop=e.scrollHeight")
                self.assert_bounds(page, "#journal-dialog", "#journal-dialog [data-journal-close]")
                page.locator("#journal-dialog [data-journal-close]").click()
                page.locator("#admin-settings-toggle").click()
                self.wait(page, "() => !!document.querySelector('.admin-login')")
                self.assert_fields(page, "#admin-dialog")
                self.assert_bounds(page, "#admin-dialog", "#admin-dialog [data-journal-close]")
                page.locator("#admin-dialog [data-journal-close]").click()
        desktop = self.page(width=1280, height=900, mobile=False)
        desktop.emulate_media(reduced_motion="no-preference")
        self.assertLessEqual(desktop.evaluate("document.documentElement.scrollWidth"), 1280)
        desktop.locator("#journal-new").click()
        self.assertEqual(desktop.locator("#journal-dialog").evaluate("e => getComputedStyle(e).transform"), "none")
        self.assert_bounds(desktop, "#journal-dialog", "#journal-dialog [data-journal-close]")
        self.assertGreater(desktop.locator("#journal-dialog").bounding_box()["width"], 600)

    def test_mailbox_fields_images_and_nested_scroll_lock(self):
        page = self.page(width=320, height=740)
        self.login(page)
        self.assert_fields(page, "#secret-workspace")
        page.locator("#secret-new").click()
        page.locator("#secret-title").fill("Lá thư có dấu " + "TênDài" * 20)
        page.locator("#secret-content").fill(("https://example.com/" + "x" * 300 + "\n") * 14)
        page.locator("#secret-images").set_input_files([
            {"name": "anh-" + str(i) + ".png", "mimeType": "image/png", "buffer": self.picture()}
            for i in range(3)])
        self.assert_fields(page, "#secret-compose")
        self.assert_bounds(page, "#secret-dialog", "#secret-close")
        page.locator("#secret-save").click()
        self.wait(page, "() => !!document.querySelector('.secret-letter-content')")
        self.assert_bounds(page, "#secret-dialog", "#secret-close")
        page.locator(".secret-gallery-item").first.click()
        self.assert_bounds(page, "#secret-lightbox", "#secret-lightbox-close")
        self.assertEqual(page.evaluate("getComputedStyle(document.body).position"), "fixed")
        page.locator("#secret-lightbox-close").click()
        self.wait(page, "() => !document.querySelector('#secret-lightbox').open")
        self.assertEqual(page.evaluate("getComputedStyle(document.body).position"), "fixed")
        page.locator("#secret-close").click()
        self.wait(page, "() => !document.querySelector('#secret-dialog').open")
        self.assertNotEqual(page.evaluate("getComputedStyle(document.body).position"), "fixed")

    def test_real_journal_images_nested_dialogs_restore_scroll_across_cycles(self):
        self.seed_journal()
        page = self.page(width=375, height=812)
        self.wait(page, "() => document.querySelectorAll('.journal-card').length === 1")
        for _ in range(3):
            page.locator(".journal-view").scroll_into_view_if_needed()
            before = page.evaluate("scrollY")
            page.locator(".journal-view").click()
            self.wait(page, "() => !!document.querySelector('.journal-gallery')")
            self.assert_bounds(page, "#journal-dialog", "#journal-dialog [data-journal-close]")
            self.assertEqual(page.locator(".journal-gallery img").count(), 3)
            page.locator(".journal-gallery .journal-image-button").first.click()
            self.assert_bounds(page, "#journal-image-dialog", "#journal-image-dialog [data-journal-close]")
            self.assertEqual(page.evaluate("getComputedStyle(document.body).position"), "fixed")
            page.locator("#journal-image-dialog [data-journal-close]").click()
            self.assertEqual(page.evaluate("getComputedStyle(document.body).position"), "fixed")
            page.locator("#journal-dialog").evaluate("e => e.scrollTop=e.scrollHeight")
            self.assert_bounds(page, "#journal-dialog", "#journal-dialog [data-journal-close]")
            page.locator("#journal-dialog [data-journal-close]").click()
            self.wait(page, "() => getComputedStyle(document.body).position !== 'fixed'")
            self.assertAlmostEqual(page.evaluate("scrollY"), before, delta=2)
            self.assertFalse(page.evaluate("document.body.classList.contains('dialog-open')"))

    def test_visual_viewport_keyboard_resize_focus_and_rotation(self):
        page = self.page(width=390, height=844, mock_viewport=True)
        page.locator("#journal-new").click()
        page.evaluate("() => window.__setVisualViewport({height:350,offsetTop:80})")
        page.locator('#journal-compose [name=content]').focus()
        page.wait_for_timeout(220)
        self.assert_bounds(page, "#journal-dialog", "#journal-dialog [data-journal-close]")
        field = page.locator('#journal-compose [name=content]').bounding_box()
        self.assertGreaterEqual(field["y"], 140)
        self.assertLessEqual(field["y"] + field["height"], 414)
        page.locator('#journal-compose [name=title]').focus()
        page.wait_for_timeout(160)
        self.assert_bounds(page, "#journal-dialog", "#journal-dialog [data-journal-close]")
        title = page.locator('#journal-compose [name=title]').bounding_box()
        self.assertGreaterEqual(title["y"], 140)
        self.assertLessEqual(title["y"] + title["height"], 414)
        page.evaluate("() => window.__setVisualViewport({height:844,offsetTop:0})")
        page.wait_for_timeout(120)
        self.assert_bounds(page, "#journal-dialog", "#journal-dialog [data-journal-close]")
        page.set_viewport_size({"width": 844, "height": 390})
        page.evaluate("() => window.__setVisualViewport({width:844,height:220,offsetTop:25})")
        page.locator('#journal-compose [name=locationLabel]').focus()
        page.wait_for_timeout(220)
        self.assert_bounds(page, "#journal-dialog", "#journal-dialog [data-journal-close]")
        location = page.locator('#journal-compose [name=locationLabel]').bounding_box()
        self.assertGreaterEqual(location["y"], 85)
        self.assertLessEqual(location["y"] + location["height"], 229)
        page.evaluate("() => window.__setVisualViewport({width:844,height:390,offsetTop:0})")
        page.locator("#journal-dialog [data-journal-close]").click()
        page.locator("#admin-settings-toggle").click()
        self.wait(page, "() => !!document.querySelector('.admin-login')")
        page.evaluate("() => window.__setVisualViewport({height:200,offsetTop:40})")
        page.locator('.admin-login [name=password]').focus()
        page.wait_for_timeout(220)
        self.assert_bounds(page, "#admin-dialog", "#admin-dialog [data-journal-close]")
        self.assert_fields(page, "#admin-dialog")
        page.locator("#admin-dialog [data-journal-close]").click()
        self.assertNotEqual(page.evaluate("getComputedStyle(document.body).position"), "fixed")

    def test_dense_admin_forms_enlarged_text_and_unbroken_values(self):
        page = self.page(width=320, height=740)
        self.login_admin(page)
        page.locator(".admin-group").evaluate_all("items => items.forEach(e => e.open=true)")
        page.locator('[name=tuan__name]').fill("Tên" * 25)
        page.locator('[name=tuan__hobbies]').fill("https://example.com/" + "a" * 800)
        page.locator('.admin-account-form [name=username]').first.fill("a" * 80)
        self.assert_fields(page, "#admin-dialog")
        self.assert_bounds(page, "#admin-dialog", "#admin-dialog [data-journal-close]")
        # Double the rendered sizes captured before any mutation: a user-style
        # simulation, not an assertion about physical OS text-size settings.
        page.locator("#admin-dialog").evaluate("""dialog => {
          const items=[...dialog.querySelectorAll('*')].filter(e =>
            e.matches('input,textarea,select,button') ||
            [...e.childNodes].some(n => n.nodeType===Node.TEXT_NODE && n.textContent.trim()));
          const sizes=items.map(e => parseFloat(getComputedStyle(e).fontSize));
          items.forEach((e,i) => e.style.setProperty('font-size',`${sizes[i]*2}px`,'important'));
        }""")
        for width, height in [(320, 740), (740, 320), (768, 1024)]:
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(100)
            page.locator("#admin-dialog").evaluate("e => e.scrollTop=e.scrollHeight")
            self.assert_bounds(page, "#admin-dialog", "#admin-dialog [data-journal-close]")
            self.assert_fields(page, "#admin-dialog")
        page.keyboard.press("Escape")
        self.wait(page, "() => !document.querySelector('#admin-dialog').open")
        self.assertNotEqual(page.evaluate("getComputedStyle(document.body).position"), "fixed")

    def test_without_visual_viewport_uses_layout_resize_fallback(self):
        page = self.page(width=390, height=844, no_visual_viewport=True)
        page.locator("#journal-new").click()
        for width, height in [(390, 360), (740, 320), (390, 844)]:
            page.set_viewport_size({"width": width, "height": height})
            page.locator('#journal-compose [name=content]').focus()
            page.wait_for_timeout(160)
            self.assert_bounds(page, "#journal-dialog", "#journal-dialog [data-journal-close]")
            self.assert_fields(page, "#journal-dialog")
        page.locator("#journal-dialog [data-journal-close]").click()
        self.wait(page, "() => getComputedStyle(document.body).position !== 'fixed'")
        self.assertEqual(page.evaluate("document.documentElement.style.getPropertyValue('--love-viewport-height')"), "")

    def test_browser_zoom_override_keeps_popup_usable(self):
        page = self.page(width=390, height=844)
        page.locator("#journal-new").click()
        session = page.context.new_cdp_session(page)
        session.send("Emulation.setPageScaleFactor", {"pageScaleFactor": 2})
        page.locator('#journal-compose [name=title]').focus()
        page.wait_for_timeout(220)
        self.assertAlmostEqual(page.evaluate("visualViewport.scale"), 2, delta=.05)
        self.assert_bounds(page, "#journal-dialog", "#journal-dialog [data-journal-close]")
        self.assert_fields(page, "#journal-dialog")
        session.send("Emulation.setPageScaleFactor", {"pageScaleFactor": 1})
        page.wait_for_timeout(160)
        page.locator("#journal-dialog [data-journal-close]").click()
        self.wait(page, "() => getComputedStyle(document.body).position !== 'fixed'")
        self.gate(page)
        session.send("Emulation.setPageScaleFactor", {"pageScaleFactor": 2})
        page.locator("#secret-password").focus()
        page.wait_for_timeout(220)
        self.assert_bounds(page, "#secret-dialog", "#secret-close")
        self.assert_fields(page, "#secret-dialog")
        session.send("Emulation.setPageScaleFactor", {"pageScaleFactor": 1})
        page.wait_for_timeout(120)
        page.locator("#secret-close").click()
        page.locator("[data-profile=tuan]").click()
        session.send("Emulation.setPageScaleFactor", {"pageScaleFactor": 2})
        page.wait_for_timeout(220)
        self.assert_bounds(page, "#profile-dialog", "#profile-close")
        session.send("Emulation.setPageScaleFactor", {"pageScaleFactor": 1})
        page.wait_for_timeout(120)
        page.locator("#profile-close").click()
        session.detach()


if __name__ == "__main__":
    unittest.main()
