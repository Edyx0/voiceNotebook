from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from voice_notebook import App
from recording_library import title_weeks, audio_range


class RecordingLibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_title_markers_and_ranges_without_guessing_course_numbers(self):
        for title in ('tkl w3', 'EE Week3', 'Week 3 / HUM', 'HTR hafta 3'):
            self.assertEqual(title_weeks(title), (3, 3))
        self.assertEqual(title_weeks('htr w1-2'), (1, 2))
        for title in ('CSE211', 'window3', 'week 99', 'w0', 'week3notes', ''):
            self.assertIsNone(title_weeks(title))

    def test_recent_notebook_week_labels_dates_and_preserves_assignments(self):
        library = self.app.library
        library.cache_notebooks([
            SimpleNamespace(id='old', title='htr w1-2', created_at=datetime.fromisoformat('2026-10-11T21:00:00+00:00')),
            SimpleNamespace(id='latest', title='tkl Week3', created_at=datetime.fromisoformat('2026-10-16T08:00:00+00:00')),
        ])
        def row(rid, at, route=None, notebook_id=None):
            return dict(id=rid, name='Original', recorded_at=at, route=route, notebook_id=notebook_id, reason='Add week 1 and your timetable in Setup.')
        rows = library.annotate([
            row('this', '2026-10-12T09:00:00+03:00'),
            row('before', '2026-10-05T09:00:00+03:00'),
            row('range', None, notebook_id='old'),
            row('manual', '2026-10-12T09:00:00+03:00', route={'week': 5}),
            row('unknown', None), row('ancient', '2024-01-01T09:00:00+03:00'),
        ])
        self.assertEqual([r['week_label'] for r in rows], ['Week 3', 'Week 2', 'Week 1–2', 'Week 5', 'Unassigned week', 'Unassigned week'])
        self.assertIsNone(rows[0]['route'])
        self.assertEqual(rows[0]['reason'], '')
        self.assertIn('Estimated', rows[0]['week_source'])

    def test_local_rename_survives_restart_without_changing_original(self):
        original = Path(self.tmp.name) / 'original.qta'
        original.write_bytes(b'original')
        with self.app.db() as db:
            db.execute('INSERT INTO recordings(id,path,name) VALUES(?,?,?)', ('a', str(original), original.name))
        self.app.library.rename('a', 'Lecture notes')
        restarted = App(Path(self.tmp.name))
        self.assertEqual(restarted.records()[0]['display_name'], 'Lecture notes')
        self.assertEqual(restarted.records()[0]['name'], 'original.qta')
        self.assertEqual(original.read_bytes(), b'original')
        for name in ('', '  ', 'a\nb', 'x' * 161, None):
            with self.assertRaises(ValueError):
                self.app.library.rename('a', name)
        with self.assertRaisesRegex(ValueError, 'not found'):
            self.app.library.rename('missing', 'Notes')

    def test_audio_ranges_support_seek_and_suffix(self):
        self.assertEqual(audio_range(None, 100), (0, 99, False))
        self.assertEqual(audio_range('bytes=10-19', 100), (10, 19, True))
        self.assertEqual(audio_range('bytes=80-', 100), (80, 99, True))
        self.assertEqual(audio_range('bytes=-5', 100), (95, 99, True))
        for header in ('bytes=100-', 'bytes=20-10', 'bytes=-0', 'bytes=1-2,3-4', 'invalid'):
            with self.assertRaises(ValueError):
                audio_range(header, 100)


if __name__ == '__main__':
    unittest.main()
