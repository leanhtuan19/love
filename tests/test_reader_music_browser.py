"""Reader, stable recipient IDs and actual audio controls in isolated Chrome."""
import io
import json
from pathlib import Path
import unittest
import wave

from flask import send_file

import test_browser as helpers


@unittest.skipIf(helpers.sync_playwright is None, "Install Playwright for browser checks")
class ReaderMusicTests(unittest.TestCase):
    setUpClass = classmethod(helpers.BrowserTests.setUpClass.__func__)
    tearDownClass = classmethod(helpers.BrowserTests.tearDownClass.__func__)
    setUp = helpers.BrowserTests.setUp
    tearDown = helpers.BrowserTests.tearDown
    page = helpers.BrowserTests.page
    wait = helpers.BrowserTests.wait
    login = helpers.BrowserTests.login
    gate = helpers.BrowserTests.gate
    tap_page = staticmethod(helpers.BrowserTests.tap_page)

    def test_recipient_follows_stable_sender_ids_on_open_change_reset_and_server(self):
        with self.app.extensions['auth_store'].transaction() as database:
            profiles = json.loads(database.execute("SELECT value FROM site_settings WHERE group_name='profiles'").fetchone()[0])
            profiles['tuan']['name'] = 'Tên mới của người thứ nhất'
            profiles['thu']['name'] = 'Tên mới của người thứ hai'
            database.execute("UPDATE site_settings SET value=? WHERE group_name='profiles'", (json.dumps(profiles),))
        page = self.page(width=320, touch=True)
        self.login(page)
        page.locator('#secret-new').click()
        self.assertEqual(page.locator('#secret-sender').input_value(), 'tuan')
        self.assertEqual(page.locator('#secret-recipient').input_value(), 'thu')
        self.assertTrue(page.locator('#secret-recipient').is_disabled())
        page.locator('#secret-sender').select_option('thu')
        self.assertEqual(page.locator('#secret-recipient').input_value(), 'tuan')
        self.assertEqual(page.locator('#secret-sender-name').input_value(), profiles['thu']['name'])
        page.locator('#secret-compose-form').evaluate('form => form.reset()')
        self.wait(page, "() => document.querySelector('#secret-sender').value==='tuan' && document.querySelector('#secret-recipient').value==='thu'")
        csrf = page.context.request.get(self.origin + '/api/session').json()['csrfToken']
        response = page.context.request.post(self.origin + '/api/letters', data={
            'senderId': 'tuan', 'recipientId': 'tuan', 'senderName': 'Tên người viết',
            'title': 'Sai cặp', 'content': 'Không được gửi cho chính mình', 'type': 'message'},
            headers={'Origin': self.origin, 'X-CSRF-Token': csrf})
        self.assertEqual(response.status, 400)

    def test_reader_frames_preserve_lines_and_render_markup_as_text(self):
        page = self.page(width=320, touch=True)
        self.login(page)
        csrf = page.context.request.get(self.origin + '/api/session').json()['csrfToken']
        headers = {'Origin': self.origin, 'X-CSRF-Token': csrf}
        content = 'Dòng thứ nhất\n\nDòng thứ hai: <img src=x onerror="window.injected=true">\n' + 'KhôngKhoảngTrắng' * 60
        response = page.context.request.post(self.origin + '/api/letters', data={
            'senderId': 'tuan', 'recipientId': 'thu', 'senderName': 'Tên người viết',
            'title': 'Lá thư có khung', 'content': content, 'type': 'love-letter'}, headers=headers)
        self.assertEqual(response.status, 201)
        letter = response.json()['letter']
        response = page.context.request.post(self.origin + '/api/journal', data={
            'authorName': 'Tên người đăng rất dài ' * 3, 'title': 'Bài có khung',
            'content': content, 'location': {'label': '', 'latitude': None, 'longitude': None}}, headers=headers)
        self.assertEqual(response.status, 201)
        page.reload(wait_until='domcontentloaded')
        self.wait(page, "() => !!document.querySelector('#secret-dialog') && !!document.querySelector('.journal-view')")
        self.gate(page)
        self.wait(page, "() => !!document.querySelector('.secret-letter-row')")
        page.locator('[data-letter-id="' + letter['id'] + '"]').click()
        self.wait(page, "() => !!document.querySelector('.secret-letter-content')")
        for selector in ['.secret-letter-content']:
            self.assertEqual(page.locator(selector).inner_text(), content)
            self.assertTrue(page.locator(selector).evaluate("e => parseFloat(getComputedStyle(e).borderTopWidth)>0 && e.scrollWidth<=e.clientWidth"))
        page.locator('#secret-close').click()
        page.locator('.journal-view').click()
        self.wait(page, "() => !!document.querySelector('.journal-post-content')")
        self.assertEqual(page.locator('.journal-post-content').inner_text(), content)
        self.assertTrue(page.locator('.journal-post-content').evaluate("e => parseFloat(getComputedStyle(e).borderTopWidth)>0 && e.scrollWidth<=e.clientWidth"))
        self.assertEqual(page.locator('.journal-post-meta .journal-post-author').count(), 1)
        self.assertFalse(page.evaluate('Boolean(window.injected)'))
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'))

    def test_real_audio_play_pause_seek_mute_end_and_denied_play(self):
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as sample:
            sample.setnchannels(1)
            sample.setsampwidth(2)
            sample.setframerate(8000)
            sample.writeframes(b'\x00\x00' * 8000 * 4)
        sample_bytes = buffer.getvalue()
        self.app.add_url_rule('/main/music/controls-test.wav', 'test_audio',
            lambda: send_file(io.BytesIO(sample_bytes), mimetype='audio/wav', conditional=True))
        with self.app.extensions['auth_store'].transaction() as database:
            content = json.loads(database.execute("SELECT value FROM site_settings WHERE group_name='content'").fetchone()[0])
            content['musicSrc'] = 'main/music/controls-test.wav'
            database.execute("UPDATE site_settings SET value=? WHERE group_name='content'", (json.dumps(content),))
        page = self.page(width=320, touch=True)
        self.wait(page, "() => !document.querySelector('#love-audio-seek').disabled && document.querySelector('#love-audio').seekable.length>0")
        self.assertEqual(page.locator('#love-audio').count(), 1)
        self.assertEqual(page.locator('#love-audio-duration').inner_text(), '0:04')
        page.locator('#music-toggle').click()
        self.wait(page, "() => document.querySelector('#music').classList.contains('is-playing')")
        page.locator('#music-toggle').click()
        self.wait(page, "() => document.querySelector('#love-audio').paused")
        page.locator('#love-audio-seek').focus()
        page.keyboard.press('End')
        page.keyboard.press('ArrowLeft')
        self.wait(page, "() => document.querySelector('#love-audio').currentTime>3")
        page.locator('#love-audio-mute').click()
        self.assertTrue(page.locator('#love-audio').evaluate('audio => audio.muted'))
        self.assertEqual(page.locator('#love-audio-mute').get_attribute('aria-pressed'), 'true')
        page.evaluate("() => {const audio=document.querySelector('#love-audio'); audio.loop=false; audio.currentTime=3.85;}")
        page.locator('#music-toggle').click()
        self.wait(page, "() => document.querySelector('#love-audio').ended")
        self.assertEqual(page.locator('#music-toggle').get_attribute('aria-pressed'), 'false')
        page.evaluate("() => {document.querySelector('#love-audio').play=()=>Promise.reject(new DOMException('Blocked','NotAllowedError'));}")
        page.locator('#music-toggle').click()
        self.wait(page, "() => document.querySelector('#music-status').textContent.includes('chưa cho phép')")
        self.assertFalse(page.locator('#music-toggle').evaluate("e => e.getAttribute('aria-busy')==='true'"))
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth'))

    def test_private_letter_video_stops_on_edit_and_lock_revokes_access(self):
        page = self.page(width=320, touch=True)
        self.login(page)
        page.locator('#secret-new').click()
        page.locator('#secret-title').fill('Một video riêng tư')
        page.locator('#secret-content').fill('Nội dung riêng tư có video.\nGiữ nguyên xuống dòng.')
        page.locator('#secret-images').set_input_files(str(Path(__file__).parent / 'fixtures' / 'sample.webm'))
        page.locator('#secret-save').click()
        self.wait(page, "() => !!document.querySelector('.secret-video-item video')")
        video = page.locator('.secret-video-item video')
        media_url = video.get_attribute('src')
        video.evaluate("v => {window.previousPrivateVideo=v;v.muted=true;v.loop=true;v.play().catch(()=>{});}")
        self.wait(page, "() => window.previousPrivateVideo.currentTime>0")
        page.locator('.secret-letter-actions button').first.click()
        self.assertTrue(page.evaluate('window.previousPrivateVideo.paused'))
        page.locator('#secret-discard').click()
        self.wait(page, "() => !!document.querySelector('.secret-video-item video')")
        page.locator('#secret-logout').click()
        self.wait(page, "() => !document.querySelector('#secret-gate').hidden")
        self.wait(page, "() => document.querySelector('#secret-auth-status').textContent.includes('đã được khóa')")
        self.assertEqual(page.request.get(media_url).status, 401)
        self.assertEqual(page.locator('.secret-video-item').count(), 0)


if __name__ == '__main__':
    unittest.main()
