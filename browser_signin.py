"""Sign in through the macOS default browser, then import its Google session."""
import subprocess
import sys
import select
import json
import time
import asyncio
import tempfile
import os
import traceback
from pathlib import Path
from urllib.parse import parse_qs, urlparse


LOGIN_URL = "https://accounts.google.com/AccountChooser?continue=https%3A%2F%2Fnotebooklm.google.com%2F"
BROWSERS = {
    "com.apple.Safari": "safari",
    "com.google.Chrome": "chrome",
    "com.microsoft.edgemac": "edge",
    "com.brave.Browser": "brave",
    "company.thebrowser.Browser": "arc",
    "org.mozilla.firefox": "firefox",
    "com.vivaldi.Vivaldi": "vivaldi",
    "com.operasoftware.Opera": "opera",
    "app.zen-browser.zen": "zen",
}


def _diagnose(stage, error=None, output=''):
    details = {'stage': stage, 'error_type': type(error).__name__ if error else None,
        'frames': [f'{Path(frame.filename).name}:{frame.lineno}:{frame.name}'
            for frame in traceback.extract_tb(error.__traceback__)[-8:]] if error and error.__traceback__ else [],
        'flags': [word for word in ('permission', 'keychain', 'decrypt', 'module', 'profile', 'storage', 'cookie', 'account', 'invalid', 'failed', 'token', 'network') if word in output.lower()]}
    if isinstance(error, ModuleNotFoundError):
        details['module'] = error.name
    try:
        root = Path(os.environ.get('VOICE_NOTEBOOK_HOME', Path.home() / 'Library/Application Support/voiceNotebook'))
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = root / 'last-login-error.json'
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as file:
            json.dump(details, file)
    except OSError:
        pass


def default_browser():
    script = '''ObjC.import('AppKit');
    const url = $.NSURL.URLWithString('https://notebooklm.google.com');
    const app = $.NSWorkspace.sharedWorkspace.URLForApplicationToOpenURL(url);
    $.NSBundle.bundleWithURL(app).bundleIdentifier.js;'''
    result = subprocess.run(
        ["/usr/bin/osascript", "-l", "JavaScript", "-e", script],
        capture_output=True, text=True, check=True, timeout=10,
    )
    return BROWSERS.get(result.stdout.strip())


def import_session(browser, authuser=None, account_email=None):
    # CliRunner keeps SDK output (which may contain account information) private
    # and prevents an ambiguous multi-account selection from waiting on stdin.
    from click.testing import CliRunner
    from notebooklm.notebooklm_cli import cli
    arguments = ["login", "--browser-cookies", browser]
    if account_email:
        arguments.extend(["--account", account_email])
    if authuser is not None:
        # Match the popup's chosen account instead of silently using Google's default.
        from notebooklm.cli.services.login.browser_accounts import _enumerate_browser_accounts
        discovered = _enumerate_browser_accounts(browser, verbose=False)
        if not isinstance(discovered, tuple):
            message = str(getattr(discovered, "message", "")).lower()
            return 2 if any(word in message for word in ("permission", "access", "keychain", "decrypt")) else 1
        _, accounts = discovered
        account = next((account for account in accounts if account.authuser == authuser), None)
        if account is None:
            return 4
        arguments.extend(["--account", account.email])
    with tempfile.TemporaryDirectory(prefix='voiceNotebook-session-') as tmp:
        staged = Path(tmp) / 'session.json'
        result = CliRunner().invoke(cli, [arguments[0], '--storage', str(staged), *arguments[1:]], input='')
        if result.exit_code == 0:
            return 0 if save_verified_session(staged) else 1
    output = result.output.lower()
    _diagnose('import', result.exception, output)
    if any(word in output for word in ("permission denied", "operation not permitted", "full disk access", "keychain", "decrypt")):
        return 2
    if any(word in output for word in ("multiple accounts", "--account", "select an account", "choose an account")):
        return 4
    return 1


def save_verified_session(staged):
    """Never replace a working connection with an unverified browser session."""
    from notebooklm import NotebookLMClient
    from notebooklm.auth import read_account_metadata, replace_profile_from_login
    from notebooklm.paths import get_storage_path

    async def verify():
        async with NotebookLMClient.from_storage(str(staged)) as client:
            await client.notebooks.list()
    try:
        asyncio.run(verify())
        account = read_account_metadata(staged)
        outcome = replace_profile_from_login(get_storage_path(), json.loads(staged.read_text()),
            include_domains=None, account_mode='set', account_authuser=int(account.get('authuser', 0)),
            account_email=account.get('email'))
        return outcome.ok
    except Exception as error:
        _diagnose('verify', error)
        return False


def open_sign_in(browser):
    """Create a new window instead of following the browser's tab preference."""
    bundle_id = next((key for key, value in BROWSERS.items() if value == browser), None)
    if not bundle_id:
        raise ValueError("Unsupported default browser")
    app = f"Application({json.dumps(bundle_id)})"
    url = json.dumps(LOGIN_URL)
    if browser == "safari":
        script = f"const browser = {app}; const before = browser.windows().map(w => w.id()); browser.make({{new: 'document', withProperties: {{url: {url}}}}}); const window = browser.windows().find(w => !before.includes(w.id())); if (!window) throw Error('No separate browser window'); window.bounds = {{x: 180, y: 100, width: 560, height: 720}}; browser.activate(); JSON.stringify({{id: String(window.id()), tabs: window.tabs().length}});"
    elif browser in {"chrome", "edge", "brave", "vivaldi", "opera"}:
        script = f"const browser = {app}; const window = browser.Window(); browser.windows.push(window); window.bounds = {{x: 180, y: 100, width: 560, height: 720}}; window.activeTab.url = {url}; browser.activate(); JSON.stringify({{id: String(window.id()), tabs: window.tabs().length}});"
    elif browser in {"firefox", "zen"}:
        script = f"ObjC.import('AppKit'); const app = $.NSWorkspace.sharedWorkspace.URLForApplicationWithBundleIdentifier({json.dumps(bundle_id)}); $.NSBundle.bundleWithURL(app).executablePath.js;"
        result = subprocess.run(["/usr/bin/osascript", "-l", "JavaScript", "-e", script],
                                capture_output=True, text=True, check=True, timeout=10)
        subprocess.Popen([result.stdout.strip(), "--new-window", LOGIN_URL],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return
    else:
        raise ValueError("Unsupported default browser window API")
    result = subprocess.run(["/usr/bin/osascript", "-l", "JavaScript", "-e", script],
                            capture_output=True, text=True, check=True, timeout=30)
    window = json.loads(result.stdout)
    return window['id'], int(window['tabs'])


def popup_account(browser, window_id):
    """Read only our sign-in window's URL; never inspect another browser window."""
    bundle_id = next(key for key, value in BROWSERS.items() if value == browser)
    tab = "currentTab" if browser == "safari" else "activeTab"
    script = f"const browser = Application({json.dumps(bundle_id)}); const window = browser.windows().find(w => String(w.id()) === {json.dumps(window_id)}); if (!window) throw Error('Sign-in window closed'); window.{tab}.url();"
    result = subprocess.run(["/usr/bin/osascript", "-l", "JavaScript", "-e", script],
                            capture_output=True, text=True, check=True, timeout=10)
    url = urlparse(result.stdout.strip())
    if url.scheme != "https" or url.hostname not in {"notebooklm.google.com", "notebook.google.com"}:
        raise ValueError("Google sign-in is not finished")
    path_parts = url.path.strip('/').split('/')
    path_account = path_parts[1] if len(path_parts) > 1 and path_parts[0] == 'u' else '0'
    account = parse_qs(url.query).get("authuser", [path_account])[0]
    if not account.isdecimal():
        raise ValueError("Unknown Google account")
    return int(account)


def close_sign_in(browser, window_id, initial_tabs=1):
    """Close only our window when the user has not added any tabs."""
    if not window_id or browser not in {'safari', 'chrome', 'edge', 'brave', 'vivaldi', 'opera'}:
        return
    bundle_id = next(key for key, value in BROWSERS.items() if value == browser)
    tab = 'currentTab' if browser == 'safari' else 'activeTab'
    script = f"const browser = Application({json.dumps(bundle_id)}); const window = browser.windows().find(w => String(w.id()) === {json.dumps(window_id)}); if (window && window.tabs().length <= {int(initial_tabs)} && /^https:\\/\\/(accounts\\.google\\.com|notebooklm\\.google\\.com|notebook\\.google\\.com)\\//.test(window.{tab}.url())) window.close();"
    try:
        subprocess.run(['/usr/bin/osascript', '-l', 'JavaScript', '-e', script],
            capture_output=True, text=True, check=True, timeout=10)
    except (subprocess.SubprocessError, OSError):
        pass


def available_accounts():
    from notebooklm.cli.services.login.browser_accounts import _enumerate_browser_accounts
    browser = default_browser()
    if browser is None:
        raise ValueError("Session import isn’t supported for your default browser.")
    discovered = _enumerate_browser_accounts(browser, verbose=False)
    if not isinstance(discovered, tuple):
        message = str(getattr(discovered, "message", "")).lower()
        if "permission" in message or "operation not permitted" in message:
            raise ValueError("Enable voiceNotebook in System Settings → Privacy & Security → Full Disk Access, then restart the app to read your Safari session.")
        if "keychain" in message or "decrypt" in message:
            raise ValueError("Allow browser Keychain access when macOS asks, then try again.")
        raise ValueError("Could not read your Google session. Finish signing in, then try again.")
    return [account.email for account in discovered[1]]


def sign_in(timeout=300, system_popup=False):
    browser = default_browser()
    if browser is None:
        return 3
    window_id, initial_tabs = None, 1
    if not system_popup:
        try:
            window = open_sign_in(browser)
            if window:
                window_id, initial_tabs = window
        except ValueError:
            return 3
        except (subprocess.SubprocessError, OSError):
            return 5
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            readable, _, _ = select.select([sys.stdin], [], [], min(1, max(0, deadline - time.monotonic())))
            if readable:
                command = sys.stdin.readline().strip()
                if not command or command.split('\t', 1)[0] != 'finish':
                    return 1
                email = command.partition('\t')[2]
                if email:
                    return import_session(browser, account_email=email)
                if system_popup:
                    return 4
            elif system_popup or not window_id:
                continue
            if window_id and browser in {'safari', 'chrome', 'edge', 'brave', 'vivaldi', 'opera'}:
                try:
                    account = popup_account(browser, window_id)
                except ValueError:
                    # Google has not returned to NotebookLM in our window yet.
                    if readable:
                        return 6
                    continue
                except (subprocess.SubprocessError, OSError):
                    return 6
                return import_session(browser, account)
            if readable:
                return import_session(browser)
        return 1
    finally:
        close_sign_in(browser, window_id, initial_tabs)
