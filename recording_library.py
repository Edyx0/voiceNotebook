"""Local recording labels, playback copies, and weeks read from NotebookLM."""
from datetime import date, datetime, timedelta
from pathlib import Path
import re
import threading
from zoneinfo import ZoneInfo


WEEK = re.compile(r"(?<!\w)(?:week|w|hafta)\s*[-_.]?\s*(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?(?!\w)", re.I)


def title_weeks(title):
    match = WEEK.search(title or "")
    if not match:
        return None
    start, end = int(match[1]), int(match[2] or match[1])
    return (start, end) if 1 <= start <= end <= 60 else None


class RecordingLibrary:
    def __init__(self, app, run_media):
        self.app = app
        self.run_media = run_media
        self.preview_lock = threading.Lock()
        with app.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS recording_labels (id TEXT PRIMARY KEY, name TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS notebook_catalog (id TEXT PRIMARY KEY, title TEXT, created_at TEXT);
            """)

    def cache_notebooks(self, notebooks):
        values = []
        for notebook in notebooks:
            if not isinstance(getattr(notebook, "id", None), str):
                continue
            created = getattr(notebook, "created_at", None)
            values.append((notebook.id, notebook.title or "", created.isoformat() if isinstance(created, datetime) else None))
        with self.app.db() as db:
            db.execute("DELETE FROM notebook_catalog")
            db.executemany("INSERT INTO notebook_catalog VALUES(?,?,?)", values)

    def annotate(self, recordings):
        with self.app.db() as db:
            names = dict(db.execute("SELECT id,name FROM recording_labels"))
            notebooks = [dict(row) for row in db.execute("SELECT * FROM notebook_catalog ORDER BY created_at DESC")]
        zone = ZoneInfo(self.app.config["timezone"])
        anchor = None
        for notebook in notebooks:
            weeks = title_weeks(notebook["title"])
            if weeks and weeks[0] == weeks[1] and notebook["created_at"]:
                created = datetime.fromisoformat(notebook["created_at"]).astimezone(zone).date()
                anchor = created - timedelta(days=created.weekday() + (weeks[0] - 1) * 7)
                break
        if anchor is None and self.app.config["week_one"]:
            anchor = date.fromisoformat(self.app.config["week_one"])
        by_id = {n["id"]: n for n in notebooks}
        for row in recordings:
            row["display_name"] = names.get(row["id"], row["name"])
            if (row.get("reason") or "").startswith("Add week 1 and"):
                row["reason"] = ""
            weeks, source = None, None
            notebook = by_id.get(row.get("notebook_id"))
            if notebook:
                weeks = title_weeks(notebook["title"])
                source = "NotebookLM · " + notebook["title"]
            if weeks is None and row.get("route"):
                week = row["route"]["week"]
                weeks, source = (week, week), "Recording assignment"
            if weeks is None and anchor and row.get("recorded_at"):
                recorded = datetime.fromisoformat(row["recorded_at"]).astimezone(zone).date()
                week = (recorded - anchor).days // 7 + 1
                if 1 <= week <= self.app.config["semester_weeks"]:
                    weeks, source = (week, week), "Estimated from recent NotebookLM notebook dates" if notebooks else "Timetable dates"
            row["week"] = weeks[0] if weeks else None
            row["week_label"] = (f"Week {weeks[0]}" + (f"–{weeks[1]}" if weeks[0] != weeks[1] else "")) if weeks else "Unassigned week"
            row["week_source"] = source
        return recordings

    def rename(self, rid, name):
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 160 or any(ord(c) < 32 for c in name):
            raise ValueError("Enter a name between 1 and 160 characters.")
        with self.app.db() as db:
            if not db.execute("SELECT 1 FROM recordings WHERE id=?", (rid,)).fetchone():
                raise ValueError("Recording not found.")
            db.execute("INSERT OR REPLACE INTO recording_labels VALUES(?,?)", (rid, name.strip()))

    def preview(self, rid):
        with self.app.db() as db:
            row = db.execute("SELECT path FROM recordings WHERE id=?", (rid,)).fetchone()
        if not row:
            raise ValueError("Recording not found.")
        original = Path(row["path"])
        if not original.is_file():
            raise ValueError("Recording unavailable. Check folder access and scan again.")
        folder = self.app.home / "previews"
        with self.preview_lock:
            folder.mkdir(exist_ok=True, mode=0o700)
            output = folder / f"{rid}.mp3"
            if not output.exists():
                temporary = folder / f"{rid}.tmp.mp3"
                try:
                    result = self.run_media(["ffmpeg", "-v", "error", "-y", "-i", str(original), "-vn", "-c:a", "libmp3lame", "-q:a", "5", str(temporary)], timeout=600)
                    if result.returncode:
                        raise ValueError("Could not prepare this recording for playback.")
                    temporary.replace(output)
                finally:
                    temporary.unlink(missing_ok=True)
        return output


def audio_range(header, size):
    if not header:
        return 0, size - 1, False
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header)
    if not match or not any(match.groups()):
        raise ValueError("Invalid audio range")
    first, last = match.groups()
    start = int(first) if first else max(0, size - int(last))
    end = min(int(last), size - 1) if first and last else size - 1
    if start > end or start >= size:
        raise ValueError("Invalid audio range")
    return start, end, True
