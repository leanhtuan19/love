"""Real Chromium mailbox UI with isolated data and controlled server time."""
import time
import unittest

import test_browser as browser_helpers


@unittest.skipIf(browser_helpers.sync_playwright is None, "Install playwright for browser checks")
class MailboxUITests(unittest.TestCase):
    setUpClass = classmethod(browser_helpers.BrowserTests.setUpClass.__func__)
    tearDownClass = classmethod(browser_helpers.BrowserTests.tearDownClass.__func__)
    setUp = browser_helpers.BrowserTests.setUp
    tearDown = browser_helpers.BrowserTests.tearDown
    page = browser_helpers.BrowserTests.page
    wait = browser_helpers.BrowserTests.wait
    gate = browser_helpers.BrowserTests.gate
    tap_page = staticmethod(browser_helpers.BrowserTests.tap_page)
    login = browser_helpers.BrowserTests.login

    @staticmethod
    def visibility(page, hidden):
        # Lifecycle events are simulated; input still uses native Playwright
        # mouse/keyboard and server clocks exercise actual durable expiration.
        page.evaluate("""hidden => {
          Object.defineProperty(document, 'hidden', {configurable:true, value:hidden});
          document.dispatchEvent(new Event('visibilitychange'));
        }""", hidden)

    def test_idle_resume_masks_content_then_requires_password_and_keeps_draft(self):
        page = self.page()
        self.login(page)
        page.locator("#secret-new").click()
        page.locator("#secret-title").fill("Bản nháp giữ trong bộ nhớ")
        page.locator("#secret-content").fill("Nội dung riêng tư chưa lưu")
        self.visibility(page, True)
        self.assertTrue(page.locator("#secret-workspace").is_hidden())
        self.clock[0] += 301
        self.visibility(page, False)
        self.wait(page, "() => !document.querySelector('#secret-password').disabled && document.querySelector('#secret-workspace').hidden && document.querySelector('#secret-auth-status').textContent.includes('Phiên đã hết hạn')")
        self.assertEqual(page.locator("#secret-content").input_value(), "")
        self.assertEqual(page.context.request.get(self.origin + "/api/letters").status, 401)
        page.locator("#secret-password").fill(self.password)
        page.locator("#secret-auth-submit").click()
        self.wait(page, "() => !document.querySelector('#secret-compose').hidden")
        self.assertEqual(page.locator("#secret-title").input_value(), "Bản nháp giữ trong bộ nhớ")
        self.assertEqual(page.locator("#secret-content").input_value(), "Nội dung riêng tư chưa lưu")

    def test_close_reopen_before_thirty_seconds_never_cancels_deadline(self):
        page = self.page(touch=True)
        self.login(page)
        page.locator("#secret-close").tap()
        self.wait(page, "() => !document.querySelector('#secret-dialog').open")
        self.gate(page)
        self.wait(page, "() => !document.querySelector('#secret-workspace').hidden")
        state = page.context.request.get(self.origin + "/api/session").json()
        self.assertTrue(state["authenticated"])
        self.assertIsNotNone(state["closeExpiresAt"])
        self.clock[0] += 29
        self.assertEqual(page.context.request.get(self.origin + "/api/letters").status, 200)
        page.locator("#secret-close").tap()
        self.gate(page)
        self.wait(page, "() => !document.querySelector('#secret-workspace').hidden")
        self.assertEqual(page.context.request.get(self.origin + "/api/session").json()["closeExpiresAt"], state["closeExpiresAt"])
        self.clock[0] += 1
        self.visibility(page, True)
        self.visibility(page, False)
        self.wait(page, "() => document.querySelector('#secret-workspace').hidden && !document.querySelector('#secret-password').disabled")
        self.assertEqual(page.context.request.get(self.origin + "/api/letters").status, 401)

    def test_lock_icon_revokes_both_tabs_and_has_accessible_touch_target(self):
        first = self.page(width=430, touch=True)
        self.login(first)
        icon = first.locator("#secret-logout")
        self.assertEqual(icon.get_attribute("aria-label"), "Khóa hòm thư")
        self.assertEqual(icon.get_attribute("title"), "Khóa hòm thư")
        bounds = icon.bounding_box()
        self.assertGreaterEqual(bounds["width"], 44)
        self.assertGreaterEqual(bounds["height"], 44)
        second = first.context.new_page()
        second.route("https://graph.facebook.com/**", lambda route: route.abort())
        second.on("pageerror", lambda error: self.page_errors.append(str(error)))
        second.goto(self.origin, wait_until="domcontentloaded")
        self.wait(second, "() => !document.querySelector('#love-loader') && !!document.querySelector('#secret-dialog')")
        self.gate(second)
        self.wait(second, "() => !document.querySelector('#secret-workspace').hidden")
        second.locator("#secret-logout").tap()
        self.wait(second, "() => document.querySelector('#secret-workspace').hidden && !document.querySelector('#secret-password').disabled")
        first.bring_to_front()
        first.evaluate("() => window.dispatchEvent(new Event('focus'))")
        self.wait(first, "() => document.querySelector('#secret-workspace').hidden && !document.querySelector('#secret-password').disabled")
        self.assertEqual(first.context.request.get(self.origin + "/api/letters").status, 401)

    def test_reload_retains_server_deadline_and_timer_locks_without_background_renewal(self):
        page = self.page(width=1280)
        self.login(page)
        idle_at = page.context.request.get(self.origin + "/api/session").json()["idleExpiresAt"]
        self.clock[0] += 100
        page.reload(wait_until="domcontentloaded")
        self.wait(page, "() => !document.querySelector('#love-loader') && !!document.querySelector('#secret-dialog')")
        self.gate(page)
        self.wait(page, "() => !document.querySelector('#secret-workspace').hidden")
        state = page.context.request.get(self.origin + "/api/session").json()
        self.assertEqual(state["idleExpiresAt"], idle_at)
        self.assertEqual(state["expiresIn"], 200)
        # A short test-only policy runs the same timer path without waiting 5m.
        self.app.config["TIME_PROVIDER"] = time.time
        self.app.extensions["site_settings_reader"] = lambda: {"mailboxIdleSeconds": 2, "mailboxCloseSeconds": 1}
        page.locator("#secret-logout").click()
        self.wait(page, "() => !document.querySelector('#secret-password').disabled")
        page.locator("#secret-password").fill(self.password)
        page.locator("#secret-auth-submit").click()
        self.wait(page, "() => !document.querySelector('#secret-workspace').hidden")
        self.wait(page, "() => document.querySelector('#secret-workspace').hidden && !document.querySelector('#secret-password').disabled && document.querySelector('#secret-auth-status').textContent.includes('Phiên đã hết hạn')", timeout=6)
        self.assertEqual(page.context.request.get(self.origin + "/api/letters").status, 401)

    def test_only_trusted_mailbox_input_sends_throttled_activity(self):
        page = self.page()
        self.login(page)
        requests = []
        page.on("request", lambda item: requests.append(item.url) if item.url.endswith("/api/activity") else None)
        initial = page.context.request.get(self.origin + "/api/session").json()["idleExpiresAt"]
        self.clock[0] += 120
        page.evaluate("""() => {
          document.querySelector('#secret-workspace').dispatchEvent(new WheelEvent('wheel', {bubbles:true}));
          document.querySelector('#secret-workspace').dispatchEvent(new Event('scroll', {bubbles:true}));
          window.dispatchEvent(new Event('focus'));
        }""")
        page.wait_for_timeout(150)
        self.assertEqual(requests, [])
        self.assertEqual(page.context.request.get(self.origin + "/api/session").json()["idleExpiresAt"], initial)
        self.wait(page, "() => !document.querySelector('#secret-workspace').hidden")
        page.locator("#secret-new").click()
        page.locator("#secret-title").fill("Tương tác thực tế")
        self.wait(page, "() => !document.querySelector('#secret-compose').hidden")
        page.wait_for_timeout(1300)
        self.assertEqual(len(requests), 1)
        current = page.context.request.get(self.origin + "/api/session").json()
        self.assertEqual(current["expiresIn"], 300)
        self.assertNotEqual(current["idleExpiresAt"], initial)


if __name__ == "__main__":
    unittest.main()
