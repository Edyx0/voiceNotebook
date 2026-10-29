"""First-run guidance and permission preflight without changing macOS permissions."""
from pathlib import Path
import unittest
import test_ui


class OnboardingTests(unittest.TestCase):
    def test_first_run_optional_photos_and_completion(self):
        from playwright.sync_api import expect
        server=test_ui.BrowserTests
        server.setUpClass()
        try:
            page=server.browser.new_page(viewport={'width':1100,'height':850})
            page.add_init_script("window.nativeCalls=[];window.webkit={messageHandlers:{native:{postMessage:m=>window.nativeCalls.push(m)}}};")
            def fixture(route):
                response=route.fetch();data=response.json()
                data['permissions']={'recordings':'granted','photos':'notDetermined','photos_enabled':False,'native':True}
                route.fulfill(response=response,json=data)
            page.route('**/api/state',fixture)
            page.goto(server.url)
            expect(page.locator('#onboarding-dialog')).not_to_be_visible()
            self.assertEqual(page.evaluate('nativeCalls'),[])
            page.locator('#continue-onboarding').click()
            expect(page.locator('#onboarding-title')).to_have_text('Your lectures. In order.')
            page.locator('#onboarding-next').click()
            expect(page.locator('#onboarding-copy')).to_contain_text('EE221 w3')
            page.locator('#onboarding-next').click()
            expect(page.locator('#onboarding-step')).to_have_text('3 / 3')
            page.screenshot(path=str(Path(__file__).resolve().parents[1]/'artifacts/onboarding.png'))
            page.locator('#onboarding-next').click()
            expect(page.locator('#onboarding-dialog')).not_to_be_visible()
            page.goto(server.url+'/?settings=1')
            page.locator('#photos-grant').click()
            expect(page.locator('#photos-explanation')).to_be_visible()
            self.assertEqual(page.evaluate('nativeCalls'),[])
            page.locator('#photos-not-now').click()
            self.assertEqual(page.evaluate('nativeCalls'),[])
            page.locator('#photos-grant').click();page.locator('#photos-continue').click()
            self.assertEqual(page.evaluate('nativeCalls'),[{'action':'photosAccess'}])
            page.goto(server.url);expect(page.locator('#onboarding-dialog')).not_to_be_visible()
            page.locator('.tab[data-view="recordings"]').click()
            expect(page.locator('#setup-nudge')).to_have_count(0)
            page.evaluate("view('connection')")
            page.get_by_text('How NotebookLM works',exact=True).click()
            expect(page.locator('.connection-help')).to_contain_text('default browser')
            self.assertNotIn('Chrome',page.locator('.connection-help').inner_text())
            page.close()
        finally:
            server.tearDownClass()
