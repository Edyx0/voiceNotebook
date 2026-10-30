"""Local review queue for Apple Photos. Only approved images can leave the Mac."""
import asyncio
import base64
import binascii
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import secrets
from zoneinfo import ZoneInfo
from notebook_uploads import configure_file_uploads


def class_windows(recordings, config):
    windows = []
    tz = ZoneInfo(config["timezone"])
    for row in recordings:
        if row["status"] != "uploaded" or not row["notebook_id"] or not row["route"] or not row["recorded_at"]:
            continue
        start = datetime.fromisoformat(row["recorded_at"]).astimezone(tz)
        end = start + timedelta(seconds=row["duration"])
        for slot in config["lectures"]:
            if slot["course"] != row["route"]["course"] or slot["day"] != start.weekday():
                continue
            lower = start.replace(hour=int(slot["start"][:2]), minute=int(slot["start"][3:]), second=0, microsecond=0)
            upper = start.replace(hour=int(slot["end"][:2]), minute=int(slot["end"][3:]), second=0, microsecond=0)
            if lower - timedelta(minutes=config["tolerance_minutes"]) <= start < upper:
                start, end = min(start, lower), max(end, upper)
                break
        windows.append({"start": start.timestamp(), "end": end.timestamp(),
                        "recording_id": row["id"], "notebook_id": row["notebook_id"],
                        "title": row["route"]["title"]})
    return windows


class ClassPhotos:
    def __init__(self, app):
        self.app = app
        self.folder = app.home / "class-photos"
        self.folder.mkdir(exist_ok=True, mode=0o700)
        with app.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS class_photos (
                id TEXT PRIMARY KEY, captured_at TEXT NOT NULL, label TEXT NOT NULL,
                destinations TEXT NOT NULL, notebook_id TEXT, title TEXT,
                status TEXT NOT NULL DEFAULT 'review', digest TEXT NOT NULL,
                source_id TEXT, attempted INTEGER NOT NULL DEFAULT 0, error TEXT)""")
            db.execute("UPDATE class_photos SET status='error', error='Previous upload interrupted. Retry to check saved progress.' WHERE status='uploading'")

    def records(self):
        with self.app.db() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM class_photos ORDER BY captured_at DESC, id")]
        windows=class_windows(self.app.records(),self.app.config)
        for row in rows:
            row["destinations"] = json.loads(row["destinations"])
            captured=datetime.fromisoformat(row['captured_at']).timestamp()
            row['recording_ids']=[w['recording_id'] for w in windows if w['start']<=captured<w['end'] and any(d['notebook_id']==w['notebook_id'] for d in row['destinations'])]
        return rows

    def add_selected(self, content, notebook_id):
        """Store an explicitly selected image for the approved upload queue."""
        with self.app.guard:
            if self.app.job['busy']:
                raise ValueError('Wait for the current operation before adding photos.')
            with self.app.db() as db:
                notebook = db.execute('SELECT title FROM notebook_catalog WHERE id=?', (notebook_id,)).fetchone()
                if not notebook:
                    raise ValueError('Choose an available notebook. Check the connection to refresh the list.')
                if not isinstance(content, str) or not content.startswith('data:image/jpeg;base64,'):
                    raise ValueError('Could not read this photo. Choose it again.')
                try:
                    data = base64.b64decode(content.split(',', 1)[1], validate=True)
                except (ValueError, binascii.Error):
                    raise ValueError('Could not read this photo. Choose it again.') from None
                if not data.startswith(b'\xff\xd8\xff') or len(data) > 20_000_000:
                    raise ValueError('Photo must be a JPEG under 20 MB.')
                pid = secrets.token_hex(32)
                path = self.folder / f'{pid}.jpg'
                path.write_bytes(data)
                title = notebook['title'].strip() or 'Untitled notebook'
                choice = {'notebook_id': notebook_id, 'title': title}
                try:
                    db.execute("INSERT INTO class_photos(id,captured_at,label,destinations,notebook_id,title,status,digest) VALUES(?,?,?,?,?,?,?,?)",
                               (pid, datetime.now(timezone.utc).isoformat(), 'Selected photo', json.dumps([choice]), notebook_id, title, 'approved', hashlib.sha256(data).hexdigest()))
                except Exception:
                    path.unlink(missing_ok=True)
                    raise
                return pid

    def scan(self, recording_ids=None):
        helper = os.environ.get("VOICE_NOTEBOOK_PHOTOS_HELPER")
        if not helper or not Path(helper).is_file():
            raise ValueError("Apple Photos scanning requires the voiceNotebook Mac app. Open the Mac app and choose Find class photos.")
        if not self.app.access.read(self.app.config['recordings_folder'])['photos_enabled']:
            raise ValueError("Photos access is off. Enable Photos from the home screen, or continue with audio only.")
        records=self.app.records()
        if recording_ids is not None:records=[r for r in records if r['id'] in recording_ids]
        windows = class_windows(records, self.app.config)
        if not windows:
            raise ValueError("Upload a class recording first. Photos will be matched to its existing NotebookLM notebook.")
        request = self.folder / "scan-request.json"
        response = self.folder / "scan-response.json"
        response.unlink(missing_ok=True)
        request.write_text(json.dumps({"windows": windows, "folder": str(self.folder)}))
        self.app.job["message"] = "Finding Apple Photos taken during uploaded classes…"
        result = subprocess.run([helper, "--scan-photos", str(request), str(response)],
                                capture_output=True, timeout=1800)
        if result.returncode or not response.exists():
            raise ValueError("Photos scan could not finish. Open Photos, check Photos access in System Settings, and try again.")
        data = json.loads(response.read_text())
        if data.get("error"):
            raise ValueError(data["error"])
        self.ingest(data.get("photos", []), windows)
        failures = data.get("unavailable", 0)
        self.app.job["message"] = f"Found {len(data.get('photos', []))} class photos. Review each image before approving upload."
        if failures:
            self.app.job["message"] += f" {failures} images unavailable; download originals in Photos and scan again."

    def ingest(self, photos, windows):
        """Derive destinations on the server; the scanner never decides approval."""
        for photo in photos:
            pid = photo["id"]
            if not isinstance(pid, str) or len(pid) != 64 or any(c not in "0123456789abcdef" for c in pid):
                raise ValueError("Invalid photo identifier.")
            captured = datetime.fromisoformat(photo["captured_at"])
            if captured.tzinfo is None:
                raise ValueError("Photo capture time needs a timezone.")
            choices = {w["notebook_id"]: {"notebook_id": w["notebook_id"], "title": w["title"]}
                       for w in windows if w["start"] <= captured.timestamp() < w["end"]}
            if not choices:
                continue
            path = self.folder / f"{pid}.jpg"
            if not path.is_file() or not 0 < path.stat().st_size < 20_000_000:
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.app.db() as db:
                old = db.execute("SELECT * FROM class_photos WHERE id=?", (pid,)).fetchone()
                if old:
                    # Once reviewed, retain the exact preview bytes and destination.
                    continue
                db.execute("INSERT INTO class_photos(id,captured_at,label,destinations,digest) VALUES(?,?,?,?,?)",
                           (pid, captured.isoformat(), photo.get("label", "In-class photo"), json.dumps(list(choices.values())), digest))

    def review(self, pid, action, notebook_id=None):
        with self.app.guard:
            if self.app.job["busy"]:
                raise ValueError("Wait for the current operation before reviewing photos.")
            with self.app.db() as db:
                row = db.execute("SELECT * FROM class_photos WHERE id=?", (pid,)).fetchone()
                if not row:
                    raise ValueError("Photo not found. Scan again.")
                if row["status"] == "uploaded":
                    raise ValueError("This photo is already uploaded.")
                if action == "retry" and row["status"] == "error":
                    db.execute("UPDATE class_photos SET status='approved', error=NULL WHERE id=?", (pid,))
                elif action in ("skip", "review") and not row["attempted"]:
                    db.execute("UPDATE class_photos SET status=?,error=NULL WHERE id=?", ("skipped" if action == "skip" else "review", pid))
                elif action == "approve" and row["status"] == "review":
                    choices = json.loads(row["destinations"])
                    choice = next((d for d in choices if d["notebook_id"] == notebook_id), None)
                    if not choice:
                        raise ValueError("Choose a matching class notebook before approving.")
                    digest = hashlib.sha256((self.folder / f"{pid}.jpg").read_bytes()).hexdigest()
                    if digest != row["digest"]:
                        raise ValueError("The preview changed. Skip this image and scan again.")
                    db.execute("UPDATE class_photos SET status='approved',notebook_id=?,title=?,error=NULL WHERE id=?",
                               (choice["notebook_id"], choice["title"], pid))
                else:
                    raise ValueError("This photo cannot be changed in its current state.")

    async def sync(self, photo_ids=None):
        selected = [row for row in self.records() if row['status'] == 'approved' and (photo_ids is None or row['id'] in photo_ids)]
        if any(row.get('label') != 'Selected photo' for row in selected) and not self.app.access.read(self.app.config['recordings_folder'])['photos_enabled']:
            raise ValueError("Enable Photos access to upload class photos, or continue with audio only.")
        from notebooklm import NotebookLMClient
        async with NotebookLMClient.from_storage() as client:
            configure_file_uploads(client)
            failures = 0
            for row in self.records():
                if row["status"] != "approved" or (photo_ids is not None and row['id'] not in photo_ids):
                    continue
                try:
                    await self.upload_one(client, row)
                except Exception as exc:
                    with self.app.db() as db:
                        db.execute("UPDATE class_photos SET status='error',error=? WHERE id=?", (str(exc), row["id"]))
                    failures += 1
            if failures:
                self.app.job["error"] = f"{failures} photo upload(s) failed. Review the photo queue and retry."

    async def upload_one(self, client, row):
        from notebooklm.exceptions import SourceProcessingError

        if row["status"] != "approved" or not row["notebook_id"]:
            raise ValueError("Approve the photo and its notebook before uploading.")
        path = self.folder / f"{row['id']}.jpg"
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["digest"]:
            raise ValueError("Photo changed after approval. Upload stopped.")
        nb = row["notebook_id"]
        # Use a stable, readable source name; keep the reviewed JPEG bytes unchanged.
        captured = datetime.fromisoformat(row['captured_at']).astimezone(ZoneInfo(self.app.config['timezone']))
        title = re.sub(r'[^\w.-]', '_', row['title'])
        upload = self.folder / f"{title}_{captured:%Y%m%d_%H%M}_{row['id'][:12]}.jpg"
        if not upload.exists():
            upload.write_bytes(path.read_bytes())
        if hashlib.sha256(upload.read_bytes()).hexdigest() != row["digest"]:
            raise ValueError("Upload copy changed. Upload stopped.")
        document = upload.with_name(upload.stem + "_OCR.pdf")
        if row.get('label') == 'Selected photo' and not document.is_file():
            helper = os.environ.get('VOICE_NOTEBOOK_PHOTOS_HELPER')
            if not helper or not Path(helper).is_file():
                raise ValueError('Photo conversion requires the voiceNotebook Mac app.')
            self.app.job['message'] = 'Preparing selected photo as a searchable PDF…'
            result = await asyncio.to_thread(subprocess.run, [helper, '--photo-document', str(path), str(document)], capture_output=True, timeout=180)
            if result.returncode or not document.is_file():
                raise ValueError('Could not convert this photo to PDF. Retry or choose another photo.')
        if document.is_file():
            upload = document
        sources = await client.sources.list(nb)
        saved = [s for s in sources if s.id == row['source_id']] if row['source_id'] else []
        previous_failed = bool(saved and getattr(saved[0], 'is_error', False))
        matches = (saved if saved and not (upload == document and previous_failed)
                   else [s for s in sources if s.title in (upload.name, f"Class_photo_{row['id']}.jpg") and (upload != document or s.title == upload.name)])
        if len(matches) > 1:
            raise ValueError("Duplicate photo sources found. Check the notebook before retrying.")
        failed_source = bool(matches and getattr(matches[0], 'is_error', False))
        helper = os.environ.get("VOICE_NOTEBOOK_PHOTOS_HELPER")
        if failed_source and upload != document and helper and Path(helper).is_file():
            return await self.recover_document(client, row, path, document, matches[0].id, helper)
        if failed_source:
            matches = []
        if not matches and row["attempted"] and not (failed_source or previous_failed):
            raise ValueError("Upload outcome uncertain. Check NotebookLM; this photo will not be resent automatically.")
        self.app.job["message"] = f"Uploading approved class photo → {row['title']}"
        with self.app.db() as db:
            db.execute("UPDATE class_photos SET status='uploading',attempted=1,error=NULL WHERE id=?", (row["id"],))
            if not matches:
                db.execute("UPDATE class_photos SET source_id=NULL WHERE id=?", (row['id'],))
        try:
            if matches:
                source = matches[0]
            else:
                source = await client.sources.add_file(nb, upload, wait=False)
            with self.app.db() as db:
                db.execute("UPDATE class_photos SET source_id=? WHERE id=?", (source.id, row["id"]))
            await client.sources.wait_until_ready(nb, source.id, timeout=1200)
        except Exception as exc:
            if getattr(exc, "source_id", None):
                with self.app.db() as db:
                    db.execute("UPDATE class_photos SET source_id=? WHERE id=?", (exc.source_id, row["id"]))
            elif getattr(exc, 'upload_started', None) is False:
                with self.app.db() as db:
                    db.execute("UPDATE class_photos SET attempted=0 WHERE id=? AND source_id IS NULL", (row['id'],))
            if isinstance(exc, SourceProcessingError) and upload != document and helper and Path(helper).is_file():
                return await self.recover_document(client, row, path, document, exc.source_id, helper)
            raise
        with self.app.db() as db:
            db.execute("UPDATE class_photos SET status='uploaded',error=NULL WHERE id=?", (row["id"],))
        self.app.library.mark_notebook_edit(nb)

    async def recover_document(self, client, row, image, document, source_id, helper):
        self.app.job["message"] = "Reading the approved photo on this Mac for a searchable PDF…"
        result = await asyncio.to_thread(subprocess.run,
            [helper, "--photo-document", str(image), str(document)], capture_output=True, timeout=180)
        if result.returncode or not document.is_file():
            raise ValueError("NotebookLM could not process this photo, and local PDF recovery failed. Retry the photo upload.")
        if hashlib.sha256(image.read_bytes()).hexdigest() != row["digest"]:
            raise ValueError("Photo changed after approval. Upload stopped.")
        return await self.upload_one(client, {**row, "source_id": source_id})
