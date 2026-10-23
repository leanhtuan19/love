"""Journal/settings browser flows using random credentials and temporary storage."""
import io
import json
import os
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest import mock

from PIL import Image
from werkzeug.security import generate_password_hash

import test_browser as helpers
from site_features import setup_admins


@unittest.skipIf(helpers.sync_playwright is None, "Install Playwright to run browser checks")
class FeatureBrowserTests(unittest.TestCase):
    setUpClass = classmethod(helpers.BrowserTests.setUpClass.__func__)
    tearDownClass = classmethod(helpers.BrowserTests.tearDownClass.__func__)
    tearDown = helpers.BrowserTests.tearDown
    wait = helpers.BrowserTests.wait
    page = helpers.BrowserTests.page

    def setUp(self):
        helpers.BrowserTests.setUp(self)
        self.admin_user = "manager_" + secrets.token_hex(6)
        self.admin_password = secrets.token_urlsafe(20)
        self.journal_password = secrets.token_urlsafe(20)
        with mock.patch.dict(os.environ, {
            "LOVEDAYS_ADMIN_1_USERNAME": self.admin_user,
            "LOVEDAYS_ADMIN_1_PASSWORD": self.admin_password,
            "LOVEDAYS_ADMIN_2_USERNAME": "other_" + secrets.token_hex(6),
            "LOVEDAYS_ADMIN_2_PASSWORD": secrets.token_urlsafe(20),
        }):
            setup_admins(self.app)
        with self.app.extensions["auth_store"].transaction() as database:
            database.execute("INSERT INTO settings(key,value) VALUES('journal_password_hash',?)",
                             (generate_password_hash(self.journal_password, method="scrypt:32768:8:1"),))

    def login_admin(self, page):
        page.locator("#admin-settings-toggle").click()
        page.locator(".admin-login [name=username]").fill(self.admin_user)
        page.locator(".admin-login [name=password]").fill(self.admin_password)
        page.locator(".admin-login button[type=submit]").click()
        self.wait(page, "() => !!document.querySelector('.admin-group')")

    def group(self, page, label):
        group = page.locator(".admin-group").filter(has=page.locator("summary", has_text=label))
        if not group.evaluate("e => e.open"):
            group.locator("summary").click()
        return group

    def test_admin_live_content_profiles_and_credential_reauthentication(self):
        page = self.page(width=320, height=740, touch=True)
        self.login_admin(page)
        profiles = page.locator("form[data-group=profiles]")
        profiles.locator("[name=tuan__displayName]").fill("Người thương")
        profiles.locator("[name=tuan__name]").fill("Tên tiếng Việt đã thay đổi")
        profiles.locator("button[type=submit]").click()
        self.wait(page, "() => document.querySelector('[data-profile=tuan] .name').textContent === 'Người thương'")
        content = self.group(page, "Nội dung website")
        content.locator("[name=heading]").fill("Một câu chuyện mới")
        content.locator("[name=anniversary]").fill("2025-01-02")
        content.locator("[name=heartMessages]").fill("Một lời nhắn mới\nMột lời thương nữa")
        content.locator("button[type=submit]").click()
        self.wait(page, "() => document.querySelector('.page-header h1').textContent === 'Một câu chuyện mới'")
        self.assertEqual(page.locator("#anniversary").get_attribute("datetime"), "2025-01-02")
        accounts = self.group(page, "Tài khoản quản trị")
        form = accounts.locator("form").filter(has=page.locator("h3", has_text=self.admin_user))
        form.locator("[name=username]").fill("renamed_" + secrets.token_hex(5))
        form.locator("[name=currentPassword]").fill("incorrect-test-password")
        form.locator("button[type=submit]").click()
        self.wait(page, "() => [...document.querySelectorAll('.admin-account-form .journal-status')].some(e => e.classList.contains('is-error'))")
        self.assertTrue(page.locator(".admin-group").count())
        form.locator("[name=currentPassword]").fill(self.admin_password)
        form.locator("button[type=submit]").click()
        self.wait(page, "() => !!document.querySelector('.admin-login')")
        self.assertEqual(page.locator(".admin-login [name=password]").input_value(), "")
        page.locator("#admin-dialog [data-journal-close]").click()
        page.locator("[data-profile=tuan]").click()
        self.assertEqual(page.locator("#profile-name").inner_text(), "Tên tiếng Việt đã thay đổi")
        page.keyboard.press("Escape")
        page.locator("#heart").click()
        self.assertIn(page.locator("#heart-message .status-visual").inner_text(), ["Một lời nhắn mới", "Một lời thương nữa"])
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))

    def test_journal_location_images_password_history_delete_and_search(self):
        page = self.page(width=390, height=844, touch=True)
        page.context.grant_permissions(["geolocation"], origin=self.origin)
        page.context.set_geolocation({"latitude": 18.35, "longitude": 105.90})
        page.locator("#journal-new").click()
        form = page.locator("#journal-compose")
        form.locator("[name=authorName]").fill("Người viết thử")
        form.locator("[name=title]").fill("Kỷ niệm Hà Tĩnh")
        form.locator("[name=content]").fill("Dòng đầu tiên.\nDòng thứ hai có dấu.")
        form.get_by_role("button", name="Lấy vị trí hiện tại").click()
        self.wait(page, "() => !!document.querySelector('#journal-compose [name=latitude]').value")
        form.locator("[name=locationLabel]").fill("Một góc Hà Tĩnh")
        buffer = io.BytesIO()
        Image.new("RGB", (40, 30), "pink").save(buffer, format="PNG")
        form.locator("[name=images]").set_input_files([
            {"name": "ky-niem.png", "mimeType": "image/png", "buffer": buffer.getvalue()},
        ])
        self.assertEqual(page.locator(".journal-preview").count(), 1)
        form.locator("button[type=submit]").click()
        self.wait(page, "() => !!document.querySelector('.journal-inline-auth input[type=password]')")
        self.assertEqual(form.locator("[name=content]").input_value(), "Dòng đầu tiên.\nDòng thứ hai có dấu.")
        page.locator(".journal-inline-auth [name=password]").fill(self.password)
        page.locator(".journal-inline-auth button[type=submit]").click()
        self.wait(page, "() => !document.querySelector('.journal-inline-auth input[type=password]')")
        form.locator("button[type=submit]").click()
        self.wait(page, "() => !!document.querySelector('.journal-post-content')")
        self.assertEqual(page.locator(".journal-post-content").inner_text(), "Dòng đầu tiên.\nDòng thứ hai có dấu.")
        page.locator(".journal-gallery .journal-image-button").click()
        self.assertTrue(page.locator("#journal-image-dialog").evaluate("e => e.open"))
        page.locator("#journal-image-dialog [data-journal-close]").click()
        page.locator("#journal-dialog").get_by_role("button", name="Chỉnh sửa", exact=True).click()
        edit = page.locator("#journal-compose")
        edit.locator("[name=title]").fill("Kỷ niệm đã sửa")
        edit.locator("[name=password]").fill("wrong-journal-password")
        edit.locator("button[type=submit]").click()
        self.wait(page, "() => document.querySelector('#journal-dialog-status').classList.contains('is-error')")
        self.assertEqual(edit.locator("[name=title]").input_value(), "Kỷ niệm đã sửa")
        self.assertEqual(edit.locator("[name=password]").input_value(), "")
        edit.locator("[name=password]").fill(self.journal_password)
        edit.locator("button[type=submit]").click()
        self.wait(page, "() => document.querySelector('#journal-dialog-title').textContent === 'Kỷ niệm đã sửa'")
        page.locator("#journal-dialog [data-journal-close]").click()
        page.locator("#journal-search [name=q]").fill("ky niem")
        page.locator("#journal-search button[type=submit]").click()
        self.wait(page, "() => document.querySelectorAll('.journal-card').length === 1")
        page.locator("#journal-history").click()
        page.locator("#journal-history-body [name=password]").fill(self.journal_password)
        page.locator("#journal-history-body button[type=submit]").click()
        self.wait(page, "() => !!document.querySelector('.journal-history-entry')")
        page.locator(".journal-history-diff summary").first.click()
        self.assertIn("Kỷ niệm", page.locator("#journal-history-body").inner_text())
        page.locator("#journal-history-dialog [data-journal-close]").click()
        page.locator(".journal-view").click()
        page.locator("#journal-dialog").get_by_role("button", name="Xóa bài", exact=True).click()
        page.locator("#journal-dialog-body [name=password]").fill(self.journal_password)
        page.locator("#journal-dialog-body button[type=submit]").click()
        self.wait(page, "() => !document.querySelector('#journal-dialog').open && document.querySelectorAll('.journal-card').length === 0")
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        page.screenshot(path=str(Path(tempfile.gettempdir()) / "lovedays-journal-mobile.png"), full_page=True)

    def test_geolocation_denied_keeps_manual_location_and_bootstrap_is_safe(self):
        with self.app.extensions["auth_store"].transaction() as database:
            row = database.execute("SELECT value FROM site_settings WHERE group_name='content'").fetchone()
            content = json.loads(row[0])
            content["heading"] = "</script><script>window.injected=true</script>"
            database.execute("UPDATE site_settings SET value=? WHERE group_name='content'", (json.dumps(content, ensure_ascii=False),))
        page = self.page(width=320, height=740)
        self.assertFalse(page.evaluate("Boolean(window.injected)"))
        self.assertEqual(page.locator(".page-header h1").inner_text(), content["heading"])
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        page.locator("#journal-new").click()
        page.evaluate("() => { navigator.geolocation.getCurrentPosition = (success, failure) => failure({code: 1}); }")
        page.get_by_role("button", name="Lấy vị trí hiện tại").click()
        self.wait(page, "() => [...document.querySelectorAll('.journal-help')].some(e => e.textContent.includes('bị từ chối'))")
        location = page.locator("#journal-compose [name=locationLabel]")
        location.fill("Địa điểm nhập thủ công")
        self.assertEqual(location.input_value(), "Địa điểm nhập thủ công")
        self.assertEqual(page.locator("#journal-compose [name=latitude]").input_value(), "")


if __name__ == "__main__":
    unittest.main()
