"""Real playback, rename, and week separators against an isolated local server."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]


class LibraryUITests(unittest.TestCase):
    def test_week_sections_playback_seek_and_persistent_rename(self):
        from playwright.sync_api import sync_playwright, expect
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / 'recordings'
            audio.mkdir()
            for day, frequency in (('20261012', '440'), ('20261005', '660')):
                source = audio / f'{day}-090000.qta'
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'sine=frequency={frequency}:duration=4', '-c:a', 'aac', '-f', 'ipod', str(source)], check=True)
                os.utime(source, (time.time() - 600, time.time() - 600))
            original_bytes = {p.name: p.read_bytes() for p in audio.iterdir()}
            ready = root / 'ready.json'
            process = subprocess.Popen([sys.executable, str(ROOT / 'voice_notebook.py'), '--port', '0', '--ready-file', str(ready)],
                env={**os.environ, 'VOICE_NOTEBOOK_HOME': str(root / 'data'), 'NOTEBOOKLM_HOME': str(root / 'google')}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(100):
                    if ready.exists():
                        break
                    time.sleep(.05)
                url = json.loads(ready.read_text())['url']

                def state():
                    with urllib.request.urlopen(url + '/api/state') as response:
                        return json.load(response)

                initial = state()
                token = initial['token']

                def post(path, value):
                    request = urllib.request.Request(url + path, data=json.dumps(value).encode(), headers={'Content-Type': 'application/json', 'X-App-Token': token})
                    with urllib.request.urlopen(request) as response:
                        return json.load(response)

                cfg = initial['config']
                cfg.update(recordings_folder=str(audio), onboarding_complete=True)
                post('/api/config', cfg)
                db = sqlite3.connect(root / 'data/state.sqlite3')
                try:
                    db.execute("INSERT INTO notebook_catalog VALUES('latest','tkl week3','2026-10-16T08:00:00+00:00')")
                    db.commit()
                finally:
                    db.close()
                post('/api/scan', {})
                for _ in range(100):
                    current = state()
                    if not current['job']['busy']:
                        break
                    time.sleep(.05)
                self.assertEqual(len(current['recordings']), 2)
                rid = current['recordings'][0]['id']
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport={'width': 1160, 'height': 900})
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(url)
                    page.locator('.tab[data-view="recordings"]').click()
                    expect(page.locator('.recording-week h2')).to_have_text(['Week 3', 'Week 2'])
                    expect(page.locator('#recording-list')).not_to_contain_text('Add week 1')
                    first = page.locator('.recording').first
                    first.get_by_role('button', name='Rename', exact=True).click()
                    first.get_by_role('textbox', name='Recording name').fill('Lecture notes')
                    first.get_by_role('button', name='Save', exact=True).click()
                    expect(page.locator('.recording-name').first).to_have_text('Lecture notes')
                    page.locator('.recording').first.get_by_role('button', name='Play Lecture notes', exact=True).click()
                    page.wait_for_function('()=>document.querySelector(".recording-audio")?.duration > 0')
                    self.assertGreater(page.locator('.recording-audio').evaluate('audio=>audio.duration'), 0)
                    page.locator('.recording-audio').evaluate('audio=>{audio.currentTime=2;audio.pause()}')
                    page.screenshot(path=str(ROOT / 'artifacts/recording-library.png'), full_page=True)
                    page.reload()
                    page.locator('.tab[data-view="recordings"]').click()
                    expect(page.locator('.recording-name').first).to_have_text('Lecture notes')
                    page.set_viewport_size({'width': 390, 'height': 844})
                    self.assertFalse(page.evaluate('document.documentElement.scrollWidth > innerWidth'))
                    self.assertEqual(errors, [])
                    browser.close()
                request = urllib.request.Request(f'{url}/api/recordings/audio/{rid}?token={token}', headers={'Range': 'bytes=10-19'})
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(response.status, 206)
                    self.assertEqual(len(response.read()), 10)
                    self.assertTrue(response.headers['Content-Range'].startswith('bytes 10-19/'))
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(f'{url}/api/recordings/audio/{rid}')
                self.assertEqual(caught.exception.code, 403)
                caught.exception.close()
                self.assertEqual({p.name: p.read_bytes() for p in audio.iterdir()}, original_bytes)
            finally:
                process.terminate()
                process.wait(timeout=10)


if __name__ == '__main__':
    unittest.main()
