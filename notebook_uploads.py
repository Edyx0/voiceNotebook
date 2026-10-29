"""Use Google's working file picker while keeping SDK source reconciliation."""
import asyncio
import json
import logging
import re
from pathlib import Path
import sys
import time
from urllib.parse import quote, urlencode

logger = logging.getLogger(__name__)


def browser_options():
    options = {'headless': True}
    if getattr(sys, 'frozen', False):
        root = Path(sys.executable).parents[1] / 'browser'
        executables = sorted((p for p in root.glob('**/*.app/Contents/MacOS/*') if p.is_file()),
                             key=lambda p: len(p.parts))
        if not executables:
            raise ValueError('The bundled upload browser is missing. Reinstall voiceNotebook.')
        options['executable_path'] = str(executables[0])
    return options


def browser_storage(path):
    state = json.loads(Path(path).read_text())
    # Safari's unspecified SameSite imports as None; Chromium rejects that on non-secure cookies.
    for cookie in state.get('cookies', []):
        if cookie.get('sameSite') == 'None' and not cookie.get('secure'):
            cookie['sameSite'] = 'Lax'
    return state


async def click_upload_control(page, control):
    from playwright.async_api import TimeoutError

    try:
        await control.click(timeout=10000)
    except TimeoutError:
        if not await page.get_by_role('heading', name='New background queue', exact=True).is_visible():
            raise
        await page.get_by_role('button', name='Close dialog', exact=True).last.click()
        await control.click()


async def upload_in_browser(client, notebook_id, file_path):
    from notebooklm.paths import get_storage_path
    from playwright.async_api import async_playwright

    file = Path(file_path).resolve(strict=True)
    if not file.is_file() or file.stat().st_size == 0:
        raise ValueError('Choose a non-empty upload file.')
    before = {source.id for source in await client.sources.list(notebook_id)}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(**browser_options())
        upload_started = False
        try:
            storage = browser_storage(get_storage_path())
            query = '?' + urlencode({'authuser': storage.get('notebooklm', {}).get('account', {}).get('authuser', 0)})
            context = await browser.new_context(storage_state=storage, locale='en-US',
                                                viewport={'width': 1440, 'height': 1000})
            page = await context.new_page()
            await page.goto('https://notebook.google.com/' + query, wait_until='domcontentloaded', timeout=60000)
            if 'accounts.google.com' in page.url:
                raise ValueError('The upload browser needs a fresh Google session. Sign in again.')
            await page.locator('a[href*="/notebook/"]').first.wait_for(timeout=60000)
            await page.goto('https://notebook.google.com/notebook/' + quote(notebook_id, safe='') + query,
                            wait_until='domcontentloaded', timeout=60000)
            logger.info('Opening file picker for %s', file.name)
            try:
                upload = page.get_by_role('button', name='Upload files', exact=True)
                add = page.get_by_role('button', name=re.compile(r'^Add sources?$'))
                announcement = page.get_by_role('button', name='Close dialog', exact=True).last
                await upload.or_(add).or_(announcement).first.wait_for(timeout=60000)
                if await announcement.is_visible():
                    await announcement.click()
                    await upload.or_(add).first.wait_for(timeout=60000)
                if not await upload.is_visible():
                    await click_upload_control(page, add)
            except Exception as exc:
                raise ValueError(f'The upload browser could not open this notebook ({await page.title()}). Sign in again.') from exc
            async with page.expect_file_chooser(timeout=90000) as chooser:
                await click_upload_control(page, upload)
            upload_started = True
            await (await chooser.value).set_files(str(file))
            logger.info('File selected for upload: %s', file.name)
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                matches = [s for s in await client.sources.list(notebook_id)
                           if s.id not in before and s.title == file.name]
                if len(matches) > 1:
                    raise ValueError('Multiple new sources appeared. Review the notebook before retrying.')
                if matches:
                    logger.info('Source registered: %s (%s)', file.name, matches[0].id)
                    try:
                        return await client.sources.wait_until_ready(notebook_id, matches[0].id, timeout=1200)
                    except Exception as exc:
                        exc.source_id = matches[0].id
                        raise
                await asyncio.sleep(1)
            raise ValueError('The upload response is uncertain. Check the notebook before retrying; the file will not be resent automatically.')
        except Exception as exc:
            exc.upload_started = upload_started
            if 'page' in locals():
                exc.add_note('Upload screen controls: ' + repr(await page.get_by_role('button').all_text_contents())[:1200])
                exc.add_note('Upload screen headings: ' + repr(await page.get_by_role('heading').all_text_contents())[:500])
            raise
        finally:
            await browser.close()


def configure_file_uploads(client):
    # Test adapters and the Android backend retain their own upload implementation.
    if getattr(getattr(client, 'sources', None), '_uploader', None) is None:
        return

    async def add_file(notebook_id, file_path, mime_type=None, *, wait=False, wait_timeout=1200, **kwargs):
        source = await upload_in_browser(client, notebook_id, file_path)
        if wait:
            return await client.sources.wait_until_ready(notebook_id, source.id, timeout=wait_timeout)
        return source

    client.sources.add_file = add_file
