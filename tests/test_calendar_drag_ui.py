import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import time
import unittest

import test_ui

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec('playwright') and shutil.which('ffmpeg'), 'Playwright and FFmpeg required')
class CalendarDragBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_ui.BrowserTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        test_ui.BrowserTests.tearDownClass.__func__(cls)

    def test_calendar_drag_is_a_reviewable_weekly_draft(self):
        from playwright.sync_api import expect
        p=self.browser.new_page(viewport={'width':1440,'height':1100})
        errors=[]
        p.on('pageerror',lambda error:errors.append(str(error)))
        second=self.folder/'20261012-110000.qta'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=880:duration=2','-c:a','aac','-f','ipod',str(second)],check=True)
        os.utime(second,(time.time()-600,time.time()-600))
        p.goto(self.url)
        state=p.request.get(self.url+'/api/state').json()
        config={**state['config'],'recordings_folder':str(self.folder),'week_one':'2026-10-12','auto_sync':False,
                'lectures':[{'course':'EE221','day':0,'start':'09:00','end':'10:00'},
                            {'course':'MATH201','day':0,'start':'11:00','end':'13:00'}]}
        headers={'X-App-Token':state['token']}
        self.assertEqual(p.request.post(self.url+'/api/config',data=config,headers=headers).status,200)
        self.assertEqual(p.request.post(self.url+'/api/scan',data={},headers=headers).status,200)
        p.wait_for_function("fetch('/api/state').then(r=>r.json()).then(s=>!s.job.busy&&s.recordings.length===2)",timeout=20000)
        for row in p.request.get(self.url+'/api/state').json()['recordings']:
            first=row['name'].startswith('20261012-090000')
            review={'id':row['id'],'course':'EE221' if first else 'MATH201','week':1,
                    'recorded_at':'2026-10-12T09:00:00+03:00' if first else '2026-10-12T11:00:00+03:00'}
            response=p.request.post(self.url+'/api/review',data=review,headers=headers)
            self.assertEqual(response.status,200,response.json())
        p.reload()
        p.locator('.tab[data-view="setup"]').click()
        p.locator('#calendar-week').select_option('1')
        calendar=p.locator('#weekly-calendar')
        expect(calendar.locator('.calendar-event.has-recording')).to_have_count(2,timeout=15000)
        self.assertEqual(calendar.locator('.calendar-day').count(),7)
        self.assertGreater(calendar.locator('.calendar-scroll').evaluate('el=>el.scrollTop'),400)
        calendar.locator('.calendar-scroll').evaluate('el=>el.scrollTop=700')
        p.evaluate('renderTimetable()')
        self.assertEqual(calendar.locator('.calendar-scroll').evaluate('el=>el.scrollTop'),700)
        calendar.locator('.calendar-scroll').evaluate('el=>el.scrollTop=(9*60-75)*1.2')
        for course in ['EE221','MATH201']:
            event=calendar.locator(f'.calendar-event[data-course="{course}"]')
            bounds=event.evaluate("el=>{const box=el.getBoundingClientRect(),first=el.querySelector('strong').getBoundingClientRect(),last=el.querySelector('.recording-mark').getBoundingClientRect();return {top:first.top-box.top,bottom:box.bottom-last.bottom}}")
            self.assertGreater(bounds['bottom'],5)
            self.assertLess(abs(bounds['top']-bounds['bottom']),3)
        p.locator('#semester-settings').evaluate('(el)=>el.open=true')
        checkbox=p.locator('#auto-sync').bounding_box()
        text=p.locator('#semester-settings .check span').bounding_box()
        self.assertLess(abs((checkbox['y']+checkbox['height']/2)-(text['y']+text['height']/2)),1.5)
        (ROOT/'artifacts').mkdir(exist_ok=True)
        p.screenshot(path=str(ROOT/'artifacts/calendar-alignment.png'))
        p.locator('#semester-settings').screenshot(path=str(ROOT/'artifacts/calendar-settings.png'))
        calendar.locator('.calendar-event[data-course="EE221"]').focus()
        p.keyboard.press('Enter')
        expect(p.locator('#lecture-editor')).to_be_visible()
        p.locator('#lecture-cancel').click()

        def drag(root,course,day,minute,cancel=False):
            scroll=root.locator('.calendar-scroll')
            scroll.evaluate('el=>el.scrollTop=8*60*1.2')
            source=root.locator(f'.calendar-event[data-course="{course}"]')
            source.scroll_into_view_if_needed()
            box=source.bounding_box()
            target=root.locator(f'.calendar-day[data-day="{day}"]').bounding_box()
            offset=12
            p.mouse.move(box['x']+box['width']/2,box['y']+offset)
            p.mouse.down()
            p.mouse.move(target['x']+target['width']/2,target['y']+minute*1.2+offset,steps=12)
            expect(root.locator('.calendar-drop-preview')).to_be_visible()
            if cancel:p.keyboard.press('Escape')
            p.mouse.up()

        drag(calendar,'EE221',4,10*60,cancel=True)
        expect(calendar.locator('.calendar-drop-preview')).to_have_count(0)
        expect(calendar.locator('.calendar-day[data-day="0"] .calendar-event[data-course="EE221"]')).to_have_count(1)
        expect(p.locator('#calendar-draft')).to_have_text('')
        calendar.locator('.calendar-event[data-course="EE221"]').click()
        expect(p.locator('#lecture-editor')).to_be_visible()
        p.locator('#lecture-cancel').click()
        scroll=calendar.locator('.calendar-scroll')
        scroll.evaluate('el=>el.scrollTop=8*60*1.2')
        source=calendar.locator('.calendar-event[data-course="EE221"]')
        source.scroll_into_view_if_needed()
        box=source.bounding_box();bounds=scroll.bounding_box();before=scroll.evaluate('el=>el.scrollTop')
        p.mouse.move(box['x']+box['width']/2,box['y']+12)
        p.mouse.down()
        p.mouse.move(bounds['x']+bounds['width']/2,bounds['y']+bounds['height']-8,steps=12)
        p.wait_for_function("initial=>document.querySelector('#weekly-calendar .calendar-scroll').scrollTop>initial+16",arg=before)
        p.keyboard.press('Escape');p.mouse.up()
        expect(calendar.locator('.calendar-drop-preview')).to_have_count(0)
        drag(calendar,'EE221',3,11*60+15)
        moved=calendar.locator('.calendar-day[data-day="3"] .calendar-event[data-course="EE221"]')
        expect(moved).to_contain_text('11:15–12:15')
        expect(p.locator('#calendar-draft')).to_have_text('Unsaved changes')
        expect(p.locator('#notice')).to_have_text('This move affects every week. Review and save the timetable to apply.')
        self.assertEqual(p.request.get(self.url+'/api/state').json()['config']['lectures'][0]['day'],0)
        p.get_by_role('button',name='Save timetable',exact=True).click()
        expect(p.locator('#recordings-view')).to_be_visible()
        saved=p.request.get(self.url+'/api/state').json()['config']['lectures'][0]
        self.assertEqual((saved['day'],saved['start'],saved['end']),(3,'11:15','12:15'))

        p.locator('.tab[data-view="setup"]').click()
        p.locator('#add-slot').click()
        p.locator('#lecture-course').fill('EXTRA')
        p.locator('#lecture-form').get_by_role('button',name='Done',exact=True).click()
        p.locator('.tab[data-view="home"]').click()
        home=p.locator('#home-calendar')
        expect(home.locator('.calendar-event[data-course="MATH201"]')).to_have_count(1)
        drag(home,'MATH201',5,14*60)
        expect(p.locator('#setup-view')).to_be_visible()
        expect(calendar.locator('.calendar-day[data-day="5"] .calendar-event[data-course="MATH201"]')).to_contain_text('14:00–16:00')
        expect(calendar.locator('.calendar-event[data-course="EXTRA"]')).to_have_count(1)
        expect(p.locator('#calendar-draft')).to_have_text('Unsaved changes')
        self.assertEqual(p.request.get(self.url+'/api/state').json()['config']['lectures'][1]['day'],0)
        self.assertEqual(len(p.request.get(self.url+'/api/state').json()['config']['lectures']),2)
        self.assertEqual(errors,[])
        p.close()


