"""Regressions found while checking the app's existing user workflows."""
import asyncio
from datetime import datetime
from pathlib import Path
import tempfile
import subprocess
import sys
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from voice_notebook import App, defaults, validate_config
from overview import weekly_overview
import test_ui
import test_class_photos


class UploadResultTests(unittest.TestCase):
    def test_blank_course_cannot_save_an_invisible_class(self):
        for course in ['   ', '', None, 123]:
            with self.subTest(course=course), self.assertRaises(ValueError):
                validate_config({**defaults(), 'lectures': [
                    {'course': course, 'day': 0, 'start': '09:00', 'end': '10:00'}]})

    def test_audio_failure_is_visible_in_the_job_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = App(Path(tmp))
            row = {'id': 'missing', 'status': 'ready', 'route': {'title': 'EE211 w5'}}
            client = SimpleNamespace(notebooks=SimpleNamespace(list=AsyncMock(return_value=[])))
            session = AsyncMock()
            session.__aenter__.return_value = client
            with patch('notebooklm.NotebookLMClient.from_storage', return_value=session), \
                 patch('voice_notebook.shutil.which', return_value='ffmpeg'), \
                 patch.object(app, 'records', return_value=[row]), \
                 patch.object(app, 'upload_one', new_callable=AsyncMock, side_effect=RuntimeError('offline')):
                asyncio.run(app.sync())
            self.assertIn('1 recording', app.job['error'])

    def test_photo_failure_is_visible_in_the_job_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = App(Path(tmp))
            session = AsyncMock()
            session.__aenter__.return_value = SimpleNamespace()
            with patch('notebooklm.NotebookLMClient.from_storage', return_value=session), \
                 patch.object(app.access, 'read', return_value={'photos_enabled': True}), \
                 patch.object(app.photos, 'records', return_value=[{'id': 'missing', 'status': 'approved'}]), \
                 patch.object(app.photos, 'upload_one', new_callable=AsyncMock, side_effect=RuntimeError('offline')):
                asyncio.run(app.photos.sync())
            self.assertIn('1 photo', app.job['error'])


class CalendarWorkflowTests(unittest.TestCase):
    def test_local_week_boundary_and_empty_class_keep_the_right_scope(self):
        from playwright.sync_api import expect
        fixture = test_ui.BrowserTests
        fixture.setUpClass()
        try:
            page = fixture.browser.new_page()
            page.add_init_script("Date.now = () => Date.parse('2026-11-01T22:00:00Z')")

            def state_response(route):
                response = route.fetch()
                data = response.json()
                data['config'].update(week_one='2026-09-28', timezone='Europe/Istanbul',
                    lectures=[{'course': 'EE211', 'day': 0, 'start': '09:00', 'end': '11:00'}])
                data['recordings'] = [{'id': 'older', 'name': 'Other week', 'recorded_at': '2026-10-26T09:00:00+03:00',
                    'duration': 3600, 'size': 123456, 'status': 'ready', 'parts': [], 'error': None, 'reason': 'Matched',
                    'route': {'course': 'EE211', 'week': 5, 'title': 'EE211 w5'}, 'notebook_id': None}]
                data['overview'] = weekly_overview(data['recordings'], data['config'], datetime.fromisoformat('2026-11-02T01:00:00+03:00'))
                data['permissions'] = {'recordings': 'granted', 'photos_enabled': False}
                route.fulfill(response=response, json=data)

            page.route('**/api/state', state_response)
            page.goto(fixture.url)
            expect(page.locator('#home-title')).to_have_text('Week 6')
            page.locator('#home-import').click()
            expect(page.locator('#calendar-week')).to_have_value('6')
            page.locator('.tab[data-view="home"]').click()
            page.locator('#home-calendar .calendar-event[data-course="EE211"]').click()
            expect(page.locator('#recording-list .recording')).to_have_count(0)
            expect(page.locator('#sync')).to_be_disabled()
            expect(page.locator('#queue-description')).to_be_empty()
            page.evaluate('refresh()')
            expect(page.locator('#sync')).to_be_disabled()
            expect(page.locator('#recording-list h2')).to_have_text('No recordings for this class.')
            expect(page.locator('#notice')).to_have_text('No recording matched this class yet.')
            page.locator('.tab[data-view="recordings"]').click()
            expect(page.locator('#recording-list .recording')).to_have_count(1)
            expect(page.locator('#sync')).to_be_enabled()
            page.close()
        finally:
            fixture.tearDownClass()


class PhotoRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_class_photos.PhotoTests()
        self.fixture.setUp()
        self.fixture.ingest()
        self.fixture.approve()

    def tearDown(self):
        self.fixture.tearDown()

    def make_document(self, command, **kwargs):
        self.assertEqual(command[1], '--photo-document')
        Path(command[3]).write_bytes(b'%PDF-local-photo-and-text')
        return subprocess.CompletedProcess(command, 0)

    def test_rejected_photo_uses_local_searchable_pdf_and_keeps_original(self):
        from notebooklm.exceptions import SourceProcessingError
        fixture = self.fixture
        client = fixture.client()
        failed = SimpleNamespace(id='failed-image', title='photo.jpg', is_error=True)
        client.sources.list.side_effect = [[], [failed]]
        client.sources.add_file.side_effect = [SourceProcessingError(failed.id), SimpleNamespace(id='pdf-source')]
        with patch.dict('os.environ', {'VOICE_NOTEBOOK_PHOTOS_HELPER': sys.executable}), \
             patch('class_photos.subprocess.run', side_effect=self.make_document):
            asyncio.run(fixture.app.photos.upload_one(client, fixture.photo()))
        self.assertEqual(fixture.photo()['status'], 'uploaded')
        self.assertEqual(fixture.photo()['source_id'], 'pdf-source')
        self.assertEqual(client.sources.add_file.await_args.args[1].suffix, '.pdf')
        self.assertEqual(fixture.image.read_bytes(), b'reviewed jpeg bytes')

    def test_lost_pdf_response_is_not_blindly_resent_after_restart(self):
        from notebooklm.exceptions import SourceProcessingError
        fixture = self.fixture
        client = fixture.client()
        failed = SimpleNamespace(id='failed-image', title='photo.jpg', is_error=True)
        client.sources.list.side_effect = [[], [failed]]
        client.sources.add_file.side_effect = [SourceProcessingError(failed.id), RuntimeError('lost PDF response')]
        with patch.dict('os.environ', {'VOICE_NOTEBOOK_PHOTOS_HELPER': sys.executable}), \
             patch('class_photos.subprocess.run', side_effect=self.make_document):
            with self.assertRaisesRegex(RuntimeError, 'lost PDF response'):
                asyncio.run(fixture.app.photos.upload_one(client, fixture.photo()))
        fixture.app = App(Path(fixture.tmp.name))
        fixture.app.photos.review(fixture.pid, 'retry')
        client.sources.list.side_effect = None
        client.sources.list.return_value = [failed]
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            asyncio.run(fixture.app.photos.upload_one(client, fixture.photo()))
        self.assertEqual(client.sources.add_file.await_count, 2)

    def test_processing_failure_after_registration_also_recovers(self):
        from notebooklm.exceptions import SourceProcessingError
        fixture = self.fixture
        client = fixture.client()
        failed = SimpleNamespace(id='image-source', title='photo.jpg', is_error=True)
        client.sources.list.side_effect = [[], [failed]]
        client.sources.add_file.side_effect = [SimpleNamespace(id=failed.id), SimpleNamespace(id='pdf-source')]
        client.sources.wait_until_ready.side_effect = [SourceProcessingError(failed.id), None]
        with patch.dict('os.environ', {'VOICE_NOTEBOOK_PHOTOS_HELPER': sys.executable}), \
             patch('class_photos.subprocess.run', side_effect=self.make_document):
            asyncio.run(fixture.app.photos.upload_one(client, fixture.photo()))
        self.assertEqual(fixture.photo()['status'], 'uploaded')
        self.assertEqual(fixture.photo()['source_id'], 'pdf-source')

    def test_failed_local_ocr_does_not_send_an_unverified_document(self):
        from notebooklm.exceptions import SourceProcessingError
        fixture = self.fixture
        client = fixture.client()
        client.sources.add_file.side_effect = SourceProcessingError('failed-image')
        with patch.dict('os.environ', {'VOICE_NOTEBOOK_PHOTOS_HELPER': sys.executable}), \
             patch('class_photos.subprocess.run', return_value=subprocess.CompletedProcess([], 1)):
            with self.assertRaisesRegex(ValueError, 'local PDF recovery failed'):
                asyncio.run(fixture.app.photos.upload_one(client, fixture.photo()))
        self.assertEqual(client.sources.add_file.await_count, 1)


class BuildSigningTests(unittest.TestCase):
    def test_default_rebuild_reuses_the_installed_apple_identity(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / 'Applications/voiceNotebook.app').mkdir(parents=True)
            tool = home / 'codesign'
            tool.write_text('#!/bin/sh\ncase "$*" in *--verbose=4*) echo "Authority=Apple Development: Test Identity" >&2;; esac\n')
            tool.chmod(0o700)
            prefix = (root / 'mac/build.sh').read_text().split('mkdir -p build', 1)[0]
            env = {**os.environ, 'HOME': tmp, 'PATH': tmp + os.pathsep + os.environ['PATH']}
            env.pop('VOICE_NOTEBOOK_SIGNING_IDENTITY', None)
            result = subprocess.run(['bash', '-c', prefix + '\nprintf "%s" "$SIGNING_IDENTITY"', str(root / 'mac/build.sh')],
                                    env=env, capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout, 'Apple Development: Test Identity')
