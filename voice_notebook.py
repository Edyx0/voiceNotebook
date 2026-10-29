"""Local Voice Memos → weekly NotebookLM notebooks. Originals are read only."""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from timetable import recognize_photo
from class_photos import ClassPhotos
from access import Access
from overview import weekly_overview
from recording_library import RecordingLibrary, audio_range
from notebook_uploads import configure_file_uploads

ROOT = Path(__file__).resolve().parent
if getattr(sys, "frozen", False):
    os.environ["PATH"] = str(ROOT / "bin") + os.pathsep + os.environ.get("PATH", "/usr/bin:/bin")
HOME = Path(os.environ.get("VOICE_NOTEBOOK_HOME", Path.home() / "Library/Application Support/voiceNotebook"))
DEFAULT_MEMOS = Path.home() / "Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings"
AUDIO = {".m4a", ".qta", ".mp3", ".wav", ".aac", ".aiff", ".caf", ".mp4"}
MAX_BYTES = 190_000_000  # Decimal MB, with room below Google's 200 MB ceiling.
BITRATE = 96_000
MEDIA_PROCESSES = set()


def run_media(command, timeout):
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    MEDIA_PROCESSES.add(process)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise
    finally:
        MEDIA_PROCESSES.discard(process)


def defaults():
    return {"recordings_folder": str(DEFAULT_MEMOS), "timezone": "Europe/Istanbul",
            "week_one": "", "semester_weeks": 16, "tolerance_minutes": 10,
            "notebook_prefix": "", "auto_sync": False, "lectures": [], "onboarding_complete": False}


def validate_config(value):
    cfg = {**defaults(), **value}
    ZoneInfo(cfg["timezone"])
    if cfg["week_one"]:
        date.fromisoformat(cfg["week_one"])
    for key, low, high in [("semester_weeks", 1, 60), ("tolerance_minutes", 0, 60)]:
        if type(cfg[key]) is not int or not low <= cfg[key] <= high:
            raise ValueError(f"{key} must be between {low} and {high}.")
    if not isinstance(cfg["auto_sync"], bool):
        raise ValueError("Auto sync must be true or false.")
    if not isinstance(cfg["onboarding_complete"], bool):
        raise ValueError("Onboarding completion must be true or false.")
    if not isinstance(cfg["recordings_folder"], str) or not cfg["recordings_folder"].strip():
        raise ValueError("Choose a recordings folder.")
    if not isinstance(cfg["notebook_prefix"], str) or len(cfg["notebook_prefix"]) > 80:
        raise ValueError("Notebook prefix must be at most 80 characters.")
    if not isinstance(cfg["lectures"], list):
        raise ValueError("Lectures must be a list.")
    for slot in cfg["lectures"]:
        if not isinstance(slot, dict) or not isinstance(slot.get("course"), str) or not re.fullmatch(r"[\w .-]{1,40}", slot["course"].strip()):
            raise ValueError("Each lecture needs a course code (letters, digits, spaces, dots or dashes).")
        if type(slot.get("day")) is not int or slot["day"] not in range(7):
            raise ValueError("Choose a weekday for each lecture.")
        for field in ("start", "end"):
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", slot.get(field, "")):
                raise ValueError("Lecture times must use HH:MM.")
        if slot["start"] >= slot["end"]:
            raise ValueError("A lecture must end after it starts, on the same day.")
        slot["course"] = slot["course"].strip().upper()
    return {k: cfg[k] for k in defaults()}


def match_recording(recorded_at, cfg):
    if not recorded_at:
        return None, "Recording date unavailable. Set it in Review."
    if not cfg["week_one"] or not cfg["lectures"]:
        return None, "Add week 1 and your timetable in Setup."
    local = datetime.fromisoformat(recorded_at).astimezone(ZoneInfo(cfg["timezone"]))
    week = (local.date() - date.fromisoformat(cfg["week_one"])).days // 7 + 1
    if not 1 <= week <= cfg["semester_weeks"]:
        return None, "Outside the configured semester."
    minute = local.hour * 60 + local.minute
    candidates, close = set(), set()
    for slot in cfg["lectures"]:
        if slot["day"] != local.weekday():
            continue
        start, end = [int(t[:2]) * 60 + int(t[3:]) for t in (slot["start"], slot["end"])]
        if start <= minute < end:
            candidates.add(slot["course"])
        elif start - cfg["tolerance_minutes"] <= minute < end:
            close.add(slot["course"])
    candidates = candidates or close
    if len(candidates) != 1:
        return None, "Overlapping lectures: choose a course in Review." if candidates else "No timetable match. Choose a course in Review."
    course = candidates.pop()
    return {"course": course, "week": week, "title": notebook_title(course, week, cfg)}, "Matched by recording start time."


def notebook_title(course, week, cfg):
    return f"{cfg['notebook_prefix']}{course} w{week}"


def probe(path):
    result = run_media(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], timeout=60)
    if result.returncode:
        raise ValueError("Could not read audio. The recording may still be downloading or damaged.")
    data = json.loads(result.stdout)
    duration = float(data.get("format", {}).get("duration", 0))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Recording has no readable duration.")
    tags = [data.get("format", {}).get("tags", {})] + [s.get("tags", {}) for s in data.get("streams", [])]
    for tag in tags:
        raw = tag.get("creation_time") or tag.get("com.apple.quicktime.creationdate")
        if raw:
            try:
                dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                if dt.tzinfo and dt.year >= 2000:
                    return duration, dt.isoformat(), "Audio creation metadata"
            except ValueError:
                pass
    return duration, None, None


def filename_date(path, tz):
    match = re.match(r"(\d{8})[-_](\d{6})", path.stem)
    if match:
        try:
            return datetime.strptime("".join(match.groups()), "%Y%m%d%H%M%S").replace(tzinfo=ZoneInfo(tz)).isoformat()
        except ValueError:
            pass
    return None


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def convert(path, folder, stem, duration, max_bytes=MAX_BYTES):
    """Constant bitrate + conservative duration, then verify every actual file size."""
    folder.mkdir(parents=True, exist_ok=True)
    segment_seconds = max(1, int((max_bytes - 32_000) * 8 / BITRATE * 0.98))
    count = math.ceil(duration / segment_seconds)
    files = []
    for part in range(count):
        output = folder / f"{stem}_part{part + 1:03d}.mp3"
        temp = output.with_suffix(".tmp.mp3")
        args = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(part * segment_seconds),
                "-i", str(path), "-t", str(min(segment_seconds, duration - part * segment_seconds)),
                "-map", "0:a:0", "-vn", "-map_metadata", "-1", "-ac", "1", "-ar", "44100",
                "-codec:a", "libmp3lame", "-b:a", "96k", str(temp)]
        result = run_media(args, timeout=7200)
        if result.returncode:
            temp.unlink(missing_ok=True)
            raise RuntimeError("Audio conversion failed: " + result.stderr[-500:])
        if not 0 < temp.stat().st_size < max_bytes:
            temp.unlink(missing_ok=True)
            raise RuntimeError("Converted part exceeded the size limit; upload stopped.")
        temp.replace(output)
        files.append(output)
    return files


class App:
    def __init__(self, home=HOME):
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db_path = self.home / "state.sqlite3"
        self.lock = threading.Lock()
        self.guard = threading.RLock()
        self.job = {"busy": False, "message": "Ready", "error": None}
        self.auth = {"status": "idle", "message": "Sign in to connect NotebookLM."}
        self.auth_process = None
        self.auth_before_login = None
        with self.db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS recordings (
                id TEXT PRIMARY KEY, path TEXT NOT NULL, name TEXT NOT NULL,
                recorded_at TEXT, date_source TEXT, duration REAL, size INTEGER, mtime_ns INTEGER,
                status TEXT NOT NULL DEFAULT 'review', route TEXT, reason TEXT,
                manual INTEGER NOT NULL DEFAULT 0, notebook_id TEXT, error TEXT);
            CREATE TABLE IF NOT EXISTS parts (
                recording_id TEXT, name TEXT, source_id TEXT, status TEXT,
                PRIMARY KEY(recording_id, name));
            CREATE TABLE IF NOT EXISTS notebooks (key TEXT PRIMARY KEY, id TEXT, title TEXT);
            """)
            columns = {r[1] for r in db.execute("PRAGMA table_info(recordings)")}
            if "mtime_ns" not in columns:
                db.execute("ALTER TABLE recordings ADD COLUMN mtime_ns INTEGER")
        self.config = self.load_config()
        self.library = RecordingLibrary(self, run_media)
        self.photos = ClassPhotos(self)
        self.access = Access()
        self.upload_batch = {"recording_ids": [], "photo_ids": [], "stage": "idle", "photo_error": None}
        # A terminated process must never cause an uncertain upload to be sent again.
        with self.db() as db:
            db.execute("UPDATE recordings SET status='error', error='Previous run interrupted. Retry to reconcile saved progress.' WHERE status IN ('converting','uploading')")

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def load_config(self):
        path = self.home / "config.json"
        return validate_config(json.loads(path.read_text())) if path.exists() else defaults()

    def save_config(self, cfg):
        with self.guard:
            if self.job["busy"]:
                raise ValueError("Wait for the current operation before changing setup.")
            cfg = validate_config(cfg)
            temp = self.home / "config.tmp"
            temp.write_text(json.dumps(cfg, indent=2))
            temp.replace(self.home / "config.json")
            self.config = cfg
            with self.db() as db:
                rows = db.execute("SELECT * FROM recordings WHERE manual=0 AND notebook_id IS NULL AND status IN ('ready','review') AND NOT EXISTS (SELECT 1 FROM parts WHERE recording_id=recordings.id)").fetchall()
                for row in rows:
                    recorded_at = row["recorded_at"]
                    if row["date_source"] == "Voice Memos filename (configured timezone)":
                        recorded_at = filename_date(Path(row["name"]), cfg["timezone"])
                    route, reason = match_recording(recorded_at, cfg)
                    db.execute("UPDATE recordings SET recorded_at=?, route=?, reason=?, status=? WHERE id=?",
                               (recorded_at, json.dumps(route) if route else None, reason, "ready" if route else "review", row["id"]))

    def update(self, rid, **values):
        with self.db() as db:
            db.execute("UPDATE recordings SET " + ",".join(k + "=?" for k in values) + " WHERE id=?", [*values.values(), rid])

    def records(self):
        with self.db() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM recordings ORDER BY recorded_at DESC, name")]
            for row in rows:
                row["route"] = json.loads(row["route"]) if row["route"] else None
                row["parts"] = [dict(p) for p in db.execute("SELECT name, source_id, status FROM parts WHERE recording_id=? ORDER BY name", (row["id"],))]
        return self.library.annotate(rows)

    def start(self, kind, include_photos=False, photo_ids=None, recording_ids=None):
        with self.guard:
            if self.job["busy"]:
                raise ValueError("An operation is already running.")
            if kind == "sync" and self.auth["status"] in ("signing_in", "checking"):
                raise ValueError("Wait for the NotebookLM connection operation to finish.")
            if type(include_photos) is not bool:
                raise ValueError("Invalid photo option.")
            if include_photos and not self.access.read(self.config['recordings_folder'])['photos_enabled']:
                raise ValueError("Photos access is optional. Enable it first or upload audio only.")
            if photo_ids is not None and (not isinstance(photo_ids,list) or len(photo_ids)>500 or not all(isinstance(p,str) for p in photo_ids)):
                raise ValueError("Invalid photo selection.")
            if recording_ids is not None and (not isinstance(recording_ids,list) or len(recording_ids)>500 or not all(isinstance(r,str) for r in recording_ids)):
                raise ValueError("Invalid recording selection.")
            selected_ids = set(recording_ids) if recording_ids is not None else None
            message = {"photos-scan": "Finding class photos…", "photos-sync": "Uploading approved class photos…"}.get(kind, "Scanning recordings…")
            self.job = {"busy": True, "message": message, "error": None}
            if kind=='sync':self.upload_batch={"recording_ids":[],"photo_ids":[],"stage":"scanning","photo_error":None}
        def run():
            try:
                if kind in ("photos-scan", "photos-sync"):
                    if kind == "photos-scan":
                        self.photos.scan(recording_ids)
                    else:
                        asyncio.run(self.photos.sync(photo_ids))
                        self.upload_batch['stage']='complete'
                        self.job["message"] = "Photo uploads finished. Check the photo queue for results."
                    return
                self.scan()
                if kind == "sync":
                    recording_ids=[r['id'] for r in self.records() if r['status']=='ready' and r['route'] and (selected_ids is None or r['id'] in selected_ids)]
                    self.upload_batch={"recording_ids":recording_ids,"photo_ids":[],"stage":"audio","photo_error":None}
                    asyncio.run(self.sync(recording_ids))
                    self.upload_batch['stage']='complete'
                    if include_photos:
                        try:
                            self.photos.scan(recording_ids)
                            self.upload_batch['photo_ids']=[p['id'] for p in self.photos.records() if any(rid in recording_ids for rid in p['recording_ids'])]
                            self.upload_batch['stage']='photo_review'
                        except Exception as exc:
                            self.upload_batch['photo_error']=str(exc)
                self.job["message"] = "Finished. Review the recording queue below."
            except Exception as exc:
                self.job["error"] = str(exc)
                self.job["message"] = "Action needed"
            finally:
                self.job["busy"] = False
        threading.Thread(target=run, daemon=True).start()

    def scan(self):
        if not shutil.which("ffprobe"):
            raise ValueError("Install FFmpeg first: brew install ffmpeg")
        folder = Path(self.config["recordings_folder"]).expanduser()
        try:
            # pathlib.rglob suppresses some permission errors; check the root explicitly.
            list(folder.iterdir())
            paths = sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in AUDIO)
            if not folder.is_dir():
                raise ValueError("Recordings folder does not exist. Choose a folder in Setup.")
        except FileNotFoundError:
            raise ValueError("Recordings folder does not exist. Choose a folder in Setup.") from None
        except PermissionError:
            raise ValueError("macOS blocked Voice Memos access. Give the app running this tool Full Disk Access in System Settings → Privacy & Security, then restart it. Or export recordings to a folder and select that folder in Setup.") from None
        errors = []
        for path in paths:
            try:
                before = path.stat()
                if time.time() - before.st_mtime < 120 or before.st_size == 0:
                    continue  # Avoid recordings still being written or downloaded.
                with self.db() as db:
                    known = db.execute("SELECT id, size, mtime_ns FROM recordings WHERE path=?", (str(path),)).fetchone()
                if known and known["size"] == before.st_size and known["mtime_ns"] == before.st_mtime_ns:
                    continue
                duration, recorded_at, source = probe(path)
                if not recorded_at:
                    recorded_at = filename_date(path, self.config["timezone"])
                    source = "Voice Memos filename (configured timezone)" if recorded_at else "Date needs review"
                rid = fingerprint(path)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    continue
                route, reason = match_recording(recorded_at, self.config)
                with self.db() as db:
                    db.execute("INSERT OR IGNORE INTO recordings(id,path,name,recorded_at,date_source,duration,size,mtime_ns,status,route,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                               (rid, str(path), path.name, recorded_at, source, duration, before.st_size, before.st_mtime_ns, "ready" if route else "review", json.dumps(route) if route else None, reason))
                    db.execute("UPDATE recordings SET path=?, mtime_ns=? WHERE id=?", (str(path), before.st_mtime_ns, rid))
            except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
                errors.append(f"{path.name}: {exc}")
        if errors:
            raise ValueError("Some recordings could not be read. " + " | ".join(errors[:5]))

    def review(self, rid, value):
        with self.guard:
            if self.job["busy"]:
                raise ValueError("Wait for the current operation before reviewing.")
            with self.db() as db:
                row = db.execute("SELECT * FROM recordings WHERE id=?", (rid,)).fetchone()
                parts = db.execute("SELECT 1 FROM parts WHERE recording_id=? LIMIT 1", (rid,)).fetchone()
            if not row:
                raise ValueError("Recording not found.")
            if value.get("action") == "retry":
                if row["status"] != "error":
                    raise ValueError("Only failed recordings can be retried.")
                self.update(rid, status="ready" if row["route"] else "review", error=None)
                return
            if row["status"] == "uploaded" or row["notebook_id"] or parts:
                raise ValueError("A recording with upload progress cannot be reassigned.")
            if value.get("action") == "ignore":
                self.update(rid, status="ignored")
                return
            course = value.get("course", "").strip().upper()
            week = int(value.get("week", 0))
            if not re.fullmatch(r"[\w .-]{1,40}", course) or not 1 <= week <= self.config["semester_weeks"]:
                raise ValueError("Enter a course code and valid semester week.")
            recorded_at = value.get("recorded_at") or row["recorded_at"]
            if not recorded_at:
                raise ValueError("Enter the recording date and time.")
            dt = datetime.fromisoformat(recorded_at)
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=ZoneInfo(self.config["timezone"]))
            route = {"course": course, "week": week, "title": notebook_title(course, week, self.config)}
            self.update(rid, recorded_at=dt.isoformat(), date_source="Manually reviewed", manual=1,
                        route=json.dumps(route), reason="Manually assigned", status="ready", error=None)

    async def sync(self, recording_ids=None):
        if not shutil.which("ffmpeg"):
            raise ValueError("Install FFmpeg first: brew install ffmpeg")
        from notebooklm import NotebookLMClient
        async with NotebookLMClient.from_storage() as client:
            configure_file_uploads(client)
            notebooks = await client.notebooks.list()
            self.library.cache_notebooks(notebooks)
            failures = 0
            for row in self.records():
                if row["status"] != "ready" or not row["route"]:
                    continue
                if recording_ids is not None and row["id"] not in recording_ids:
                    continue
                try:
                    await self.upload_one(client, notebooks, row)
                except Exception as exc:
                    self.update(row["id"], status="error", error=str(exc))
                    failures += 1
            if failures:
                self.job["error"] = f"{failures} recording upload(s) failed. Review the recording queue and retry."

    async def upload_one(self, client, notebooks, row):
        rid, route = row["id"], row["route"]
        self.job["message"] = f"Converting {row['name']} → {route['title']}"
        self.update(rid, status="converting", error=None)
        path = Path(row["path"])
        if fingerprint(path) != rid:
            raise ValueError("The original recording changed. Scan again before uploading.")
        local = datetime.fromisoformat(row["recorded_at"]).astimezone(ZoneInfo(self.config["timezone"]))
        stem = f"{re.sub(r'[^\w.-]', '_', route['course'])}_{local:%Y-%m-%d_%H-%M}_{rid[:12]}"
        files = await asyncio.to_thread(convert, path, self.home / "mp3" / rid, stem, row["duration"])
        key = self.config["week_one"] + "|" + route["title"]
        with self.db() as db:
            saved = db.execute("SELECT id FROM notebooks WHERE key=?", (key,)).fetchone()
        nb_id = row["notebook_id"] or (saved["id"] if saved else None)
        if not nb_id:
            matches = [nb for nb in notebooks if nb.title == route["title"]]
            if len(matches) > 1:
                raise ValueError("Multiple notebooks have this title. Rename the duplicates in NotebookLM, then Retry.")
            nb = matches[0] if matches else await client.notebooks.create(route["title"])
            nb_id = nb.id
            if not matches:
                notebooks.append(nb)
            with self.db() as db:
                db.execute("INSERT OR REPLACE INTO notebooks VALUES(?,?,?)", (key, nb_id, route["title"]))
        self.update(rid, notebook_id=nb_id, status="uploading")
        sources = await client.sources.list(nb_id)
        for part in files:
            with self.db() as db:
                progress = db.execute("SELECT * FROM parts WHERE recording_id=? AND name=?", (rid, part.name)).fetchone()
            if progress and progress["status"] == "done":
                continue
            existing = ([s for s in sources if s.id == progress['source_id']] if progress and progress['source_id']
                        else [s for s in sources if s.title == part.name])
            if len(existing) > 1:
                raise ValueError(f"Duplicate remote sources for {part.name}. Review them in NotebookLM before Retry.")
            failed_source = bool(existing and getattr(existing[0], 'is_error', False))
            if existing and not failed_source:
                source = existing[0]
            else:
                if progress and not failed_source:
                    raise ValueError(f"Upload outcome uncertain for {part.name}. Check NotebookLM before retrying; the tool will not resend it automatically.")
                # Persist intent BEFORE the network call. Lost responses are never blindly retried.
                with self.db() as db:
                    db.execute("INSERT OR REPLACE INTO parts VALUES(?,?,NULL,'pending')", (rid, part.name))
                self.job["message"] = f"Uploading {part.name} → {route['title']}"
                try:
                    source = await client.sources.add_file(nb_id, part, wait=False)
                except Exception as exc:
                    if getattr(exc, "source_id", None):
                        with self.db() as db:
                            db.execute("UPDATE parts SET source_id=? WHERE recording_id=? AND name=?", (exc.source_id, rid, part.name))
                    elif getattr(exc, 'upload_started', None) is False:
                        with self.db() as db:
                            db.execute("DELETE FROM parts WHERE recording_id=? AND name=? AND source_id IS NULL AND status='pending'", (rid, part.name))
                    raise
            with self.db() as db:
                db.execute("INSERT OR REPLACE INTO parts VALUES(?,?,?,'processing')", (rid, part.name, source.id))
            await client.sources.wait_until_ready(nb_id, source.id, timeout=1200)
            with self.db() as db:
                db.execute("UPDATE parts SET status='done' WHERE recording_id=? AND name=?", (rid, part.name))
        self.update(rid, status="uploaded", error=None)

    def login(self, presentation="browser"):
        with self.guard:
            if self.job["busy"]:
                raise ValueError("Wait for the current operation before signing in.")
            if self.auth["status"] in ("signing_in", "checking"):
                raise ValueError("A connection operation is already running.")
            command = [sys.executable]
            if not getattr(sys, "frozen", False):
                command.append(str(ROOT / "voice_notebook.py"))
            command.append("--notebooklm-login")
            if presentation == "system":
                command.append("--system-popup")
            if presentation == "managed":
                command.append("--managed-popup")
            previous = dict(self.auth)
            self.auth = {"status": "signing_in", "message": "Choose your Google account in the sign-in window. This window will close when connected." if presentation == "managed" else "After signing in, close the popup to connect." if presentation == "system" else "Sign in in your browser, then choose Finish sign-in.", "presentation": presentation}
            try:
                self.auth_process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                                     stderr=subprocess.DEVNULL, start_new_session=True,
                                                     env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})
            except OSError:
                self.auth = previous
                raise ValueError("The sign-in window could not open. Try again.") from None
            self.auth_before_login = previous
            process = self.auth_process
        def wait_for_login():
            result = process.wait()
            if self.auth_process is not process:
                return
            self.auth_before_login = None
            if result:
                messages = {2: "Allow browser session access in macOS Settings, then try again.",
                            3: "Session import isn’t supported for your default browser.",
                            4: "Use a browser profile with one Google account, then try again.",
                            5: "Allow voiceNotebook to open a browser window, then try again.",
                            6: "Finish Google sign-in in the popup before connecting.",
                            7: "The sign-in browser is missing. Reinstall voiceNotebook.",
                            8: "Google sign-in did not complete. Try again."}
                self.auth = {"status": "error", "message": messages.get(result, "Sign-in didn’t finish. Try again.")}
            else:
                self.auth = {"status": "idle", "message": "Session saved."}
                if not self.job["busy"]:
                    self.check_connection()
        threading.Thread(target=wait_for_login, daemon=True).start()

    def finish_login(self, email=None):
        if email is not None and (not isinstance(email, str) or not re.fullmatch(r"[^\s@\t]+@[^\s@\t]+\.[^\s@\t]+", email) or len(email) > 254):
            raise ValueError("Choose a Google account.")
        with self.guard:
            if self.auth["status"] != "signing_in" or not self.auth_process or self.auth_process.poll() is not None:
                raise ValueError("Start Google sign-in first.")
            try:
                self.auth_process.stdin.write(("finish" + ("\t" + email if email else "") + "\n").encode())
                self.auth_process.stdin.close()
            except (BrokenPipeError, OSError):
                raise ValueError("Sign-in closed. Try again.")
            self.auth = {"status": "checking", "message": "Connecting…"}

    def cancel_login(self):
        import signal
        with self.guard:
            process, self.auth_process = self.auth_process, None
            if process and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            previous, self.auth_before_login = self.auth_before_login, None
            self.auth = previous if previous and previous.get("status") == "connected" else {"status": "idle", "message": "Not connected."}

    def check_connection(self):
        with self.guard:
            if self.auth["status"] == "checking":
                raise ValueError("Already checking the connection.")
            if self.auth["status"] == "signing_in" and self.auth_process and self.auth_process.poll() is None:
                raise ValueError("Finish signing in first.")
            if self.job["busy"]:
                raise ValueError("Wait for the current operation before checking the connection.")
            self.auth = {"status": "checking", "message": "Checking your NotebookLM session…"}
        def check():
            async def connect():
                from notebooklm import NotebookLMClient
                async with NotebookLMClient.from_storage() as client:
                    notebooks = await client.notebooks.list()
                    self.library.cache_notebooks(notebooks)
                    return len(notebooks)
            try:
                count = asyncio.run(connect())
                self.auth = {"status": "connected", "message": f"Connected · {count} notebooks available", "checked_at": datetime.now(timezone.utc).isoformat()}
            except Exception:
                self.auth = {"status": "error", "message": "Could not connect. Check your internet connection or sign in again."}
        threading.Thread(target=check, daemon=True).start()

    def status(self):
        try:
            from notebooklm.paths import get_storage_path
            login_saved = get_storage_path().exists()
        except ImportError:
            login_saved = False
        records=self.records()
        permissions=self.access.read(self.config['recordings_folder'])
        return {"config": self.config, "recordings": records, "job": dict(self.job),
                "overview":weekly_overview(records,self.config),"permissions":permissions,"upload_batch":dict(self.upload_batch),
                "photos": self.photos.records(), "photos_available": permissions['photos_enabled'],
                "auth": dict(self.auth),
                "dependencies": {"ffmpeg": bool(shutil.which("ffmpeg")),
                                 "notebooklm": importlib.util.find_spec("notebooklm") is not None},
                "login_saved": login_saved,
                "data_folder": str(self.home)}

    def watch(self):
        while True:
            time.sleep(60)
            if self.config["auto_sync"] and not self.job["busy"] and not self.job["error"]:
                try:
                    self.start("sync")
                except ValueError:
                    pass  # A manual operation may have started between the check and lock.

    def close(self):
        import signal
        for process in list(MEDIA_PROCESSES):
            if process.poll() is None:
                process.terminate()
        if self.auth_process and self.auth_process.poll() is None:
            try:
                os.killpg(self.auth_process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass


def serve(app, port, open_browser=False, ready_file=None):
    token = secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, data, mime="application/json"):
            payload = json.dumps(data).encode() if mime == "application/json" else data
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def valid_host(self):
            return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}

        def do_GET(self):
            if not self.valid_host():
                return self.reply(403, {"error": "Invalid host"})
            path = urlparse(self.path).path
            if path == "/api/state":
                return self.reply(200, {**app.status(), "token": token})
            if path.startswith("/api/recordings/audio/"):
                from urllib.parse import parse_qs
                supplied = parse_qs(urlparse(self.path).query).get("token", [""])[0]
                if not secrets.compare_digest(supplied, token):
                    return self.reply(403, {"error": "Reload and try again."})
                rid = path.rsplit("/", 1)[1]
                if not re.fullmatch(r"[a-f0-9]{64}", rid):
                    return self.reply(404, {"error": "Recording not found."})
                try:
                    audio = app.library.preview(rid)
                    size = audio.stat().st_size
                except ValueError as error:
                    return self.reply(400, {"error": str(error)})
                except (OSError, subprocess.TimeoutExpired):
                    return self.reply(400, {"error": "Could not open this recording."})
                try:
                    start, end, partial = audio_range(self.headers.get("Range"), size)
                except ValueError:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(206 if partial else 200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(end - start + 1))
                self.send_header("Cache-Control", "private, no-store")
                if partial:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.end_headers()
                try:
                    with audio.open("rb") as source:
                        source.seek(start)
                        remaining = end - start + 1
                        while remaining:
                            block = source.read(min(65536, remaining))
                            if not block:
                                break
                            self.wfile.write(block)
                            remaining -= len(block)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return
            if path.startswith("/api/photos/image/"):
                pid = path.rsplit("/", 1)[1]
                if not re.fullmatch(r"[a-f0-9]{64}", pid):
                    return self.reply(404, {"error": "Photo not found"})
                with app.db() as db:
                    found = db.execute("SELECT 1 FROM class_photos WHERE id=?", (pid,)).fetchone()
                image = app.photos.folder / f"{pid}.jpg"
                if found and image.is_file():
                    return self.reply(200, image.read_bytes(), "image/jpeg")
                return self.reply(404, {"error": "Photo unavailable. Scan again."})
            assets = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css"),
                      "/photos.js": ("photos.js", "text/javascript"), "/photos.css": ("photos.css", "text/css"), "/mac.css": ("mac.css", "text/css"),
                      "/calendar.js": ("calendar.js", "text/javascript"), "/calendar.css": ("calendar.css", "text/css"),
                      "/home.js": ("home.js", "text/javascript"), "/home.css": ("home.css", "text/css"),
                       "/studio.css": ("studio.css", "text/css"),
                      "/access.css": ("access.css", "text/css"), "/library.css": ("library.css", "text/css"),
                      "/onboarding.js": ("onboarding.js", "text/javascript"), "/onboarding.css": ("onboarding.css", "text/css")}
            if path in assets:
                name, mime = assets[path]
                return self.reply(200, (ROOT / "web" / name).read_bytes(), mime)
            self.reply(404, {"error": "Not found"})

        def do_POST(self):
            if not self.valid_host() or self.headers.get("X-App-Token") != token:
                return self.reply(403, {"error": "Reload the app and try again."})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                limit = 28_100_000 if self.path == "/api/timetable/photo" else 100_000
                if not 0 <= size <= limit:
                    raise ValueError("Request too large.")
                value = json.loads(self.rfile.read(size) or b"{}")
                if self.path == "/api/timetable/photo":
                    helper = ROOT / ("bin/timetable-ocr" if getattr(sys, "frozen", False) else "build/timetable-ocr")
                    return self.reply(200, recognize_photo(value.get("content"), helper))
                elif self.path == "/api/config":
                    app.save_config(value)
                elif self.path in ("/api/scan", "/api/sync"):
                    app.start(self.path.rsplit("/", 1)[1], include_photos=value.get('include_photos',False), recording_ids=value.get('recording_ids'))
                elif self.path == "/api/permissions/refresh":
                    app.access.read(app.config['recordings_folder'],force=True)
                elif self.path == "/api/photos/scan":
                    app.start("photos-scan",recording_ids=value.get('recording_ids'))
                elif self.path == "/api/photos/sync":
                    app.start("photos-sync",photo_ids=value.get('ids'))
                elif self.path == "/api/photos/review":
                    app.photos.review(value["id"], value["action"], value.get("notebook_id"))
                elif self.path == "/api/review":
                    app.review(value["id"], value)
                elif self.path == "/api/recordings/rename":
                    app.library.rename(value["id"], value.get("name"))
                elif self.path == "/api/login":
                    app.login(value.get("presentation", "browser"))
                elif self.path == "/api/login/accounts":
                    if app.auth["status"] != "signing_in":
                        raise ValueError("Start Google sign-in first.")
                    from browser_signin import available_accounts
                    return self.reply(200, {"accounts": available_accounts()})
                elif self.path == "/api/login/complete":
                    app.finish_login(value.get("email"))
                elif self.path == "/api/login/cancel":
                    app.cancel_login()
                elif self.path == "/api/connection":
                    app.check_connection()
                else:
                    return self.reply(404, {"error": "Not found"})
                self.reply(200, {"ok": True})
            except (ValueError, KeyError, TypeError) as exc:
                self.reply(400, {"error": str(exc)})
            except Exception as exc:
                self.reply(500, {"error": str(exc)})
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    port = server.server_address[1]
    try:
        from notebooklm.paths import get_storage_path
        if get_storage_path().exists():
            app.check_connection()
    except ImportError:
        pass
    threading.Thread(target=app.watch, daemon=True).start()
    print(f"voiceNotebook is ready at http://127.0.0.1:{port}", flush=True)
    if ready_file:
        path = Path(ready_file)
        path.write_text(json.dumps({"url": f"http://127.0.0.1:{port}"}))
    if open_browser:
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    import fcntl
    if "--notebooklm-login" in sys.argv:
        if "--help" in sys.argv:
            print("Google login in your default browser.")
            raise SystemExit(0)
        if "--managed-popup" in sys.argv:
            import signal
            def cancel_capture(signum, frame):
                raise SystemExit(1)
            signal.signal(signal.SIGTERM, cancel_capture)
            from managed_signin import sign_in
            raise SystemExit(sign_in())
        from browser_signin import sign_in
        system_popup = "--system-popup" in sys.argv
        raise SystemExit(sign_in(timeout=900 if system_popup else 300, system_popup=system_popup))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="Open the app in your browser")
    parser.add_argument("--ready-file", help=argparse.SUPPRESS)
    args = parser.parse_args()
    HOME.mkdir(parents=True, exist_ok=True, mode=0o700)
    process_lock = (HOME / "process.lock").open("w")
    try:
        fcntl.flock(process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("voiceNotebook is already running. Open http://127.0.0.1:8765")
    app = App()
    import signal
    def stop(signum, frame):
        app.close()
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    serve(app, args.port, args.open, args.ready_file)
