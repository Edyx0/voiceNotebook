"""Real local-browser tests. Uses generated audio and a separate temporary data folder."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec("playwright") and shutil.which("ffmpeg"), "Playwright and FFmpeg required")
class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.tmp = tempfile.TemporaryDirectory()
        cls.folder = Path(cls.tmp.name) / "recordings"
        cls.folder.mkdir()
        source = cls.folder / "20261012-090000.qta"
        subprocess.run(["ffmpeg","-v","error","-y","-f","lavfi","-i","sine=duration=2","-c:a","aac","-f","ipod",str(source)],check=True)
        os.utime(source,(time.time()-600,time.time()-600))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1",0))
            cls.port=sock.getsockname()[1]
        cls.url=f"http://127.0.0.1:{cls.port}"
        cls.server = subprocess.Popen([sys.executable,str(ROOT/"voice_notebook.py"),"--port",str(cls.port)],
                                      env={**os.environ,"VOICE_NOTEBOOK_HOME":str(Path(cls.tmp.name)/"data"),"NOTEBOOKLM_HOME":str(Path(cls.tmp.name)/"google")}, stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        for _ in range(100):
            try:
                urllib.request.urlopen(cls.url+"/api/state",timeout=1).close()
                break
            except OSError: time.sleep(.05)
        cls.pw=sync_playwright().start()
        cls.browser=cls.pw.chromium.launch()
        cls.page=cls.browser.new_page(viewport={"width":1440,"height":1100})
        cls.errors=[]
        cls.page.on("pageerror",lambda error:cls.errors.append(str(error)))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.pw.stop();cls.server.terminate();cls.server.wait(timeout=10)
        cls.server.stderr.close();cls.tmp.cleanup()

    def test_browser_setup_scan_review_and_responsive_layout(self):
        from playwright.sync_api import expect
        p=self.page
        p.goto(self.url)
        expect(p.locator('#access-gate')).to_be_visible()
        p.locator('#gate-settings').click()
        p.locator('#source-path-input').fill(str(self.folder))
        p.locator('#source-path-save').click()
        expect(p.locator('#access-summary')).to_have_text('Audio folder connected')
        p.locator('#settings-close').click()
        expect(p.locator('#home-view')).to_be_visible()
        p.locator('.tab[data-view="recordings"]').click()
        expect(p.locator("#setup-nudge")).to_have_count(0)
        expect(p.locator("#sync")).to_be_disabled()
        p.get_by_role('button',name='Timetable',exact=True).click()
        p.locator('#semester-settings').evaluate('(el)=>el.open=true')
        p.locator("#week-one").evaluate("el => el.value = '2026-09-28'")
        p.locator("#add-slot").click()
        p.locator('#lecture-course').fill('EE221')
        p.locator('#lecture-start').fill('09:00')
        p.locator('#lecture-end').fill('11:00')
        p.locator('#lecture-form').get_by_role('button',name='Done',exact=True).click()
        expect(p.locator('#weekly-calendar .calendar-event')).to_have_count(1)
        p.get_by_role("button",name="Save timetable",exact=True).click()
        expect(p.locator("#setup-nudge")).to_have_count(0)
        p.locator("#scan").click()
        expect(p.locator(".recording-name")).to_have_text("20261012-090000.qta",timeout=15000)
        expect(p.locator(".notebook-link")).to_have_text("EE221 w3")
        expect(p.locator("#sync")).to_be_enabled()
        p.locator('.tab[data-view="setup"]').click()
        p.locator('#calendar-week').select_option('3')
        expect(p.locator('#weekly-calendar .calendar-event.has-recording')).to_have_count(1)
        expect(p.locator('#weekly-calendar .recording-mark')).to_contain_text('1 recording')
        first_color=p.locator('#weekly-calendar .calendar-event').get_attribute('data-color')
        p.locator('#add-slot').click()
        p.locator('#lecture-course').fill('EE221')
        p.locator('#lecture-day').select_option('3')
        p.locator('#lecture-start').fill('13:00')
        p.locator('#lecture-end').fill('14:30')
        p.locator('#lecture-form').get_by_role('button',name='Done',exact=True).click()
        self.assertEqual(p.locator('#weekly-calendar .calendar-event').nth(1).get_attribute('data-color'),first_color)
        self.assertEqual(p.locator('#weekly-calendar').get_attribute('data-start'),'09:00')
        self.assertEqual(p.locator('#weekly-calendar').get_attribute('data-end'),'14:30')
        p.locator('#calendar-week').select_option('2')
        expect(p.locator('#weekly-calendar .calendar-event.has-recording')).to_have_count(0)
        p.locator('#calendar-week').select_option('3')
        expect(p.locator('#setup-view .help-button')).to_have_count(0)
        expect(p.get_by_text('Semester & settings',exact=True)).to_have_count(0)
        p.locator('#semester-settings').evaluate('(el)=>el.open=false')
        (ROOT/'artifacts').mkdir(exist_ok=True)
        p.screenshot(path=str(ROOT/'artifacts/weekly-calendar.png'),full_page=True)
        p.locator('.tab[data-view="recordings"]').click()
        p.get_by_role("button",name="Review",exact=True).click()
        p.locator("#review-course").fill("MATH201")
        p.locator("#review-week").fill("4")
        p.get_by_role("button",name="Save assignment").click()
        expect(p.locator(".notebook-link")).to_have_text("MATH201 w4")
        p.get_by_role("button",name="Skip",exact=True).click()
        expect(p.locator(".badge")).to_have_text("Ignored")
        p.get_by_role("button",name="Ready",exact=True).click()
        expect(p.locator(".recording")).to_have_count(0)
        p.get_by_role("button",name="All recordings",exact=True).click()
        artifacts=ROOT/"artifacts"
        artifacts.mkdir(exist_ok=True)
        p.screenshot(path=str(artifacts/"desktop.png"),full_page=True)
        p.set_viewport_size({"width":390,"height":844})
        self.assertFalse(p.evaluate("document.documentElement.scrollWidth > innerWidth"))
        p.get_by_role("button",name="Timetable",exact=True).click()
        self.assertFalse(p.evaluate("document.documentElement.scrollWidth > innerWidth"))
        p.screenshot(path=str(artifacts/"mobile-setup.png"),full_page=True)
        self.assertEqual(self.errors,[])

    def test_local_api_rejects_unauthenticated_writes(self):
        req=urllib.request.Request(self.url+"/api/scan",data=b"{}",headers={"Content-Type":"application/json"})
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req)
        self.assertEqual(caught.exception.code,403)
        caught.exception.close()

    def test_timetable_photo_local_ocr_and_manual_edit(self):
        from playwright.sync_api import expect
        p=self.browser.new_page(viewport={'width':1100,'height':650})
        image=Path(self.tmp.name)/'timetable.png'
        p.set_content('<html><body style="background:white;color:black;font:32px Arial;padding:35px"><h1 style="font-size:36px">Weekly timetable</h1><p>Monday EE221 09:00-11:00</p><p>Wednesday MATH201 13:00-15:00</p></body></html>')
        p.screenshot(path=str(image))
        p.goto(self.url)
        p.get_by_role('button',name='Timetable',exact=True).click()
        p.locator('#timetable-image').set_input_files(str(image))
        expect(p.locator('#timetable-import-status')).to_contain_text('classes imported',timeout=100000)
        courses=p.locator('[data-key="course"]')
        self.assertIn('MATH201',courses.evaluate_all('(items)=>items.map(i=>i.value)'))
        # Imported rows are only a draft; the saved timetable is unchanged until Save.
        state=p.evaluate('fetch("/api/state").then(r=>r.json())')
        self.assertEqual(len(state['config']['lectures']),1)
        p.locator('.calendar-event[data-course="MATH201"]').click()
        p.locator('#lecture-course').fill('PHYS202')
        p.locator('#lecture-form').get_by_role('button',name='Done',exact=True).click()
        expect(p.locator('.calendar-event[data-course="PHYS202"]')).to_have_count(1)
        self.assertEqual(p.locator('#weekly-calendar').get_attribute('data-start'),'09:00')
        self.assertEqual(p.locator('#weekly-calendar').get_attribute('data-end'),'15:00')
        p.screenshot(path=str(ROOT/'artifacts/timetable-photo-import.png'),full_page=True)
        p.locator('#connection-shortcut').click()
        expect(p.locator('#connection-view')).to_be_visible()
        expect(p.locator('#login')).to_be_visible()
        expect(p.locator('.connection-details')).to_have_count(0)
        p.close()


if __name__ == "__main__": unittest.main()
