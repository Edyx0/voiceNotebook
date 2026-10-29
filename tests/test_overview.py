from datetime import datetime
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock,patch
from types import SimpleNamespace
from voice_notebook import App,defaults
from access import Access
from overview import weekly_overview


def config():return {**defaults(),'week_one':'2026-09-28','lectures':[{'course':'EE221','day':0,'start':'09:00','end':'11:00'},{'course':'MATH201','day':4,'start':'13:00','end':'15:00'}]}
def recording(rid='a',at='2026-10-12T09:00:00+03:00',duration=3600):return {'id':rid,'recorded_at':at,'duration':duration,'status':'uploaded','notebook_id':'nb','route':{'course':'EE221','week':3,'title':'EE221 w3'}}


class OverviewTests(unittest.TestCase):
    def test_current_week_class_and_past_coverage(self):
        result=weekly_overview([recording()],config(),datetime.fromisoformat('2026-10-16T14:00:00+03:00'))
        self.assertEqual(result['week'],3);self.assertEqual(result['current']['course'],'MATH201')
        self.assertEqual(result['past_count'],1);self.assertEqual(result['matched_count'],1);self.assertEqual(result['coverage_percent'],50)

    def test_overlapping_audio_is_counted_once(self):
        result=weekly_overview([recording(),recording('b','2026-10-12T09:30:00+03:00')],config(),datetime.fromisoformat('2026-10-16T14:00:00+03:00'))
        self.assertEqual(result['coverage_percent'],75)

    def test_future_and_ignored_recordings_do_not_inflate_coverage(self):
        row=recording();row['status']='ignored'
        result=weekly_overview([row],config(),datetime.fromisoformat('2026-10-12T08:00:00+03:00'))
        self.assertEqual(result['past_count'],0);self.assertIsNone(result['coverage_percent']);self.assertEqual(result['next']['course'],'EE221')

    def test_missing_semester_and_outside_semester(self):
        self.assertIsNone(weekly_overview([],defaults())['week'])
        self.assertEqual(weekly_overview([],config(),datetime.fromisoformat('2026-09-01T09:00:00+03:00'))['season'],'upcoming')

    def test_timezone_and_week_assignment(self):
        result=weekly_overview([recording()],config(),datetime.fromisoformat('2026-10-16T11:00:00+00:00'))
        self.assertEqual(result['current']['course'],'MATH201')


class AccessTests(unittest.TestCase):
    def test_source_folder_and_optional_photos(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict('os.environ',{},clear=True):
            result=Access().read(tmp)
            self.assertEqual(result['recordings'],'granted');self.assertFalse(result['photos_enabled'])
            self.assertEqual(Access().read(tmp+'/missing')['recordings'],'missing')

    def test_permission_probe_is_read_only_and_can_detect_limited_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            helper=Path(tmp)/'native';helper.touch()
            with patch.dict('os.environ',{'VOICE_NOTEBOOK_PHOTOS_HELPER':str(helper)}),patch('access.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='{"photos":"limited"}')) as run:
                result=Access().read(tmp)
                self.assertTrue(result['photos_enabled']);self.assertEqual(run.call_args.args[0],[str(helper),'--permissions'])


class UploadWorkflowTests(unittest.TestCase):
    def test_audio_only_does_not_scan_or_require_photos(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(Path(tmp));app.scan=lambda:None;app.sync=AsyncMock()
            with patch.object(app.photos,'scan') as photos:
                app.start('sync')
                for _ in range(100):
                    if not app.job['busy']:break
                    time.sleep(.01)
                photos.assert_not_called();self.assertIsNone(app.job['error'])

    def test_photos_option_requires_actual_grant(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(Path(tmp))
            with patch.object(app.access,'read',return_value={'photos_enabled':False}):
                with self.assertRaisesRegex(ValueError,'Photos access is optional'):app.start('sync',include_photos=True)

    def test_optional_photo_failure_preserves_completed_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=App(Path(tmp));app.scan=lambda:None;app.sync=AsyncMock()
            with patch.object(app.access,'read',return_value={'photos_enabled':True}),patch.object(app.photos,'scan',side_effect=ValueError('Photos unavailable')):
                app.start('sync',include_photos=True)
                for _ in range(100):
                    if not app.job['busy']:break
                    time.sleep(.01)
                self.assertEqual(app.upload_batch['stage'],'complete');self.assertEqual(app.upload_batch['photo_error'],'Photos unavailable');self.assertIsNone(app.job['error'])
