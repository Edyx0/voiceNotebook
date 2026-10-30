import asyncio
import base64
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
import urllib.request
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from voice_notebook import App, defaults
from class_photos import class_windows


class PhotoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(Path(self.tmp.name))
        self.cfg = {**defaults(), "week_one": "2026-09-28", "lectures": [
            {"course": "EE221", "day": 0, "start": "09:00", "end": "11:00"}]}
        self.row = {"id":"recording", "status":"uploaded", "notebook_id":"existing-notebook",
                    "recorded_at":"2026-10-12T06:10:00+00:00", "duration":1200,
                    "route":{"course":"EE221", "week":3, "title":"EE221 w3"}}
        self.windows = class_windows([self.row], self.cfg)
        self.pid = hashlib.sha256(b"asset-1").hexdigest()
        self.image = self.app.photos.folder / f"{self.pid}.jpg"
        self.image.write_bytes(b"reviewed jpeg bytes")

    def tearDown(self):
        self.tmp.cleanup()

    def ingest(self, at="2026-10-12T10:00:00+03:00", windows=None):
        self.app.photos.ingest([{"id":self.pid,"captured_at":at,"label":"Possible board"}], windows or self.windows)

    def photo(self):
        return self.app.photos.records()[0]

    def approve(self):
        self.app.photos.review(self.pid, "approve", "existing-notebook")

    def client(self):
        sources = SimpleNamespace(list=AsyncMock(return_value=[]),
                                  add_file=AsyncMock(return_value=SimpleNamespace(id="source",title="photo")),
                                  wait_until_ready=AsyncMock())
        return SimpleNamespace(sources=sources)

    def test_selected_photo_requires_known_notebook_and_uses_pdf_upload(self):
        content = 'data:image/jpeg;base64,' + base64.b64encode(b'\xff\xd8\xffsynthetic').decode()
        with self.assertRaisesRegex(ValueError, 'available notebook'):
            self.app.photos.add_selected(content, 'missing')
        with self.app.db() as db:
            db.execute('INSERT INTO notebook_catalog(id,title) VALUES(?,?)', ('target', 'My notebook'))
        with self.assertRaisesRegex(ValueError, 'read this photo'):
            self.app.photos.add_selected('invalid', 'target')
        pid = self.app.photos.add_selected(content, 'target')
        row = next(item for item in self.app.photos.records() if item['id'] == pid)
        self.assertEqual((row['status'], row['notebook_id']), ('approved', 'target'))
        helper = Path(self.tmp.name) / 'helper'
        helper.touch()
        def convert(args, **kwargs):
            Path(args[-1]).write_bytes(b'%PDF synthetic document')
            return SimpleNamespace(returncode=0)
        client = self.client()
        with patch.dict('os.environ', {'VOICE_NOTEBOOK_PHOTOS_HELPER': str(helper)}), patch('class_photos.subprocess.run', side_effect=convert):
            asyncio.run(self.app.photos.upload_one(client, row))
        self.assertEqual(client.sources.add_file.await_args.args[0], 'target')
        self.assertEqual(client.sources.add_file.await_args.args[1].suffix, '.pdf')
        self.assertEqual(next(item for item in self.app.photos.records() if item['id'] == pid)['status'], 'uploaded')

    def test_selected_photo_sync_does_not_require_library_permission(self):
        with self.app.db() as db:
            db.execute('INSERT INTO notebook_catalog(id,title) VALUES(?,?)', ('target', 'My notebook'))
        content = 'data:image/jpeg;base64,' + base64.b64encode(b'\xff\xd8\xffsynthetic').decode()
        pid = self.app.photos.add_selected(content, 'target')
        client = self.client()
        class Session:
            async def __aenter__(self): return client
            async def __aexit__(self, *args): return False
        with patch.object(self.app.access, 'read', return_value={'photos_enabled': False}), \
             patch('notebooklm.NotebookLMClient.from_storage', return_value=Session()), \
             patch('class_photos.configure_file_uploads'), \
             patch.object(self.app.photos, 'upload_one', new_callable=AsyncMock) as upload:
            asyncio.run(self.app.photos.sync([pid]))
            upload.assert_awaited_once()

    def test_windows_use_uploaded_classes_timezone_and_full_lecture(self):
        self.assertEqual(len(self.windows), 1)
        self.assertEqual(datetime.fromtimestamp(self.windows[0]["start"]).timestamp(), datetime.fromisoformat("2026-10-12T09:00:00+03:00").timestamp())
        self.assertEqual(self.windows[0]["end"], datetime.fromisoformat("2026-10-12T11:00:00+03:00").timestamp())
        self.assertEqual(class_windows([{**self.row,"status":"ready"}],self.cfg), [])
        self.assertEqual(class_windows([{**self.row,"notebook_id":None}],self.cfg), [])

    def test_capture_end_boundary_excluded_and_no_auto_approval(self):
        self.ingest("2026-10-12T11:00:00+03:00")
        self.assertEqual(self.app.photos.records(), [])
        self.ingest()
        self.assertEqual(self.photo()["status"], "review")
        client = self.client()
        with self.assertRaisesRegex(ValueError,"Approve"):
            asyncio.run(self.app.photos.upload_one(client,self.photo()))
        client.sources.add_file.assert_not_called()

    def test_overlapping_classes_require_explicit_destination(self):
        other = {**self.windows[0], "notebook_id":"other", "title":"MATH w3"}
        self.ingest(windows=self.windows+[other])
        self.assertEqual(len(self.photo()["destinations"]), 2)
        for destination in [None,"unrelated-notebook"]:
            with self.assertRaisesRegex(ValueError,"Choose"):
                self.app.photos.review(self.pid,"approve",destination)
        self.approve()
        self.assertEqual(self.photo()["notebook_id"], "existing-notebook")

    def test_rescan_preserves_skip_and_approval(self):
        self.ingest()
        self.app.photos.review(self.pid,"skip")
        self.ingest()
        self.assertEqual(self.photo()["status"], "skipped")
        self.app.photos.review(self.pid,"review")
        self.approve()
        self.ingest()
        self.assertEqual(self.photo()["status"], "approved")
        self.app.photos.review(self.pid,"review")
        self.assertEqual(self.photo()["status"], "review")

    def test_only_approved_uploaded_to_existing_notebook_and_ready_waited(self):
        self.ingest();self.approve();client=self.client()
        asyncio.run(self.app.photos.upload_one(client,self.photo()))
        self.assertEqual(client.sources.add_file.call_args.args[0],"existing-notebook")
        self.assertEqual(client.sources.add_file.call_args.args[1].read_bytes(),self.image.read_bytes())
        client.sources.wait_until_ready.assert_awaited_once_with("existing-notebook","source",timeout=1200)
        self.assertEqual(self.photo()["status"], "uploaded")

    def test_changed_preview_cannot_be_approved_or_uploaded(self):
        self.ingest();self.image.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError,"preview changed"):
            self.approve()
        self.image.write_bytes(b"reviewed jpeg bytes");self.approve()
        self.image.write_bytes(b"changed");client=self.client()
        with self.assertRaisesRegex(ValueError,"changed after approval"):
            asyncio.run(self.app.photos.upload_one(client,self.photo()))
        client.sources.add_file.assert_not_called()

    def test_lost_upload_response_never_resubmitted_after_restart(self):
        self.ingest();self.approve();client=self.client()
        client.sources.add_file.side_effect=RuntimeError("connection lost")
        with self.assertRaises(RuntimeError):asyncio.run(self.app.photos.upload_one(client,self.photo()))
        self.app=App(Path(self.tmp.name))
        self.assertEqual(self.photo()["status"],"error")
        self.app.photos.review(self.pid,"retry")
        with self.assertRaisesRegex(ValueError,"uncertain"):
            asyncio.run(self.app.photos.upload_one(client,self.photo()))
        self.assertEqual(client.sources.add_file.await_count,1)

    def test_interrupted_processing_reuses_saved_source(self):
        self.ingest();self.approve();client=self.client()
        client.sources.wait_until_ready.side_effect=TimeoutError("processing")
        with self.assertRaises(TimeoutError):asyncio.run(self.app.photos.upload_one(client,self.photo()))
        self.app=App(Path(self.tmp.name));self.app.photos.review(self.pid,"retry")
        client.sources.list.return_value=[SimpleNamespace(id="source",title="renamed")]
        client.sources.wait_until_ready.side_effect=None
        asyncio.run(self.app.photos.upload_one(client,self.photo()))
        self.assertEqual(client.sources.add_file.await_count,1)
        self.assertEqual(self.photo()["status"],"uploaded")

    def test_scan_requires_mac_app_and_an_uploaded_class(self):
        with patch.dict("os.environ",{"VOICE_NOTEBOOK_PHOTOS_HELPER":""}):
            with self.assertRaisesRegex(ValueError,"Mac app"):self.app.photos.scan()
        with patch.dict("os.environ",{"VOICE_NOTEBOOK_PHOTOS_HELPER":sys.executable}):
            with patch.object(self.app.access,'read',return_value={'photos_enabled':True}):
                with self.assertRaisesRegex(ValueError,"Upload a class"):self.app.photos.scan()

    def test_regular_audio_sync_does_not_upload_approved_photos(self):
        self.ingest();self.approve();self.app.config=self.cfg
        client=SimpleNamespace(notebooks=SimpleNamespace(list=AsyncMock(return_value=[])))
        class Session:
            async def __aenter__(self):return client
            async def __aexit__(self,*args):return False
        with patch("notebooklm.NotebookLMClient.from_storage",return_value=Session()), \
             patch("voice_notebook.shutil.which",return_value="ffmpeg"), \
             patch.object(self.app.photos,"sync",new_callable=AsyncMock) as photo_sync:
            asyncio.run(self.app.sync())
            photo_sync.assert_not_called()
        self.assertEqual(self.photo()["status"],"approved")

    @unittest.skipUnless((Path(__file__).resolve().parents[1]/"dist/voiceNotebook.app/Contents/MacOS/voiceNotebook").exists(), "Build the Mac app first")
    def test_packaged_scanner_reports_no_classes_without_requesting_access(self):
        executable=Path(__file__).resolve().parents[1]/"dist/voiceNotebook.app/Contents/MacOS/voiceNotebook"
        request=Path(self.tmp.name)/"request.json";response=Path(self.tmp.name)/"response.json"
        request.write_text(json.dumps({"windows":[],"folder":str(self.app.photos.folder)}))
        result=subprocess.run([str(executable),"--scan-photos",str(request),str(response)],capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertIn("No uploaded classes",json.loads(response.read_text())["error"])

    @unittest.skipUnless((Path(__file__).resolve().parents[1]/"dist/voiceNotebook.app/Contents/Resources/backend/voice-notebook-server").exists(), "Build the Mac app first")
    def test_packaged_backend_includes_photo_module_assets_and_preview(self):
        self.ingest()
        executable=Path(__file__).resolve().parents[1]/"dist/voiceNotebook.app/Contents/Resources/backend/voice-notebook-server"
        ready=Path(self.tmp.name)/"ready.json"
        import os
        process=subprocess.Popen([str(executable),"--port","0","--ready-file",str(ready)],
                                 env={**os.environ,"VOICE_NOTEBOOK_HOME":self.tmp.name,"NOTEBOOKLM_HOME":self.tmp.name+"/auth"},stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            for _ in range(200):
                if ready.exists() or process.poll() is not None:break
                time.sleep(.05)
            self.assertTrue(ready.exists(),"Packaged backend did not start")
            url=json.loads(ready.read_text())["url"]
            with urllib.request.urlopen(url+"/api/state") as r:state=json.load(r)
            self.assertEqual(state["photos"][0]["status"],"review")
            for asset in ["/photos.js","/photos.css"]:
                with urllib.request.urlopen(url+asset) as r:self.assertEqual(r.status,200)
            with urllib.request.urlopen(url+"/api/photos/image/"+self.pid) as r:
                self.assertEqual(r.read(),self.image.read_bytes())
                self.assertEqual(r.headers["Content-Type"],"image/jpeg")
        finally:
            process.terminate();process.communicate(timeout=10)


if __name__ == "__main__": unittest.main()
