"""Turn local Vision OCR into editable timetable drafts. Unreadable times stay blank."""
import base64
import binascii
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unicodedata

DAY_WORDS = [("monday", "mon", "pazartesi", "pzt"), ("tuesday", "tue", "tues", "sali", "sal"),
             ("wednesday", "wed", "carsamba", "car"), ("thursday", "thu", "thur", "thurs", "persembe", "per"),
             ("friday", "fri", "cuma", "cum"), ("saturday", "sat", "cumartesi", "cmt"), ("sunday", "sun", "pazar", "paz")]
TIME = re.compile(r"(?<!\d)([01]?\d|2[0-3])[:.]([0-5]\d)(?!\d)")
HOUR_RANGE = re.compile(r"([01]?\d|2[0-3])\s*[-–—]\s*([01]?\d|2[0-3])")
COURSE = re.compile(r"(?<!\w)([A-Za-zÇĞİÖŞÜçğıöşü]{2,10})[ -]?(\d{2,4}[A-Za-z]?)(?!\w)")


def normalized(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold().replace("ı", "i")) if not unicodedata.combining(c))


def days_in(text):
    text = normalized(text)
    found = []
    for day, words in enumerate(DAY_WORDS):
        for word in words:
            for match in re.finditer(r"\b" + word + r"\b", text):
                found.append((day, match.start(), match.end()))
    return sorted(set(found), key=lambda item: item[1])


def times_in(text):
    hours = HOUR_RANGE.fullmatch(text.strip())
    if hours and int(hours[1]) < int(hours[2]):
        return [f"{int(hour):02d}:00" for hour in hours.groups()]
    return [f"{int(m[1]):02d}:{m[2]}" for m in TIME.finditer(text)]


def parse_observations(observations):
    if not isinstance(observations, list):
        raise ValueError("The image could not be read.")
    rows = []
    for item in observations:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        try:
            row = {"text":item["text"].strip(), **{k:float(item.get(k, 0)) for k in ("x","y","width","height")},
                   "confidence":float(item.get("confidence", 1))}
        except (ValueError, TypeError):
            continue
        row["cx"] = row["x"] + row["width"]/2
        row["cy"] = row["y"] + row["height"]/2
        rows.append(row)
    rows.sort(key=lambda r:(r["y"],r["x"]))
    headers = []
    for row in rows:
        if not COURSE.search(row["text"]) and not times_in(row["text"]):
            for day, a, b in days_in(row["text"]):
                headers.append({"day":day,"x":row["x"]+row["width"]*(a+b)/2/max(1,len(normalized(row["text"]))),"y":row["cy"]})
    # A header is a row of day names. Day labels in a vertical list aren't column headers.
    header_group = []
    for marker in headers:
        group = [m for m in headers if abs(m["y"]-marker["y"]) < .035]
        if len({m["day"] for m in group}) > len({m["day"] for m in header_group}):
            header_group = group
    columns = sorted(header_group, key=lambda m:m["x"]) if len({m["day"] for m in header_group}) >= 2 else []
    slots, warnings, seen = [], [], set()
    for row in rows:
        codes = list(COURSE.finditer(row["text"]))
        if not codes:
            continue
        for code in codes:
            course = (code[1]+code[2]).upper()
            if normalized(code[1]) in {"room", "oda", "derslik", "classroom", "salon"}:
                continue
            cx = row["x"]+row["width"]*(code.start()+code.end())/2/max(1,len(row["text"]))
            own_days = days_in(row["text"])
            day = own_days[0][0] if len(own_days)==1 else None
            if day is None and columns:
                day = min(columns,key=lambda c:abs(c["x"]-cx))["day"]
            if day is None:
                nearby = [h for h in headers if abs(h["y"]-row["cy"]) < max(.025,row["height"])]
                if len({h["day"] for h in nearby})==1:
                    day = nearby[0]["day"]
            if day is None:
                warnings.append(f"{course}: weekday could not be read. Select it before saving.")
            times = times_in(row["text"])
            explicit = len(times)>=2
            grid_time = False
            if not explicit:
                aligned = [r for r in rows if abs(r["cy"]-row["cy"]) < max(.018,row["height"]*.7)
                           and times_in(r["text"]) and (not columns or abs(r["cx"]-cx)<.15 or r["cx"]<columns[0]["x"]-.07)]
                aligned.sort(key=lambda r:abs(r["cx"]-cx))
                if aligned:
                    times=times_in(aligned[0]["text"])
                    explicit=len(times)>=2
                    grid_time = bool(columns and explicit and aligned[0]["x"]+aligned[0]["width"] < columns[0]["x"])
                elif columns:
                    # Common photo layout: a course code with an explicit time range below it.
                    nearby=[r for r in rows if 0 < abs(r["cy"]-row["cy"]) < .10 and abs(r["cx"]-cx)<.12
                            and r["x"]+r["width"] >= columns[0]["x"]
                            and len(times_in(r["text"]))>=2 and not COURSE.search(r["text"])]
                    nearby.sort(key=lambda r:abs(r["cy"]-row["cy"]))
                    if nearby:
                        times=times_in(nearby[0]["text"])
                        explicit=True
            start = times[0] if times else ""
            end = times[1] if len(times)>=2 else ""
            if end and start>=end:
                start=end=""
                explicit=False
            if not start or not end:
                warnings.append(f"{course}: start or end time could not be read. Complete the blank fields.")
            if columns and not times_in(row["text"]):
                warnings.append(f"{course}: times were read from an aligned table row. Check the lecture duration.")
            key=(course,day,start,end, row["cy"] if not start or not end else None)
            if key in seen:
                continue
            seen.add(key)
            slots.append({"course":course,"day":day,"start":start,"end":end,"needs_review":grid_time or not explicit or day is None or row["confidence"]<.7,
                          "grid_time":grid_time})
    # Merge only consecutive, readable table cells; never fill a missing hour.
    merged = []
    for slot in slots:
        previous = next((s for s in reversed(merged) if slot["grid_time"] and s["grid_time"]
                         and s["course"]==slot["course"] and s["day"]==slot["day"]
                         and s["end"]==slot["start"]), None)
        if previous is not None:
            previous["end"] = slot["end"]
        else:
            merged.append(slot)
    slots = [{k:v for k,v in slot.items() if k!="grid_time"} for slot in merged]
    if not slots:
        warnings.append("No course codes could be identified. Try a straight, sharper crop of the timetable, or add lecture times manually.")
    return {"slots":slots,"warnings":list(dict.fromkeys(warnings)),"text":"\n".join(r["text"] for r in rows)}


def recognize_photo(content, helper):
    if not isinstance(content, str) or len(content)>28_000_000:
        raise ValueError("Choose a timetable image smaller than 20 MB.")
    try:
        image=base64.b64decode(content,validate=True)
    except (ValueError,binascii.Error):
        raise ValueError("The image could not be read. Choose it again.") from None
    if not image or len(image)>20_000_000:
        raise ValueError("Choose a timetable image smaller than 20 MB.")
    if not helper.is_file():
        raise ValueError("Photo recognition is unavailable. Rebuild or reinstall the Mac app.")
    with tempfile.TemporaryDirectory(prefix="voiceNotebook-timetable-") as temp:
        path=Path(temp)/"timetable-image"
        path.write_bytes(image)
        try:
            result=subprocess.run([str(helper),str(path)],capture_output=True,text=True,timeout=90)
        except subprocess.TimeoutExpired:
            raise ValueError("Reading the photo took too long. Try a smaller, sharper crop.") from None
        if result.returncode:
            raise ValueError("The timetable image could not be read. Try a JPEG, PNG or HEIC photo.")
        return parse_observations(json.loads(result.stdout).get("observations",[]))
