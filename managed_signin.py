"""Capture only the account selected in voiceNotebook's own login window."""
import asyncio
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import sqlite3
import subprocess
import time
from urllib.parse import parse_qs, urlparse


LOGIN_URL = "https://accounts.google.com/AccountChooser?continue=https%3A%2F%2Fnotebook.google.com%2F"


def interactive_login(executable, profile, timeout):
    # Sign-in runs in ordinary Chrome, with no automation connection attached.
    # Only this new, private profile is watched; no Safari/other-account jars.
    process = subprocess.Popen([
        # App-mode windows cannot present macOS iCloud Keychain authentication.
        executable, f"--user-data-dir={profile}", "--new-window", LOGIN_URL,
        "--window-size=540,720", "--no-first-run", "--no-default-browser-check",
        "--disable-save-password-bubble",
    ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise ValueError("Sign-in window closed")
            if profile_signed_in(profile):
                return
            time.sleep(.5)
        raise TimeoutError("Google sign-in timed out")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def profile_signed_in(profile):
    for cookies in (profile / "Default" / "Cookies", profile / "Default" / "Network" / "Cookies"):
        if not cookies.is_file():
            continue
        try:
            with closing(sqlite3.connect(cookies.as_uri() + "?mode=ro", uri=True, timeout=.2)) as db:
                names = {r[0] for r in db.execute("SELECT name FROM cookies WHERE host_key IN ('.google.com','accounts.google.com') AND name IN ('SID','__Secure-1PSID') AND (length(value)>0 OR length(encrypted_value)>0)")}
            if names == {"SID", "__Secure-1PSID"}:
                return True
        except sqlite3.Error:
            pass
    return False


def capture(timeout=900):
    from playwright.sync_api import sync_playwright
    from notebooklm import NotebookLMClient
    from notebooklm.auth import replace_profile_from_login
    from notebooklm.paths import get_storage_path
    from notebooklm._browser.browser_capture import wait_for_login_landing, heal_captured_state
    from notebooklm._browser.browser_capture import filter_storage_state_cookies_by_domain_policy

    with tempfile.TemporaryDirectory(prefix="voiceNotebook-login-") as temporary:
        root = Path(temporary)
        with sync_playwright() as playwright:
            options = dict(
                user_data_dir=str(root / "browser"), headless=True,
                ignore_default_args=["--enable-automation"],
            )
            if getattr(sys, "frozen", False):
                browser_root = Path(sys.executable).parents[1] / "browser"
                executables = sorted(
                    (p for p in browser_root.glob("**/*.app/Contents/MacOS/*") if p.is_file()),
                    key=lambda p: len(p.parts),
                )
                if not executables:
                    return 7
                options["executable_path"] = str(executables[0])
            for installed in (Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'), Path.home() / 'Applications/Google Chrome.app/Contents/MacOS/Google Chrome'):
                if installed.is_file():
                    options["executable_path"] = str(installed)
                    break
            executable = options.get("executable_path", playwright.chromium.executable_path)
            interactive_login(executable, root / "browser", timeout)
            context = playwright.chromium.launch_persistent_context(**options)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto("https://notebook.google.com/", wait_until="commit")
                wait_for_login_landing(page, timeout_s=60, context=context)
                selected = urlparse(page.url)
                authuser = parse_qs(selected.query).get("authuser", ["0"])[0]
                if not authuser.isdecimal():
                    raise ValueError("Unknown Google account")
                state = filter_storage_state_cookies_by_domain_policy(context.storage_state(), include_domains=None)
                state, _ = heal_captured_state(state)
                # Verify a staged session before replacing a working connection.
                staged = root / "session.json"
                outcome = replace_profile_from_login(staged, state, include_domains=None, account_mode="set", account_authuser=int(authuser))
                if outcome.lock_unavailable:
                    raise RuntimeError("Session is busy")

                async def verify():
                    async with NotebookLMClient.from_storage(str(staged)) as client:
                        await client.notebooks.list()

                # Playwright's synchronous API already owns an asyncio loop.
                with ThreadPoolExecutor(max_workers=1) as verification:
                    verification.submit(lambda: asyncio.run(verify())).result(timeout=90)
                outcome = replace_profile_from_login(get_storage_path(), state, include_domains=None, account_mode="set", account_authuser=int(authuser))
                if outcome.lock_unavailable:
                    raise RuntimeError("Session is busy")
                return 0
            finally:
                context.close()


def sign_in(timeout=900):
    try:
        return capture(timeout)
    except Exception:
        return 8
