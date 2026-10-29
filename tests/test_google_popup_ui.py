"""Native sign-in bridge and account selection, without using real accounts."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec('playwright'), 'Playwright required')
class GooglePopupUITests(unittest.TestCase):
    def test_settings_uses_isolated_login_and_connects_without_a_finish_step(self):
        from playwright.sync_api import sync_playwright, expect
        with tempfile.TemporaryDirectory() as tmp:
            ready = Path(tmp) / 'ready.json'
            env = {**os.environ, 'VOICE_NOTEBOOK_HOME': tmp + '/data', 'NOTEBOOKLM_HOME': tmp + '/google'}
            process = subprocess.Popen([sys.executable, str(ROOT / 'voice_notebook.py'), '--port', '0', '--ready-file', str(ready)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(600):
                    if ready.exists() or process.poll() is not None:
                        break
                    time.sleep(.05)
                self.assertTrue(ready.exists(), f'Local service did not start (exit {process.poll()})')
                url = json.loads(ready.read_text())['url']
                with urllib.request.urlopen(url + '/api/state') as response:
                    state = json.load(response)
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page()
                    errors, requests = [], []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.add_init_script('window.nativeCalls=[]; window.webkit={messageHandlers:{native:{postMessage(message){window.nativeCalls.push(message.action)}}}};')
                    page.route('**/api/state', lambda route: route.fulfill(json=state))

                    def login(route):
                        requests.append(route.request.post_data_json)
                        state['auth'] = {'status': 'signing_in', 'message': 'Choose your account.', 'presentation': 'managed'}
                        route.fulfill(json={'ok': True})

                    page.route('**/api/login', login)
                    def cancel(route):
                        state['auth'] = {'status': 'idle', 'message': 'Not connected.'}
                        route.fulfill(json={'ok': True})
                    page.route('**/api/login/cancel', cancel)
                    page.goto(url + '/?settings=1')
                    page.locator('#settings-login').click()
                    expect(page.locator('#settings-login')).to_have_text('Cancel sign-in')
                    self.assertEqual(requests, [{'presentation': 'managed'}])
                    self.assertEqual(page.evaluate('window.nativeCalls'), [])
                    page.locator('#settings-login').click()
                    expect(page.locator('#settings-login')).to_have_text('Sign in with Google ↗')
                    expect(page.locator('#google-account-dialog')).not_to_be_visible()
                    page.locator('#settings-login').click()
                    expect(page.locator('#settings-login')).to_have_text('Cancel sign-in')
                    state['auth'] = {'status': 'connected', 'message': 'Connected'}
                    page.evaluate('refresh()')
                    expect(page.locator('#google-account-dialog')).not_to_be_visible()
                    self.assertIn('googleSignInConnected', page.evaluate('window.nativeCalls'))
                    self.assertEqual(errors, [])
                    browser.close()
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
