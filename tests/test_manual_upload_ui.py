"""Manually reviewed destinations do not require a timetable."""
import unittest

import test_ui


class ManualUploadBrowserTests(unittest.TestCase):
    def test_upload_enabled_for_manual_assignment_without_timetable(self):
        from playwright.sync_api import expect

        BrowserTests = test_ui.BrowserTests
        BrowserTests.setUpClass()
        try:
            page = BrowserTests.browser.new_page()

            def fixture(route):
                response = route.fetch()
                data = response.json()
                data['config'].update(week_one='', lectures=[])
                data['permissions']['recordings'] = 'granted'
                data['recordings'] = [{
                    'id': 'manual', 'name': 'Lecture.m4a', 'status': 'ready',
                    'manual': 1, 'route': {'course': 'TKL201', 'week': 4, 'title': 'TKL201 w4'},
                    'parts': [], 'duration': 60, 'size': 1000,
                    'recorded_at': '2026-10-20T09:00:00+03:00',
                }]
                route.fulfill(response=response, json=data)

            page.route('**/api/state', fixture)
            page.goto(BrowserTests.url)
            page.locator('.tab[data-view="recordings"]').click()
            expect(page.locator('#sync')).to_be_enabled()
            page.locator('#sync').click()
            expect(page.locator('#upload-summary')).to_have_text('1 recording → weekly notebooks')
            requests = []

            def upload(route):
                requests.append(route.request.post_data_json)
                route.fulfill(json={'ok': True})

            page.route('**/api/sync', upload)
            page.locator('#upload-start').click()
            self.assertEqual(requests, [{'include_photos': False, 'recording_ids': ['manual']}])
            page.close()
        finally:
            BrowserTests.tearDownClass()
