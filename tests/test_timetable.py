import base64
import json
from pathlib import Path
import unittest

from timetable import days_in, parse_observations, recognize_photo, times_in


def item(text,x=.1,y=.1,w=.7,h=.035):
    return {'text':text,'x':x,'y':y,'width':w,'height':h,'confidence':.99}


class TimetablePhotoTests(unittest.TestCase):
    def test_turkish_day_abbreviations(self):
        self.assertEqual([d for d,_,_ in days_in('Pzt Sal Çar Per Cum Cmt Paz')],list(range(7)))

    def test_hour_only_axis_ranges(self):
        for text in ('9-10', '09 – 10', '9—10'):
            self.assertEqual(times_in(text),['09:00','10:00'])
        for text in ('10-9', '23-24', '25-26', 'ROOM 9-10', 'CSE 211-212'):
            self.assertEqual(times_in(text),[])

    def test_supplied_mobile_timetable(self):
        observations=json.loads((Path(__file__).parent/'fixtures/timetable_mobile_ocr.json').read_text())
        result=parse_observations(observations)
        self.assertEqual(sorted((r['day'],r['course'],r['start'],r['end']) for r in result['slots']),sorted([
            (0,'TKL201','09:00','11:00'),(0,'CSE211','11:00','13:00'),
            (0,'CSE221','13:00','14:00'),(0,'HUM103','14:00','16:00'),(0,'HTR301','16:00','18:00'),
            (1,'CSE211','13:00','14:00'),(1,'EE211','14:00','16:00'),(1,'CSE211','16:00','18:00'),
            (2,'EE211','14:00','16:00'),(2,'CSE221','16:00','18:00'),
            (3,'EE211','13:00','14:00'),(3,'CSE221','16:00','18:00')]))
        self.assertTrue(all(r['needs_review'] for r in result['slots']))

    def test_unreadable_axis_is_not_filled_or_merged(self):
        result=parse_observations([
            item('Pzt',.15,.1,.10),item('Sal',.55,.1,.10),
            item('9-10',.02,.3,.10),item('CSE211',.15,.3,.10),
            item('CSE211',.15,.36,.10),item('CSE211',.15,.42,.10),
            item('12-13',.02,.48,.10),item('CSE211',.15,.48,.10)])
        self.assertEqual([(r['start'],r['end']) for r in result['slots']],
                         [('09:00','10:00'),('',''),('',''),('12:00','13:00')])

    def test_english_and_turkish_list_rows(self):
        result=parse_observations([item('Monday EE221 09:00-11:00',y=.1),item('Çarşamba MAT 201 13.00-15.00',y=.3)])
        self.assertEqual([(r['course'],r['day'],r['start'],r['end']) for r in result['slots']],
                         [('EE221',0,'09:00','11:00'),('MAT201',2,'13:00','15:00')])

    def test_grid_with_separate_time_lines(self):
        result=parse_observations([item('Monday',.25,.1,.15),item('Tuesday',.65,.1,.15),
                                   item('EE221',.25,.3,.15),item('09:00-11:00',.24,.35,.18),
                                   item('MATH201',.65,.3,.15),item('13:00-15:00',.64,.35,.18)])
        self.assertEqual([(r['day'],r['start'],r['end']) for r in result['slots']],[(0,'09:00','11:00'),(1,'13:00','15:00')])

    def test_missing_times_and_day_are_not_invented(self):
        result=parse_observations([item('EE221')])
        self.assertEqual(result['slots'][0]['day'],None)
        self.assertEqual(result['slots'][0]['start'],'')
        self.assertEqual(result['slots'][0]['end'],'')
        self.assertTrue(result['warnings'])

    def test_visible_start_without_end_stays_incomplete(self):
        result=parse_observations([item('Friday EE221 09:00')])
        self.assertEqual(result['slots'][0]['start'],'09:00')
        self.assertEqual(result['slots'][0]['end'],'')

    def test_room_numbers_not_imported_as_courses(self):
        result=parse_observations([item('Monday EE221 ROOM101 09:00-11:00')])
        self.assertEqual([r['course'] for r in result['slots']],['EE221'])

    def test_invalid_image_is_rejected(self):
        with self.assertRaises(ValueError): recognize_photo('bad-base64',Path('/missing'))
        with self.assertRaises(ValueError): recognize_photo(base64.b64encode(b'not an image').decode(),Path('/missing'))

    def test_no_text_produces_review_guidance(self):
        result=parse_observations([])
        self.assertEqual(result['slots'],[])
        self.assertIn('sharper',result['warnings'][0])
