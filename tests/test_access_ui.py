"""Permission explanation and exported-folder fallback; no real permissions changed."""
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec("playwright"), "Playwright required")
class AccessBrowserTests(unittest.TestCase):
    def test_denied_access_keeps_manual_folder_available(self):
        from playwright.sync_api import sync_playwright, expect
        with tempfile.TemporaryDirectory() as temp, sync_playwright() as pw:
            folder = Path(temp) / "Exported Recordings"
            folder.mkdir()
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            url = f"http://127.0.0.1:{port}"
            server = subprocess.Popen(
                [sys.executable, str(ROOT / "voice_notebook.py"), "--port", str(port)],
                env={**os.environ, "VOICE_NOTEBOOK_HOME": str(Path(temp) / "data"), "NOTEBOOKLM_HOME": str(Path(temp) / "google")},
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            browser = pw.chromium.launch()
            try:
                for _ in range(100):
                    try:
                        urllib.request.urlopen(url + "/api/state", timeout=1).close()
                        break
                    except OSError:
                        time.sleep(.05)
                page = browser.new_page(viewport={"width": 1160, "height": 900})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.add_init_script("window.nativeCalls=[];window.webkit={messageHandlers:{native:{postMessage:message=>window.nativeCalls.push(message.action)}}};")

                def permissions(route):
                    response = route.fetch()
                    data = response.json()
                    data['config']['onboarding_complete'] = True
                    data['permissions']['recordings'] = 'granted' if data['config']['recordings_folder'] == str(folder) else 'denied'
                    route.fulfill(response=response, json=data)

                page.route('**/api/state', permissions)
                page.goto(url)
                expect(page.locator('#access-gate')).to_be_visible()
                expect(page.locator('#workspace-nav')).to_be_hidden()
                expect(page.locator('#home-view')).to_be_hidden()
                expect(page.locator('#home-view #voice-grant')).to_have_count(0)
                page.locator('#gate-settings').click()
                self.assertEqual(page.evaluate('window.nativeCalls'), ['settings'])
                page.goto(url + '/?settings=1')
                expect(page.locator('#settings-content')).to_be_visible()
                expect(page.locator('#workspace-nav')).to_be_hidden()
                expect(page.locator('#voice-access-help')).to_contain_text('protected recordings folder')
                page.locator('#voice-grant').click()
                self.assertEqual(page.evaluate('window.nativeCalls'), ['fullDiskAccess'])
                expect(page.locator('#source-path-help')).to_contain_text('still requires permission')
                artifacts = ROOT / 'artifacts'
                artifacts.mkdir(exist_ok=True)
                page.screenshot(path=str(artifacts / 'recordings-access-desktop.png'), full_page=True)
                page.set_viewport_size({'width': 390, 'height': 844})
                self.assertFalse(page.evaluate('document.documentElement.scrollWidth > innerWidth'))
                page.screenshot(path=str(artifacts / 'recordings-access-mobile.png'), full_page=True)
                page.set_viewport_size({'width': 1160, 'height': 900})
                page.locator('#source-path-input').fill('  ' + str(folder) + '  ')
                page.locator('#source-path-save').click()
                expect(page.locator('#access-summary')).to_have_text('Audio folder connected')
                expect(page.locator('#voice-access-state')).to_have_text('Using an audio folder')
                expect(page.locator('#home-view')).to_be_hidden()
                self.assertEqual(page.evaluate('window.nativeCalls'), ['fullDiskAccess'])
                page.reload()
                expect(page.locator('#source-path-input')).to_have_value(str(folder))
                page.route('**/api/config', lambda route: route.fulfill(status=400, json={'error': 'Could not save folder.'}))
                page.locator('#source-path-input').fill('/another/folder')
                page.locator('#source-path-save').click()
                expect(page.locator('#notice')).to_have_text('Could not save folder.')
                expect(page.locator('#source-path-input')).to_have_value('/another/folder')
                expect(page.locator('#source-path-save')).to_be_enabled()
                page.unroute('**/api/config')
                page.locator('#source-path-input').fill(str(folder))
                page.goto(url)
                expect(page.locator('#home-view')).to_be_visible()
                expect(page.locator('#workspace-nav')).to_be_visible()
                expect(page.locator('#settings-content')).to_be_hidden()
                expect(page.locator('#access-gate')).to_be_hidden()
                # Losing access hides the workspace again; optional Photos never gates it.
                page.unroute('**/api/state')
                def denied(route):
                    response = route.fetch(); data = response.json()
                    data['config']['onboarding_complete'] = True
                    data['permissions']['recordings'] = 'denied'
                    route.fulfill(response=response, json=data)
                page.route('**/api/state', denied)
                page.evaluate('refresh()')
                expect(page.locator('#access-gate')).to_be_visible()
                expect(page.locator('#workspace-nav')).to_be_hidden()
                page.screenshot(path=str(artifacts / 'recordings-access-gate.png'), full_page=True)
                # Development/browser fallback uses the same settings in a dialog.
                fallback = browser.new_page()
                fallback.route('**/api/state', denied)
                fallback.goto(url)
                fallback.locator('#gate-settings').click()
                expect(fallback.locator('#settings-dialog')).to_be_visible()
                expect(fallback.locator('#voice-grant')).to_be_disabled()
                expect(fallback.locator('#source-path-input')).to_be_editable()
                fallback.keyboard.press('Escape')
                expect(fallback.locator('#settings-dialog')).to_be_hidden()
                fallback.locator('#open-settings').click()
                expect(fallback.locator('#settings-dialog')).to_be_visible()
                fallback.close()
                self.assertEqual(errors, [])
            finally:
                browser.close()
                server.terminate()
                server.wait(timeout=10)
                server.stderr.close()


if __name__ == '__main__':
    unittest.main()
