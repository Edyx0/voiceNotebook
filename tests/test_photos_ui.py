"""Review workflow with synthetic images; never accesses Photos or uploads to Google."""
import hashlib
import json
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


@unittest.skipUnless(importlib.util.find_spec("playwright"), "Playwright required")
class PhotoBrowserTests(unittest.TestCase):
    def test_review_preview_skip_approval_and_responsive_layout(self):
        from playwright.sync_api import sync_playwright, expect
        with tempfile.TemporaryDirectory() as temp, sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width":1160,"height":900})
            errors=[]
            page.on("pageerror",lambda error:errors.append(str(error)))
            home=Path(temp)/"data"
            app=App(home)
            app.save_config({**app.config, 'onboarding_complete': True})
            pid=hashlib.sha256(b"synthetic board").hexdigest()
            page.set_content('<body style="background:#254a42;color:white;font:32px Georgia;padding:60px"><p>EE221 · Week 3</p><h1>Circuit analysis</h1><p>V = I × R</p><p>Kirchhoff’s current law</p><p>Σ I = 0</p><small>Synthetic test image</small></body>')
            page.screenshot(path=str(app.photos.folder/f"{pid}.jpg"),type="jpeg")
            app.photos.ingest([{"id":pid,"captured_at":"2026-10-12T10:00:00+03:00","label":"Text detected · possible board or presentation"}],
                              [{"start":1791788400,"end":1791795600,"notebook_id":"existing","title":"EE221 w3"}])
            other=hashlib.sha256(b"second synthetic board").hexdigest()
            (app.photos.folder/f"{other}.jpg").write_bytes((app.photos.folder/f"{pid}.jpg").read_bytes())
            app.photos.ingest([{"id":other,"captured_at":"2026-10-12T10:05:00+03:00","label":"Another board"}],
                              [{"start":1791788400,"end":1791795600,"notebook_id":"existing","title":"EE221 w3"}])
            self.assertEqual(len(app.photos.records()),2)
            rid=hashlib.sha256(b'class recording').hexdigest()
            with app.db() as db:
                db.execute("INSERT INTO recordings(id,path,name,recorded_at,duration,size,status,route,notebook_id) VALUES(?,?,?,?,?,?,?,?,?)",(rid,'/test/audio.m4a','EE221 recording','2026-10-12T09:00:00+03:00',7200,1000,'uploaded',json.dumps({'course':'EE221','week':3,'title':'EE221 w3'}),'existing'))
            with socket.socket() as sock:
                sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
            url=f"http://127.0.0.1:{port}"
            server=subprocess.Popen([sys.executable,str(ROOT/"voice_notebook.py"),"--port",str(port)],env={**os.environ,"VOICE_NOTEBOOK_HOME":str(home),"NOTEBOOKLM_HOME":str(Path(temp)/"google")},stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            try:
                for _ in range(100):
                    try:urllib.request.urlopen(url+"/api/state",timeout=1).close();break
                    except OSError:time.sleep(.05)
                def permission_fixture(route):
                    response=route.fetch();data=response.json();data['permissions']={'photos':'authorized','photos_enabled':True,'recordings':'granted','native':False};data['photos_available']=True;route.fulfill(response=response,json=data)
                page.route('**/api/state',permission_fixture)
                page.goto(url)
                expect(page.locator('.tab[data-view="photos"]')).to_have_count(0)
                page.locator('.tab[data-view="recordings"]').click()
                page.get_by_role('button',name='Photos',exact=True).click()
                expect(page.get_by_role("button",name="Upload approved photos ↗")).to_be_disabled()
                expect(page.locator(".class-photo img")).to_be_visible()
                expect(page.locator('.photo-navigation')).to_contain_text('Photo 1 of 2')
                page.get_by_role('button',name='Next photo').click()
                expect(page.locator('.photo-navigation')).to_contain_text('Photo 2 of 2')
                page.wait_for_function("() => { const image = document.querySelector('.class-photo img'); return image?.complete && image.naturalWidth > 0; }")
                page.get_by_role("button",name="Enlarge photo",exact=False).click()
                expect(page.locator("#photo-preview")).to_be_visible()
                page.get_by_role("button",name="Close photo preview").click()
                page.get_by_role("button",name="Skip",exact=True).click()
                expect(page.locator(".class-photo .badge")).to_have_text("Skipped")
                page.reload();page.locator('.tab[data-view="recordings"]').click();page.get_by_role('button',name='Photos',exact=True).click()
                page.get_by_role('button',name='Next photo').click()
                expect(page.locator(".class-photo .badge")).to_have_text("Skipped")
                page.get_by_role("button",name="Review again").click()
                expect(page.locator(".class-photo select")).to_have_value("existing")
                artifacts=ROOT/"artifacts";artifacts.mkdir(exist_ok=True)
                page.screenshot(path=str(artifacts/"class-photos-desktop.png"),full_page=True)
                page.get_by_role("button",name="Approve photo",exact=True).click()
                expect(page.locator("#photo-sync")).to_be_enabled()
                expect(page.locator(".class-photo .badge")).to_have_text("Approved")
                expect(page.locator(".class-photo a")).to_have_attribute("href","https://notebooklm.google.com/notebook/existing")
                page.get_by_role("button",name="Undo approval").click()
                expect(page.locator("#photo-sync")).to_be_disabled()
                page.set_viewport_size({"width":390,"height":844})
                self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth"))
                page.screenshot(path=str(artifacts/"class-photos-mobile.png"),full_page=True)
                self.assertEqual(errors,[])
                req=urllib.request.Request(url+"/api/photos/review",data=b'{}',headers={"Content-Type":"application/json"})
                with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(req)
                self.assertEqual(error.exception.code,403);error.exception.close()
            finally:
                browser.close();server.terminate();server.wait(timeout=10);server.stderr.close()


if __name__ == "__main__":unittest.main()
