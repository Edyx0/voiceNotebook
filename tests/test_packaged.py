"""Offline smoke test for the built backend, independent of Python/Homebrew on PATH."""
import json
import base64
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
EXECUTABLE = ROOT / 'dist/voiceNotebook.app/Contents/Resources/backend/voice-notebook-server'


@unittest.skipUnless(EXECUTABLE.exists(), 'Build the Mac app first')
class PackagedTests(unittest.TestCase):
    def test_bundled_service_assets_audio_tools_and_sdk(self):
        with tempfile.TemporaryDirectory() as tmp:
            ready = Path(tmp) / 'ready.json'
            env = {**os.environ, 'PATH':'/usr/bin:/bin', 'VOICE_NOTEBOOK_HOME':tmp+'/data', 'NOTEBOOKLM_HOME':tmp+'/notebooklm'}
            process = subprocess.Popen([str(EXECUTABLE),'--port','0','--ready-file',str(ready)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                for _ in range(200):
                    if ready.exists() or process.poll() is not None: break
                    time.sleep(.05)
                if not ready.exists():
                    out,err=process.communicate(timeout=5)
                    self.fail('Packaged service failed: '+err.decode()[-1500:])
                url=json.loads(ready.read_text())['url']
                with urllib.request.urlopen(url+'/api/state') as response: state=json.load(response)
                self.assertTrue(state['dependencies']['ffmpeg'])
                self.assertTrue(state['dependencies']['notebooklm'])
                with urllib.request.urlopen(url) as response: html=response.read().decode()
                self.assertIn('connection-view',html)
                from playwright.sync_api import sync_playwright
                with sync_playwright() as pw:
                    browser=pw.chromium.launch()
                    page=browser.new_page(viewport={'width':1000,'height':400})
                    page.set_content('<body style="font:32px Arial;background:white;color:black;padding:35px"><p>Monday EE221 09:00-11:00</p><p>Thursday MATH201 13:00-15:00</p></body>')
                    photo=page.screenshot()
                    browser.close()
                request=urllib.request.Request(url+'/api/timetable/photo',data=json.dumps({'content':base64.b64encode(photo).decode()}).encode(),headers={'Content-Type':'application/json','X-App-Token':state['token']})
                with urllib.request.urlopen(request) as response: timetable=json.load(response)
                self.assertEqual([s['course'] for s in timetable['slots']],['EE221','MATH201'])
                cli=subprocess.run([str(EXECUTABLE),'--notebooklm-login','--help'],env={**env,'PYINSTALLER_RESET_ENVIRONMENT':'1'},capture_output=True,text=True,timeout=20)
                self.assertEqual(cli.returncode,0,cli.stderr)
                self.assertIn('login',cli.stdout)
                request=urllib.request.Request(url+'/api/connection',data=b'{}',headers={'Content-Type':'application/json','X-App-Token':state['token']})
                urllib.request.urlopen(request).close()
                for _ in range(100):
                    with urllib.request.urlopen(url+'/api/state') as response: state=json.load(response)
                    if state['auth']['status']!='checking': break
                    time.sleep(.05)
                self.assertEqual(state['auth']['status'],'error')  # Isolated home has no Google session.
                ffmpeg=EXECUTABLE.parent/'_internal/bin/ffmpeg'
                result=subprocess.run([str(ffmpeg),'-v','error','-f','lavfi','-i','sine=duration=1','-f','mp3',tmp+'/audio.mp3'],env=env,capture_output=True)
                self.assertEqual(result.returncode,0,result.stderr.decode())
                self.assertGreater((Path(tmp)/'audio.mp3').stat().st_size,0)
            finally:
                process.terminate()
                process.communicate(timeout=10)
