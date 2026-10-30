"""Exercise photo selection without accessing a personal library or Google."""
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
sys.path.insert(0, str(ROOT))
from voice_notebook import App


@unittest.skipUnless(importlib.util.find_spec('playwright'), 'Playwright required')
class SelectedPhotoBrowserTests(unittest.TestCase):
    def test_choose_review_and_submit_to_selected_notebook(self):
        from playwright.sync_api import sync_playwright, expect
        with tempfile.TemporaryDirectory() as temp, sync_playwright() as pw:
            home = Path(temp) / 'data'
            app = App(home)
            app.save_config({**app.config, 'onboarding_complete': True})
            with app.db() as db:
                db.execute('INSERT INTO notebook_catalog(id,title) VALUES(?,?)', ('target', 'Selected notebook'))
                db.execute('INSERT INTO notebook_catalog(id,title) VALUES(?,?)', ('untitled', ''))
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            url = f'http://127.0.0.1:{port}'
            server = subprocess.Popen([sys.executable, str(ROOT / 'voice_notebook.py'), '--port', str(port)],
                env={**os.environ, 'VOICE_NOTEBOOK_HOME': str(home), 'NOTEBOOKLM_HOME': str(Path(temp) / 'google')},
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            browser = pw.chromium.launch()
            try:
                for _ in range(100):
                    try:
                        urllib.request.urlopen(url + '/api/state', timeout=1).close()
                        break
                    except OSError:
                        time.sleep(.05)
                page = browser.new_page()
                page.set_content('<body style="background:#536;color:white"><h1>Synthetic board</h1></body>')
                image = Path(temp) / 'board.jpg'
                page.screenshot(path=str(image), type='jpeg')
                def state_fixture(route):
                    response = route.fetch()
                    data = response.json()
                    data['permissions']['recordings'] = 'granted'
                    route.fulfill(response=response, json=data)
                page.route('**/api/state', state_fixture)
                uploads = []
                def sync_fixture(route):
                    uploads.append(route.request.post_data_json)
                    route.fulfill(json={'ok': True})
                page.route('**/api/photos/sync', sync_fixture)
                page.goto(url)
                page.get_by_role('button', name='Add photos to a notebook').click()
                expect(page.locator('#selected-photos-notebook option')).to_have_text(['Untitled notebook', 'Selected notebook'])
                page.locator('#selected-photos-notebook').select_option('target')
                page.locator('#selected-photos-input').set_input_files(str(image))
                expect(page.locator('#selected-photos-preview img')).to_have_count(1)
                expect(page.get_by_role('button', name='Add to notebook')).to_be_enabled()
                page.get_by_role('button', name='Add to notebook').click()
                expect(page.locator('#selected-photos-message')).to_contain_text('Uploading selected photos')
                self.assertEqual(len(uploads), 1)
                photo = app.photos.records()[0]
                self.assertEqual(photo['notebook_id'], 'target')
                self.assertEqual(photo['status'], 'approved')
                self.assertEqual(uploads[0]['ids'], [photo['id']])
            finally:
                browser.close()
                server.terminate()
                server.wait(timeout=10)
