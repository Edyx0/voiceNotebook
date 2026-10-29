import asyncio
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from notebook_uploads import browser_storage, click_upload_control, configure_file_uploads, upload_in_browser


class BrowserFileUploadTests(unittest.TestCase):
    def test_late_google_announcement_is_closed_before_upload_control_is_retried(self):
        from playwright.async_api import TimeoutError
        control = SimpleNamespace(click=AsyncMock(side_effect=[TimeoutError('covered'), None]))
        close = SimpleNamespace(click=AsyncMock())
        buttons = Mock()
        buttons.last = close
        page = SimpleNamespace(get_by_role=Mock(side_effect=[
            SimpleNamespace(is_visible=AsyncMock(return_value=True)), buttons]))
        asyncio.run(click_upload_control(page, control))
        self.assertEqual(control.click.await_count, 2)
        close.click.assert_awaited_once()

    def test_unknown_upload_blocker_is_not_dismissed(self):
        from playwright.async_api import TimeoutError
        control = SimpleNamespace(click=AsyncMock(side_effect=TimeoutError('unknown blocker')))
        page = SimpleNamespace(get_by_role=Mock(return_value=SimpleNamespace(is_visible=AsyncMock(return_value=False))))
        with self.assertRaises(TimeoutError):
            asyncio.run(click_upload_control(page, control))
        self.assertEqual(control.click.await_count, 1)

    def test_safari_unspecified_cookie_policy_survives_chromium_import(self):
        import json
        state = {'cookies': [
            {'name': 'SID', 'secure': False, 'sameSite': 'None'},
            {'name': '__Secure-1PSID', 'secure': True, 'sameSite': 'None'},
        ]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'session.json'
            path.write_text(json.dumps(state))
            loaded = browser_storage(path)
            self.assertEqual(loaded['cookies'][0]['sameSite'], 'Lax')
            self.assertEqual(loaded['cookies'][1]['sameSite'], 'None')
            self.assertEqual(json.loads(path.read_text()), state)

    def test_browser_upload_returns_the_registered_source_and_preserves_readiness_wait(self):
        source = SimpleNamespace(id='registered')
        ready = SimpleNamespace(id='registered', is_ready=True)
        client = SimpleNamespace(sources=SimpleNamespace(_uploader=object(),
                                 wait_until_ready=AsyncMock(return_value=ready)))
        configure_file_uploads(client)
        with patch('notebook_uploads.upload_in_browser', new_callable=AsyncMock, return_value=source) as upload:
            self.assertIs(asyncio.run(client.sources.add_file('notebook', 'class.mp3')), source)
            upload.assert_awaited_once_with(client, 'notebook', 'class.mp3')
            self.assertIs(asyncio.run(client.sources.add_file('notebook', 'class.mp3', wait=True, wait_timeout=90)), ready)
        client.sources.wait_until_ready.assert_awaited_once_with('notebook', 'registered', timeout=90)

    def test_uncertain_browser_upload_is_not_replayed(self):
        client = SimpleNamespace(sources=SimpleNamespace(_uploader=object()))
        configure_file_uploads(client)
        with patch('notebook_uploads.upload_in_browser', new_callable=AsyncMock,
                   side_effect=ValueError('Upload response uncertain')) as upload:
            with self.assertRaisesRegex(ValueError, 'uncertain'):
                asyncio.run(client.sources.add_file('notebook', 'class.mp3'))
            self.assertEqual(upload.await_count, 1)

    def test_invalid_file_does_not_open_a_browser(self):
        with self.assertRaises(FileNotFoundError):
            asyncio.run(upload_in_browser(None, 'notebook', '/missing/voiceNotebook-test.mp3'))
