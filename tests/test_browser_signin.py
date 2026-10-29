import io
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import browser_signin


class BrowserSignInTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = patch.dict('os.environ', {'VOICE_NOTEBOOK_HOME': tmp.name})
        env.start()
        self.addCleanup(env.stop)

    def test_blocked_safari_session_names_the_actual_macos_permission(self):
        failure = SimpleNamespace(code='COOKIE_READ_FAILED', message='Permission denied reading safari cookies.')
        with patch('browser_signin.default_browser', return_value='safari'), \
             patch('notebooklm.cli.services.login.browser_accounts._enumerate_browser_accounts', return_value=failure):
            with self.assertRaisesRegex(ValueError, 'voiceNotebook.*Full Disk Access'):
                browser_signin.available_accounts()

    def test_uses_macos_default_browser(self):
        with patch('browser_signin.subprocess.run', return_value=SimpleNamespace(stdout='com.apple.Safari\n')) as run:
            self.assertEqual(browser_signin.default_browser(), 'safari')
            self.assertIn('URLForApplicationToOpenURL', run.call_args.args[0][-1])

    def test_explicit_completion_uses_the_account_in_our_window(self):
        stream = io.StringIO('finish\n')
        with patch('browser_signin.default_browser', return_value='safari'), \
             patch('browser_signin.open_sign_in', return_value=('123', 4)) as open_window, \
             patch('browser_signin.close_sign_in') as close_window, \
             patch('browser_signin.sys.stdin', stream), \
             patch('browser_signin.select.select', return_value=([stream], [], [])), \
             patch('browser_signin.popup_account', return_value=2), \
             patch('browser_signin.import_session', return_value=0) as save:
            self.assertEqual(browser_signin.sign_in(), 0)
            open_window.assert_called_once_with('safari')
            save.assert_called_once_with('safari', 2)
            close_window.assert_called_once_with('safari', '123', 4)

    def test_completed_popup_connects_and_closes_without_finish_button(self):
        with patch('browser_signin.default_browser', return_value='chrome'), \
             patch('browser_signin.open_sign_in', return_value=('123', 4)), \
             patch('browser_signin.close_sign_in') as close_window, \
             patch('browser_signin.select.select', return_value=([], [], [])), \
             patch('browser_signin.popup_account', side_effect=[ValueError('Still signing in'), 2]), \
             patch('browser_signin.import_session', return_value=0) as save:
            self.assertEqual(browser_signin.sign_in(), 0)
            save.assert_called_once_with('chrome', 2)
            close_window.assert_called_once_with('chrome', '123', 4)

    def test_close_preserves_other_windows_and_added_tabs(self):
        with patch('browser_signin.subprocess.run') as run:
            browser_signin.close_sign_in('safari', '123', 4)
            script = run.call_args.args[0][-1]
            self.assertIn('String(w.id()) === "123"', script)
            self.assertIn('window.tabs().length <= 4', script)
            self.assertIn('accounts', script)
            self.assertIn('window.close()', script)

    def test_timeout_does_not_import_existing_account(self):
        with patch('browser_signin.default_browser', return_value='firefox'), \
             patch('browser_signin.open_sign_in', return_value=None), \
             patch('browser_signin.select.select', return_value=([], [], [])), \
             patch('browser_signin.import_session') as save:
            self.assertEqual(browser_signin.sign_in(timeout=1), 1)
            save.assert_not_called()

    def test_unknown_browser_never_imports_from_another_browser(self):
        with patch('browser_signin.default_browser', return_value=None), \
             patch('browser_signin.open_sign_in') as open_window, \
             patch('browser_signin.import_session') as save:
            self.assertEqual(browser_signin.sign_in(), 3)
            open_window.assert_not_called()
            save.assert_not_called()

    def test_permission_and_ambiguous_accounts_have_clear_results(self):
        for output, expected in [('Full Disk Access required', 2), ('Use --account to select an account', 4)]:
            with self.subTest(output=output), patch('click.testing.CliRunner.invoke', return_value=SimpleNamespace(exit_code=1, output=output, exception=None)):
                self.assertEqual(browser_signin.import_session('safari'), expected)

    def test_import_uses_real_sdk_command_without_reading_browser_cookies(self):
        from click.testing import CliRunner
        from notebooklm.notebooklm_cli import cli
        real_invoke = CliRunner().invoke
        # An invalid browser reaches the real SDK's validation, with no session read.
        with patch('click.testing.CliRunner.invoke', wraps=real_invoke) as invoke:
            self.assertEqual(browser_signin.import_session('invalid-test-browser'), 1)
            self.assertIs(invoke.call_args.args[0], cli)

    def test_sdk_receives_staged_storage_path_before_reading_cookies(self):
        from click.testing import CliRunner
        from notebooklm.notebooklm_cli import cli
        with tempfile.TemporaryDirectory() as tmp, \
             patch('notebooklm.cli.session_cmd._login_browser_cookies_single') as login:
            staged = str(Path(tmp) / 'session.json')
            result = CliRunner().invoke(cli, ['login', '--storage', staged, '--browser-cookies', 'safari', '--account', 'chosen@example.test'])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(str(login.call_args.kwargs['storage']), staged)

    def test_safari_sign_in_creates_a_document_instead_of_opening_a_tab(self):
        with patch('browser_signin.subprocess.run', return_value=SimpleNamespace(stdout='{"id":"123","tabs":4}')) as run:
            browser_signin.open_sign_in('safari')
            script = run.call_args.args[0][-1]
            self.assertIn("new: 'document'", script)
            self.assertIn('com.apple.Safari', script)
            self.assertIn(browser_signin.LOGIN_URL, script)

    def test_chrome_sign_in_creates_its_own_window(self):
        with patch('browser_signin.subprocess.run', return_value=SimpleNamespace(stdout='{"id":"123","tabs":1}')) as run:
            browser_signin.open_sign_in('chrome')
            script = run.call_args.args[0][-1]
            self.assertIn('browser.Window()', script)
            self.assertIn('window.activeTab.url', script)

    def test_denied_window_access_does_not_import_a_session(self):
        import subprocess
        with patch('browser_signin.default_browser', return_value='safari'), \
             patch('browser_signin.open_sign_in', side_effect=subprocess.CalledProcessError(1, 'osascript')), \
             patch('browser_signin.import_session') as save:
            self.assertEqual(browser_signin.sign_in(), 5)
            save.assert_not_called()

    def test_popup_account_reads_only_our_window_and_selected_account(self):
        with patch('browser_signin.subprocess.run', return_value=SimpleNamespace(stdout='https://notebook.google.com/?authuser=2\n')) as run:
            self.assertEqual(browser_signin.popup_account('safari', '123'), 2)
            self.assertIn('"123"', run.call_args.args[0][-1])

    def test_popup_account_accepts_google_account_slot_in_path(self):
        with patch('browser_signin.subprocess.run', return_value=SimpleNamespace(stdout='https://notebook.google.com/u/2/\n')):
            self.assertEqual(browser_signin.popup_account('safari', '123'), 2)

    def test_unfinished_sign_in_never_imports_the_default_account(self):
        with patch('browser_signin.subprocess.run', return_value=SimpleNamespace(stdout='https://accounts.google.com/AccountChooser')):
            with self.assertRaises(ValueError):
                browser_signin.popup_account('safari', '123')

    def test_chosen_popup_account_is_passed_to_sdk(self):
        accounts = [SimpleNamespace(authuser=0, email='first@example.com'), SimpleNamespace(authuser=2, email='chosen@example.com')]
        with patch('notebooklm.cli.services.login.browser_accounts._enumerate_browser_accounts', return_value=({}, accounts)), \
             patch('browser_signin.save_verified_session', return_value=True), \
             patch('click.testing.CliRunner.invoke', return_value=SimpleNamespace(exit_code=0, output='')) as invoke:
            self.assertEqual(browser_signin.import_session('safari', 2), 0)
            self.assertEqual(invoke.call_args.args[1][-2:], ['--account', 'chosen@example.com'])
            self.assertEqual(invoke.call_args.args[1][:2], ['login', '--storage'])

    def test_invalid_session_never_replaces_the_saved_connection(self):
        with patch('notebooklm.NotebookLMClient.from_storage', side_effect=ValueError('Expired session')), \
             patch('notebooklm.auth.replace_profile_from_login') as replace:
            self.assertFalse(browser_signin.save_verified_session(Path('/staged/session.json')))
            replace.assert_not_called()

    def test_login_diagnostics_exclude_exception_messages(self):
        import os
        try:
            raise ValueError('private@example.test cookie=secret')
        except ValueError as error:
            browser_signin._diagnose('verify', error)
        diagnostic = Path(os.environ['VOICE_NOTEBOOK_HOME']) / 'last-login-error.json'
        text = diagnostic.read_text()
        self.assertNotIn('private@example.test', text)
        self.assertNotIn('cookie=secret', text)
        self.assertEqual(diagnostic.stat().st_mode & 0o777, 0o600)

    def test_system_popup_never_opens_a_regular_browser_window(self):
        stream = io.StringIO('finish\tchosen@example.com\n')
        with patch('browser_signin.default_browser', return_value='safari'), \
             patch('browser_signin.open_sign_in') as regular_window, \
             patch('browser_signin.sys.stdin', stream), \
             patch('browser_signin.select.select', return_value=([stream], [], [])), \
             patch('browser_signin.import_session', return_value=0) as save:
            self.assertEqual(browser_signin.sign_in(system_popup=True), 0)
            regular_window.assert_not_called()
            save.assert_called_once_with('safari', account_email='chosen@example.com')

    def test_system_popup_requires_an_explicit_account(self):
        stream = io.StringIO('finish\n')
        with patch('browser_signin.default_browser', return_value='safari'), \
             patch('browser_signin.sys.stdin', stream), \
             patch('browser_signin.select.select', return_value=([stream], [], [])), \
             patch('browser_signin.import_session') as save:
            self.assertEqual(browser_signin.sign_in(system_popup=True), 4)
            save.assert_not_called()
