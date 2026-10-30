"""Keep an all-weeks notebook in sync with each course's existing sources."""
import json
import re


COURSE = re.compile(r"[A-Z]{2,8}\d{3}")
TITLE = re.compile(r"^([A-Z]{2,8})(\d{3})?(?:\s+(?:W|WEEK|HAFTA)\s*\d+(?:\s*[-–]\s*\d+)*)?$", re.I)


class CourseNotebooks:
    def __init__(self, app):
        self.app = app
        with app.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS course_notebooks
                    (course TEXT PRIMARY KEY, notebook_id TEXT, title TEXT NOT NULL, status TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS course_sources
                    (course TEXT, origin_notebook_id TEXT, origin_source_id TEXT,
                     target_source_id TEXT, title TEXT, status TEXT, previous_ids TEXT,
                     PRIMARY KEY(course, origin_notebook_id, origin_source_id));
                CREATE TABLE IF NOT EXISTS course_notebook_assignments
                    (notebook_id TEXT PRIMARY KEY, course TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS course_notebook_ambiguities
                    (notebook_id TEXT PRIMARY KEY, title TEXT NOT NULL, courses TEXT NOT NULL);
            """)

    def records(self):
        with self.app.db() as db:
            return [dict(row) for row in db.execute(
                "SELECT course, notebook_id, title, status FROM course_notebooks WHERE notebook_id IS NOT NULL ORDER BY course")]

    def assign(self, notebook_id, course):
        if not isinstance(notebook_id, str) or not notebook_id or not isinstance(course, str):
            raise ValueError("Choose a notebook and a valid course code.")
        course = course.strip().upper()
        if not COURSE.fullmatch(course):
            raise ValueError("Choose a notebook and a valid course code.")
        with self.app.db() as db:
            db.execute("INSERT OR REPLACE INTO course_notebook_assignments VALUES(?,?)", (notebook_id, course))
            db.execute("DELETE FROM course_notebook_ambiguities WHERE notebook_id=?", (notebook_id,))

    def ambiguities(self):
        with self.app.db() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM course_notebook_ambiguities ORDER BY title")]
        for row in rows:
            row["courses"] = json.loads(row["courses"])
        return rows

    def groups(self, notebooks):
        prefix = self.app.config.get("notebook_prefix", "")
        parsed = []
        courses = {slot["course"].strip().upper() for slot in self.app.config["lectures"] if COURSE.fullmatch(slot["course"].strip().upper())}
        with self.app.db() as db:
            assignments = dict(db.execute("SELECT notebook_id, course FROM course_notebook_assignments"))
        for notebook in notebooks:
            title = (notebook.title or "").strip()
            if prefix and title.casefold().startswith(prefix.casefold()):
                title = title[len(prefix):].strip()
            match = TITLE.fullmatch(title)
            if match:
                full_course = (match[1] + (match[2] or "")).upper()
                if match[2] and full_course not in courses and notebook.id not in assignments and not re.search(r"\s+(?:W|WEEK|HAFTA)\s*\d", title, re.I):
                    continue
                parsed.append((notebook, match))
                if match[2]:
                    courses.add((match[1] + match[2]).upper())
        groups = {}
        ambiguous = []
        for notebook, match in parsed:
            candidates = [c for c in courses if c.startswith(match[1].upper())] if not match[2] else [(match[1] + match[2]).upper()]
            course = assignments.get(notebook.id) or (candidates[0] if len(candidates) == 1 else None)
            if course:
                groups.setdefault(course, []).append(notebook)
            elif candidates:
                ambiguous.append({"notebook_id": notebook.id, "title": notebook.title, "courses": sorted(candidates)})
        return groups, ambiguous

    async def destination(self, client, notebooks, course):
        title = f"{self.app.config.get('notebook_prefix', '')}{course} · All weeks"
        with self.app.db() as db:
            row = db.execute("SELECT * FROM course_notebooks WHERE course=?", (course,)).fetchone()
        if row and row["notebook_id"]:
            if not any(nb.id == row["notebook_id"] for nb in notebooks):
                raise ValueError(f"{title} is unavailable in this Google account. Check the connection.")
            return row["notebook_id"]
        matches = [nb for nb in notebooks if nb.title == title]
        if len(matches) > 1 or (matches and not row):
            raise ValueError(f"A notebook named {title} already exists. Rename it before creating a course notebook.")
        if not matches and row:
            raise ValueError(f"Creation of {title} is uncertain. Check NotebookLM before retrying.")
        if matches:
            notebook = matches[0]
        else:
            with self.app.db() as db:
                db.execute("INSERT INTO course_notebooks VALUES(?,NULL,?,'pending')", (course, title))
            self.app.job["message"] = f"Creating {title}…"
            notebook = await client.notebooks.create(title)
            notebooks.append(notebook)
        with self.app.db() as db:
            db.execute("UPDATE course_notebooks SET notebook_id=?,status='ready' WHERE course=?", (notebook.id, course))
        return notebook.id

    async def copy_source(self, client, course, origin, target, source):
        key = (course, origin, source.id)
        with self.app.db() as db:
            progress = db.execute("SELECT * FROM course_sources WHERE course=? AND origin_notebook_id=? AND origin_source_id=?", key).fetchone()
        if progress and progress["status"] == "done":
            return
        if progress and progress["target_source_id"]:
            target_id = progress["target_source_id"]
        else:
            existing = await client.sources.list(target, strict=True)
            if progress:
                before = set(json.loads(progress["previous_ids"]))
                candidates = [item for item in existing if item.id not in before and item.title == progress["title"]]
                if len(candidates) != 1:
                    raise ValueError(f"Copy of {source.title or 'a source'} is uncertain. Check the course notebook before retrying.")
                target_id = candidates[0].id
            else:
                with self.app.db() as db:
                    db.execute("INSERT INTO course_sources VALUES(?,?,?,NULL,?,'pending',?)", (*key, source.title, json.dumps([item.id for item in existing])))
                self.app.job["message"] = f"Copying sources to {course} · All weeks…"
                copies = await client.sources.copy(origin, [source.id], target)
                if len(copies) != 1 or copies[0].original_id != source.id or not copies[0].source.id:
                    raise ValueError(f"Copy of {source.title or 'a source'} is uncertain. Check the course notebook before retrying.")
                target_id = copies[0].source.id
            with self.app.db() as db:
                db.execute("UPDATE course_sources SET target_source_id=?,status='processing' WHERE course=? AND origin_notebook_id=? AND origin_source_id=?", (target_id, *key))
        await client.sources.wait_until_ready(target, target_id, timeout=1200)
        with self.app.db() as db:
            db.execute("UPDATE course_sources SET status='done' WHERE course=? AND origin_notebook_id=? AND origin_source_id=?", key)

    async def sync(self):
        from notebooklm import NotebookLMClient
        from notebook_uploads import configure_file_uploads

        errors = []
        async with NotebookLMClient.from_storage() as client:
            configure_file_uploads(client)
            notebooks = await client.notebooks.list()
            groups, ambiguous = self.groups(notebooks)
            with self.app.db() as db:
                db.execute("DELETE FROM course_notebook_ambiguities")
                db.executemany("INSERT INTO course_notebook_ambiguities VALUES(?,?,?)",
                               [(item["notebook_id"], item["title"], json.dumps(item["courses"])) for item in ambiguous])
            for course, originals in sorted(groups.items()):
                try:
                    target = await self.destination(client, notebooks, course)
                    for original in originals:
                        sources = await client.sources.list(original.id, strict=True)
                        for source in sources:
                            if getattr(source, "is_error", False):
                                errors.append(f"{original.title}: a source needs attention.")
                            elif getattr(source, "is_ready", True):
                                try:
                                    await self.copy_source(client, course, original.id, target, source)
                                except Exception as exc:
                                    errors.append(f"{course}: {exc}")
                            else:
                                errors.append(f"{original.title}: a source is still processing.")
                except Exception as exc:
                    errors.append(f"{course}: {exc}")
            self.app.library.cache_notebooks(notebooks)
        if ambiguous:
            errors.append("Choose the course for: " + ", ".join(item["title"] for item in ambiguous))
        if errors:
            raise ValueError("; ".join(dict.fromkeys(errors)))
