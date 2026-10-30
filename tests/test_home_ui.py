from datetime import datetime
from pathlib import Path
import sys
import unittest
from overview import weekly_overview
import test_ui


class HomeBrowserTests(unittest.TestCase):
    def test_ambiguous_notebook_can_be_assigned_and_synced(self):
        fixture = test_ui.BrowserTests
        fixture.setUpClass()
        try:
            page = fixture.browser.new_page(viewport={'width':1160,'height':900})
            def state_response(route):
                response = route.fetch()
                data = response.json()
                data['permissions'] = {'recordings':'granted','photos_enabled':False}
                data['course_notebook_ambiguities'] = [{'notebook_id':'old','title':'ee w3','courses':['EE211','EE221']}]
                route.fulfill(response=response,json=data)
            requests = []
            def assign(route):
                requests.append(route.request.post_data_json)
                route.fulfill(json={'ok':True})
            syncs = []
            def sync(route):
                syncs.append(True)
                route.fulfill(json={'ok':True})
            page.route('**/api/state',state_response)
            page.route('**/api/course-notebooks/assign',assign)
            page.route('**/api/course-notebooks/sync',sync)
            page.goto(fixture.url)
            page.locator('.tab[data-view="recordings"]').click()
            page.get_by_label('Course for ee w3').select_option('EE211')
            with page.expect_response('**/api/course-notebooks/sync'):
                page.get_by_role('button',name='Assign',exact=True).click()
            self.assertEqual(len(syncs),1)
            self.assertEqual(requests,[{'notebook_id':'old','course':'EE211'}])
            page.close()
        finally:
            fixture.tearDownClass()

    def test_current_week_coverage_optional_permissions_and_audio_only_upload(self):
        from playwright.sync_api import sync_playwright,expect
        BrowserTests=test_ui.BrowserTests
        # Reuse the isolated local server fixture without touching the user's data.
        BrowserTests.setUpClass()
        try:
            page=BrowserTests.browser.new_page(viewport={'width':1160,'height':900})
            cfg={'week_one':'2026-09-28','semester_weeks':16,'timezone':'Europe/Istanbul','tolerance_minutes':10,
                 'lectures':[{'course':'EE221','day':0,'start':'09:00','end':'11:00'},{'course':'MATH201','day':4,'start':'13:00','end':'15:00'}]}
            def recording(rid,course,at,status):return {'id':rid,'path':'/test.m4a','name':course+' recording','recorded_at':at,'duration':3600,'size':123456,'status':status,'route':{'course':course,'week':3,'title':course+' w3'},'notebook_id':'nb' if status=='uploaded' else None,'parts':[],'reason':'Matched','error':None,'date_source':'Test fixture'}
            rows=[recording('a','EE221','2026-10-12T09:00:00+03:00','uploaded'),recording('b','MATH201','2026-10-16T13:00:00+03:00','ready')]
            def fixture(route):
                response=route.fetch();data=response.json();data['config'].update(cfg);data['recordings']=rows;data['overview']=weekly_overview(rows,data['config'],datetime.fromisoformat('2026-10-16T14:00:00+03:00'));data['permissions']={'recordings':'granted','photos':'notDetermined','photos_enabled':False,'native':False};data['photos_available']=False;route.fulfill(response=response,json=data)
            page.route('**/api/state',fixture)
            page.goto(BrowserTests.url)
            expect(page.locator('#home-title')).to_have_text('Week 3')
            expect(page.locator('#home-current')).to_contain_text('Now · MATH201')
            expect(page.locator('#home-coverage')).to_have_text('1 of 1 past classes matched')
            expect(page.locator('#home-captured')).to_have_text('50% audio coverage')
            expect(page.locator('#home-calendar .calendar-now')).to_be_visible()
            expect(page.locator('#home-calendar .current-class')).to_have_count(1)
            page.locator('#home-previous').click()
            expect(page.locator('#home-title')).to_have_text('Week 2')
            expect(page.locator('#home-calendar .calendar-now')).to_have_count(0)
            expect(page.locator('#home-calendar .has-recording')).to_have_count(0)
            page.locator('#home-today').click()
            expect(page.locator('#home-title')).to_have_text('Week 3')
            expect(page.locator('#home-calendar .has-recording')).to_have_count(2)
            expect(page.locator('.tab[data-view="photos"]')).to_have_count(0)
            page.screenshot(path=str(Path(__file__).resolve().parents[1]/'artifacts/home-week.png'),full_page=True)
            page.locator('.tab[data-view="recordings"]').click();page.locator('#sync').click()
            expect(page.locator('#upload-dialog')).to_be_visible();expect(page.locator('#include-photos')).to_be_disabled()
            requests=[]
            def upload(route):requests.append(route.request.post_data_json);route.fulfill(json={'ok':True})
            page.route('**/api/sync',upload);page.locator('#upload-start').click()
            self.assertEqual(requests,[{'include_photos':False,'recording_ids':['b']}])
            page.locator('#upload-close').click();page.locator('.tab[data-view="home"]').click()
            page.set_viewport_size({'width':390,'height':844})
            self.assertFalse(page.evaluate('document.documentElement.scrollWidth > innerWidth'))
            page.screenshot(path=str(Path(__file__).resolve().parents[1]/'artifacts/home-mobile.png'),full_page=True)
            page.close()
        finally:BrowserTests.tearDownClass()
