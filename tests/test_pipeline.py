import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from voice_notebook import App, convert, defaults, filename_date, match_recording, probe, validate_config


def config(folder="/tmp"):
    return validate_config({**defaults(), "week_one": "2026-09-28", "recordings_folder": folder,
                            "lectures": [{"course": "EE221", "day": 0, "start": "09:00", "end": "11:00"},
                                         {"course": "EE221", "day": 3, "start": "13:00", "end": "15:00"}]})


class TimetableTests(unittest.TestCase):
    def test_two_lectures_share_week_three_notebook(self):
        cfg = config()
        a, _ = match_recording("2026-10-12T09:10:00+03:00", cfg)
        b, _ = match_recording("2026-10-15T13:00:00+03:00", cfg)
        self.assertEqual(a, b)
        self.assertEqual(a["title"], "EE221 w3")

    def test_utc_is_converted_to_timetable_timezone(self):
        route, _ = match_recording("2026-10-12T06:05:00+00:00", config())
        self.assertEqual(route["week"], 3)

    def test_unmatched_undated_and_out_of_semester(self):
        for timestamp in [None, "2026-10-13T09:00:00+03:00", "2026-09-21T09:00:00+03:00", "2027-10-11T09:00:00+03:00"]:
            with self.subTest(timestamp=timestamp):
                self.assertIsNone(match_recording(timestamp, config())[0])

    def test_overlapping_courses_require_review(self):
        cfg = config()
        cfg["lectures"].append({"course":"MATH201", "day":0, "start":"09:00", "end":"10:00"})
        self.assertIsNone(match_recording("2026-10-12T09:00:00+03:00", cfg)[0])

    def test_early_allowance_and_end_boundary(self):
        self.assertIsNotNone(match_recording("2026-10-12T08:51:00+03:00", config())[0])
        self.assertIsNone(match_recording("2026-10-12T08:49:00+03:00", config())[0])
        self.assertIsNone(match_recording("2026-10-12T11:00:00+03:00", config())[0])

    def test_filename_fallback_does_not_use_mtime(self):
        self.assertEqual(filename_date(Path("20261012-090000.qta"), "Europe/Istanbul"), "2026-10-12T09:00:00+03:00")
        self.assertIsNone(filename_date(Path("New Recording.m4a"), "Europe/Istanbul"))

    def test_invalid_config_rejected(self):
        for change in [{"timezone":"invalid"},{"semester_weeks":0},{"lectures":[{"course":"EE221","day":7,"start":"09:00","end":"10:00"}]}]:
            with self.subTest(change=change), self.assertRaises((ValueError, KeyError)):
                validate_config({**config(), **change})


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.audio = self.root / "recordings"
        self.audio.mkdir()
        self.source = self.audio / "20261012-090000.m4a"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=6", "-c:a", "aac", str(self.source)], check=True)
        self.age(self.source)
        self.app = App(self.root / "state")
        self.app.save_config(config(str(self.audio)))

    def tearDown(self):
        self.tmp.cleanup()

    def age(self, path):
        os.utime(path, (time.time()-600, time.time()-600))

    def scan(self):
        self.app.scan()
        return self.app.records()[0]

    def test_qta_content_detected_and_deduplicated(self):
        qta = self.audio / "20261012-090000.qta"
        shutil.copyfile(self.source, qta)
        self.age(qta)
        self.assertAlmostEqual(probe(qta)[0], 6, delta=.2)
        self.app.scan()
        self.assertEqual(len(self.app.records()), 1)
        self.assertEqual(self.app.records()[0]["status"], "ready")

    def test_real_split_every_part_below_limit_and_duration_preserved(self):
        files = convert(self.source, self.root / "out", "lecture", 6, max_bytes=60_000)
        self.assertGreater(len(files), 1)
        self.assertTrue(all(0 < p.stat().st_size < 60_000 for p in files))
        self.assertAlmostEqual(sum(probe(p)[0] for p in files), 6, delta=.5)
        self.assertTrue(self.source.exists())

    def test_undated_file_requires_review_and_manual_assignment(self):
        self.source.rename(self.audio / "New Recording.qta")
        row = self.scan()
        self.assertEqual(row["status"], "review")
        self.app.review(row["id"], {"course":"MATH201","week":4,"recorded_at":"2026-10-20T12:00"})
        self.app.save_config(config(str(self.audio)))
        self.assertEqual(self.app.records()[0]["route"]["course"], "MATH201")

    def test_recent_files_are_not_imported(self):
        os.utime(self.source, None)
        self.app.scan()
        self.assertEqual(self.app.records(), [])

    def test_permission_error_is_actionable(self):
        with patch.object(Path, "iterdir", side_effect=PermissionError), self.assertRaisesRegex(ValueError, "Full Disk Access"):
            self.app.scan()

    def client(self, fail_wait=False, fail_add=False):
        class Notebooks:
            def __init__(self): self.created=[]
            async def create(inner, title):
                nb=SimpleNamespace(id="notebook-1", title=title);inner.created.append(nb);return nb
        class Sources:
            def __init__(self): self.items=[];self.adds=0;self.fail_wait=fail_wait
            async def list(inner, nb): return inner.items
            async def add_file(inner, nb, path, wait=False):
                inner.adds+=1
                if fail_add: raise RuntimeError("connection lost")
                s=SimpleNamespace(id="source-"+str(inner.adds),title=path.name);inner.items.append(s);return s
            async def wait_until_ready(inner, nb, sid, timeout=1200):
                if inner.fail_wait: raise TimeoutError("transcription pending")
        return SimpleNamespace(notebooks=Notebooks(), sources=Sources())

    def test_partial_upload_retry_uses_saved_source(self):
        row=self.scan();client=self.client(fail_wait=True);notebooks=[]
        with self.assertRaises(TimeoutError): asyncio.run(self.app.upload_one(client,notebooks,row))
        client.sources.fail_wait=False
        asyncio.run(self.app.upload_one(client,notebooks,self.app.records()[0]))
        self.assertEqual(client.sources.adds,1)

    def test_confirmed_processing_failure_can_be_replaced_after_retry(self):
        row = self.scan()
        client = self.client(fail_wait=True)
        notebooks = []
        with self.assertRaises(TimeoutError):
            asyncio.run(self.app.upload_one(client, notebooks, row))
        client.sources.items[0].is_error = True
        client.sources.fail_wait = False
        self.app.update(row['id'], status='error', error='Google processing failed')
        self.app.review(row['id'], {'action': 'retry'})
        asyncio.run(self.app.upload_one(client, notebooks, self.app.records()[0]))
        self.assertEqual(client.sources.adds, 2)
        self.assertEqual(self.app.records()[0]['parts'][0]['source_id'], 'source-2')
        self.assertEqual(self.app.records()[0]['status'], 'uploaded')
        self.assertEqual(len(client.notebooks.created),1)
        self.assertEqual(self.app.records()[0]["status"],"uploaded")

    def test_timetable_edit_preserves_partial_upload_destination(self):
        row=self.scan();client=self.client(fail_wait=True)
        with self.assertRaises(TimeoutError): asyncio.run(self.app.upload_one(client,[],row))
        self.app.update(row['id'], status='error')
        self.app.review(row['id'], {'action':'retry'})
        changed=config(str(self.audio));changed['notebook_prefix']='New semester · '
        self.app.save_config(changed)
        self.assertEqual(self.app.records()[0]['route']['title'],'EE221 w3')
        with self.assertRaisesRegex(ValueError,'cannot be reassigned'):
            self.app.review(row['id'], {'course':'OTHER','week':4})

    def test_uncertain_upload_does_not_resend(self):
        row=self.scan();client=self.client(fail_add=True);notebooks=[]
        with self.assertRaises(RuntimeError): asyncio.run(self.app.upload_one(client,notebooks,row))
        with self.assertRaisesRegex(ValueError,"uncertain"): asyncio.run(self.app.upload_one(client,notebooks,self.app.records()[0]))
        self.assertEqual(client.sources.adds,1)

    def test_failure_before_file_selection_allows_a_manual_retry(self):
        row = self.scan()
        client = self.client()
        notebooks = []
        add = client.sources.add_file
        error = ValueError('Upload browser did not open')
        error.upload_started = False
        client.sources.add_file = AsyncMock(side_effect=error)
        with self.assertRaises(ValueError):
            asyncio.run(self.app.upload_one(client, notebooks, row))
        self.assertEqual(self.app.records()[0]['parts'], [])
        self.app.update(row['id'], status='error')
        self.app.review(row['id'], {'action': 'retry'})
        client.sources.add_file = add
        asyncio.run(self.app.upload_one(client, notebooks, self.app.records()[0]))
        self.assertEqual(self.app.records()[0]['status'], 'uploaded')
        self.assertEqual(client.sources.adds, 1)

    def test_existing_notebook_reused(self):
        row=self.scan();client=self.client();notebooks=[SimpleNamespace(id="existing", title="EE221 w3")]
        asyncio.run(self.app.upload_one(client,notebooks,row))
        self.assertEqual(client.notebooks.created,[])
        self.assertEqual(self.app.records()[0]["notebook_id"],"existing")

    def test_manual_assignment_uploads_without_timetable(self):
        self.app.save_config({**config(str(self.audio)), "week_one": "", "lectures": []})
        row = self.scan()
        self.assertEqual(row["status"], "review")
        self.app.review(row["id"], {"course": "TKL201", "week": 4})
        client = self.client()
        client.notebooks.list = AsyncMock(return_value=[])
        context = AsyncMock()
        context.__aenter__.return_value = client
        with patch("notebooklm.NotebookLMClient.from_storage", return_value=context):
            asyncio.run(self.app.sync())
        self.assertEqual(self.app.records()[0]["status"], "uploaded")
        self.assertEqual(client.notebooks.created[0].title, "TKL201 w4")
        self.assertEqual(client.sources.adds, 1)

    def test_sync_uploads_only_selected_recordings(self):
        row = self.scan()
        other = {**row, 'id': 'other-week'}
        client = self.client()
        client.notebooks.list = AsyncMock(return_value=[])
        context = AsyncMock()
        context.__aenter__.return_value = client
        with patch("notebooklm.NotebookLMClient.from_storage", return_value=context), \
             patch.object(self.app, 'records', return_value=[row, other]), \
             patch.object(self.app, 'upload_one', new_callable=AsyncMock) as upload:
            asyncio.run(self.app.sync([row['id']]))
            upload.assert_awaited_once_with(client, [], row)
            upload.reset_mock()
            asyncio.run(self.app.sync([]))
            upload.assert_not_awaited()

    def test_upload_job_preserves_selection_after_scan(self):
        row = self.scan()
        other = {**row, 'id': 'other-week'}
        with patch.object(self.app, 'scan'), \
             patch.object(self.app, 'records', return_value=[row, other]), \
             patch.object(self.app, 'sync', new_callable=AsyncMock) as sync, \
             patch('voice_notebook.threading.Thread', side_effect=lambda target, daemon: SimpleNamespace(start=target)):
            self.app.start('sync', recording_ids=[row['id']])
        sync.assert_awaited_once_with([row['id']])
        self.assertEqual(self.app.upload_batch['recording_ids'], [row['id']])

    def test_two_distinct_recordings_reuse_same_notebook(self):
        row=self.scan();client=self.client();notebooks=[]
        asyncio.run(self.app.upload_one(client,notebooks,row))
        second=self.audio / "20261015-130000.m4a"
        subprocess.run(["ffmpeg","-v","error","-y","-f","lavfi","-i","sine=frequency=880:duration=2","-c:a","aac",str(second)],check=True)
        self.age(second);self.app.scan()
        row2=next(r for r in self.app.records() if r["status"]=="ready")
        asyncio.run(self.app.upload_one(client,notebooks,row2))
        self.assertEqual(len(client.notebooks.created),1)
        self.assertEqual(client.sources.adds,2)


if __name__ == "__main__":
    unittest.main()
