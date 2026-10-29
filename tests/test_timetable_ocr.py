"""Run the native OCR against the supplied screenshot when explicitly available."""
import json
import os
from pathlib import Path
import subprocess
import unittest

from timetable import parse_observations


class NativeTimetableTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('TIMETABLE_TEST_IMAGE'), 'Set TIMETABLE_TEST_IMAGE for native OCR')
    def test_phone_screenshot_cells(self):
        root = Path(__file__).resolve().parents[1]
        output = subprocess.check_output(
            [str(root / 'build/timetable-ocr'), os.environ['TIMETABLE_TEST_IMAGE']],
            text=True, timeout=90)
        slots = parse_observations(json.loads(output)['observations'])['slots']
        actual = sorted((s['day'], s['course'], s['start'], s['end']) for s in slots)
        self.assertEqual(actual, sorted([
            (0, 'TKL201', '09:00', '11:00'), (0, 'CSE211', '11:00', '13:00'),
            (0, 'CSE221', '13:00', '14:00'), (0, 'HUM103', '14:00', '16:00'),
            (0, 'HTR301', '16:00', '18:00'), (1, 'CSE211', '13:00', '14:00'),
            (1, 'EE211', '14:00', '16:00'), (1, 'CSE211', '16:00', '18:00'),
            (2, 'EE211', '14:00', '16:00'), (2, 'CSE221', '16:00', '18:00'),
            (3, 'EE211', '13:00', '14:00'), (3, 'CSE221', '16:00', '18:00'),
        ]))
        self.assertTrue(all(s['needs_review'] for s in slots))
