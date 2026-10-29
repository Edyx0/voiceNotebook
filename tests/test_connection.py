import tempfile
import io
import time
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from voice_notebook import App, serve


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def wait_checked(self):
        for _ in range(100):
            if self.app.auth['status'] != 'checking': return
            time.sleep(.01)
        self.fail('Connection check did not finish.')

    def test_check_confirms_remote_access_and_notebook_count(self):
        client = SimpleNamespace(notebooks=SimpleNamespace(list=AsyncMock(return_value=[1,2])))
        context = AsyncMock()
        context.__aenter__.return_value = client
        with patch('notebooklm.NotebookLMClient.from_storage', return_value=context):
            self.app.check_connection()
            self.wait_checked()
        self.assertEqual(self.app.auth['status'], 'connected')
        self.assertIn('2 notebooks', self.app.auth['message'])

    def test_failed_session_is_not_reported_as_connected(self):
        with patch('notebooklm.NotebookLMClient.from_storage', side_effect=ValueError('expired session')):
            self.app.check_connection()
            self.wait_checked()
        self.assertEqual(self.app.auth['status'], 'error')
        self.assertNotIn('expired session', self.app.auth['message'])

    def test_login_does_not_open_terminal(self):
        process=SimpleNamespace(wait=lambda:1,poll=lambda:None)
        with patch.object(Path,'exists',return_value=True), patch('voice_notebook.subprocess.Popen',return_value=process) as spawn:
            self.app.login()
            command=spawn.call_args.args[0]
            self.assertIn('--notebooklm-login',command)
            self.assertNotIn('osascript',command)
            self.assertTrue(spawn.call_args.kwargs['start_new_session'])

    def test_upload_waits_for_login(self):
        self.app.auth['status']='signing_in'
        with self.assertRaisesRegex(ValueError,'connection operation'):
            self.app.start('sync')

    def test_canceling_sign_in_preserves_an_existing_connection(self):
        previous = {'status': 'connected', 'message': 'Connected', 'checked_at': '2026-10-29'}
        self.app.auth = dict(previous)
        process = SimpleNamespace(pid=999, poll=lambda: None)
        with patch('voice_notebook.subprocess.Popen', return_value=process), \
             patch('voice_notebook.threading.Thread'), patch('os.killpg'):
            self.app.login('browser')
            self.app.cancel_login()
        self.assertEqual(self.app.auth, previous)

    def test_a_missing_sign_in_browser_does_not_leave_login_stuck(self):
        self.app.auth = {'status': 'connected', 'message': 'Connected'}
        with patch('voice_notebook.subprocess.Popen', side_effect=OSError('missing')):
            with self.assertRaisesRegex(ValueError, 'could not open'):
                self.app.login('browser')
        self.assertEqual(self.app.auth['status'], 'connected')

    def test_closing_the_browser_keeps_the_previous_verified_connection(self):
        previous = {'status': 'connected', 'message': 'Connected'}
        self.app.auth = dict(previous)
        process = SimpleNamespace(wait=lambda: 8, poll=lambda: 8)
        with patch('voice_notebook.subprocess.Popen', return_value=process), \
             patch('voice_notebook.threading.Thread', side_effect=lambda target, daemon: SimpleNamespace(start=target)):
            self.app.login('browser')
        self.assertEqual(self.app.auth['status'], 'connected')
        self.assertIn('existing connection', self.app.auth['message'])

    def test_stale_cancel_does_not_disconnect_a_completed_login(self):
        self.app.auth = {'status': 'connected', 'message': 'Connected'}
        self.app.cancel_login()
        self.assertEqual(self.app.auth['status'], 'connected')

    def test_finish_sign_in_confirms_before_session_import(self):
        pipe = io.BytesIO()
        self.app.auth_process = SimpleNamespace(stdin=pipe, poll=lambda: None)
        self.app.auth['status'] = 'signing_in'
        self.app.finish_login()
        self.assertTrue(pipe.closed)
        self.assertEqual(self.app.auth['status'], 'checking')
        with self.assertRaisesRegex(ValueError, 'Start Google sign-in'):
            self.app.finish_login()

    def test_native_login_uses_system_popup_mode(self):
        process=SimpleNamespace(wait=lambda:1,poll=lambda:None)
        with patch('voice_notebook.subprocess.Popen',return_value=process) as spawn:
            self.app.login('system')
            self.assertIn('--system-popup',spawn.call_args.args[0])

    def test_account_cannot_inject_a_second_worker_command(self):
        with self.assertRaisesRegex(ValueError,'Choose a Google account'):
            self.app.finish_login('first@example.com\nfinish')

    def test_server_reconnects_a_saved_session_on_startup(self):
        from contextlib import redirect_stdout
        storage = Path(self.tmp.name) / 'google.json'
        for saved in (False, True):
            if saved:
                storage.write_text('{}')
            with self.subTest(saved=saved), \
                 patch('notebooklm.paths.get_storage_path', return_value=storage), \
                 patch('voice_notebook.ThreadingHTTPServer') as server, \
                 patch('voice_notebook.threading.Thread'), \
                 patch.object(self.app, 'check_connection') as check, \
                 redirect_stdout(io.StringIO()):
                server.return_value.server_address = ('127.0.0.1', 12345)
                serve(self.app, 0)
                self.assertEqual(check.call_count, int(saved))
