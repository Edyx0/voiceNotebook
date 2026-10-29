import asyncio
from contextlib import closing
import tempfile
import sqlite3
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import managed_signin


class ManagedSignInTests(unittest.TestCase):
    def run_capture(self, verify_error=None):
        context = MagicMock()
        page = context.pages.__getitem__.return_value
        page.url = 'https://notebook.google.com/?authuser=2'
        context.storage_state.return_value = {'cookies': [], 'origins': []}
        playwright = MagicMock()
        playwright.chromium.launch_persistent_context.return_value = context
        client = MagicMock()

        async def enter():
            if verify_error:
                raise verify_error
            return client

        async def leave(*args):
            pass

        async def notebooks():
            return []

        client.notebooks.list = notebooks
        session = MagicMock()
        session.__aenter__.side_effect = enter
        session.__aexit__.side_effect = leave
        with patch('managed_signin.interactive_login'), \
             patch('playwright.sync_api.sync_playwright') as pw, \
             patch('notebooklm._browser.browser_capture.wait_for_login_landing') as landing, \
             patch('notebooklm._browser.browser_capture.heal_captured_state', side_effect=lambda state: (state, None)), \
             patch('notebooklm._browser.browser_capture.filter_storage_state_cookies_by_domain_policy', side_effect=lambda state, **kw: state), \
             patch('notebooklm.auth.replace_profile_from_login', autospec=True, return_value=SimpleNamespace(lock_unavailable=False)) as save, \
             patch('notebooklm.paths.get_storage_path', return_value=Path('/saved/session.json')), \
             patch('notebooklm.NotebookLMClient.from_storage', return_value=session):
            pw.return_value.__enter__.return_value = playwright
            result = managed_signin.sign_in()
            return result, context, playwright, save.call_args_list, landing

    def test_selected_popup_session_verified_then_saved_and_closed(self):
        result, context, pw, saves, landing = self.run_capture()
        self.assertEqual(result, 0)
        self.assertEqual(len(saves), 2)
        self.assertEqual(saves[-1].args[0], Path('/saved/session.json'))
        self.assertEqual(saves[-1].kwargs['account_authuser'], 2)
        self.assertTrue(pw.chromium.launch_persistent_context.call_args.kwargs['headless'])
        landing.assert_called_once()
        context.close.assert_called_once()

    def test_invalid_session_does_not_replace_previous_connection(self):
        result, context, _, saves, _ = self.run_capture(RuntimeError('signed out'))
        self.assertEqual(result, 8)
        self.assertEqual(len(saves), 1)
        self.assertNotEqual(saves[0].args[0], Path('/saved/session.json'))
        context.close.assert_called_once()

    def test_validation_works_while_browser_event_loop_is_running(self):
        async def browser_loop():
            result, _, _, _, _ = self.run_capture()
            self.assertEqual(result, 0)
        asyncio.run(browser_loop())

    def test_packaged_browser_supports_chrome_for_testing_name(self):
        executable = Path('/app/Contents/Resources/browser/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing')
        with patch.object(managed_signin.sys, 'frozen', True, create=True), \
             patch.object(managed_signin.sys, 'executable', '/app/Contents/Resources/backend/server'), \
             patch.object(Path, 'glob', return_value=[executable]), \
             patch.object(Path, 'is_file', autospec=True, side_effect=lambda p: p == executable):
            result, _, pw, _, _ = self.run_capture()
            self.assertEqual(result, 0)
            self.assertEqual(pw.chromium.launch_persistent_context.call_args.kwargs['executable_path'], str(executable))

    def test_visible_login_has_no_automation_or_debugging_connection(self):
        process = MagicMock()
        process.poll.return_value = None
        with patch('managed_signin.subprocess.Popen', return_value=process) as spawn, \
             patch('managed_signin.profile_signed_in', return_value=True):
            managed_signin.interactive_login('/Chrome', Path('/private/profile'), 1)
        args = spawn.call_args.args[0]
        self.assertIn('--new-window', args)
        self.assertIn(managed_signin.LOGIN_URL, args)
        self.assertIn('--user-data-dir=/private/profile', args)
        self.assertFalse(any(arg.startswith('--app=') for arg in args))
        self.assertFalse(any('debugging' in arg or 'automation' in arg for arg in args))
        process.terminate.assert_called_once()

    def test_session_detection_reads_only_the_own_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp)
            (profile / 'Default').mkdir()
            with closing(sqlite3.connect(profile / 'Default/Cookies')) as db:
                db.execute('CREATE TABLE cookies (name,host_key,value,encrypted_value)')
                db.execute("INSERT INTO cookies VALUES('SID','.google.com','sample','')")
                self.assertFalse(managed_signin.profile_signed_in(profile))
                db.execute("INSERT INTO cookies VALUES('__Secure-1PSID','.google.com','','sample')")
                db.commit()
            self.assertTrue(managed_signin.profile_signed_in(profile))


if __name__ == '__main__':
    unittest.main()
