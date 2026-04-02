"""
SQLite database layer.
Hierarchy: class_name → [stream →] section
- Nursery/LKG/UKG/I–X: class_name + section (stream='')
- XI/XII:               class_name + stream + section
"""
import sqlite3
import threading
import logging
from datetime import date, datetime
from contextlib import contextmanager
from typing import Optional, List, Dict

import config

log = logging.getLogger(__name__)
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


@contextmanager
def get_db():
    conn = _get_conn()
    try:
        yield conn; conn.commit()
    except Exception:
        conn.rollback(); raise


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS students (
                student_id   TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                class_name   TEXT NOT NULL,
                stream       TEXT NOT NULL DEFAULT '',
                section      TEXT NOT NULL DEFAULT '',
                roll_no      INTEGER DEFAULT 0,
                photo_path   TEXT DEFAULT '',
                enrolled_at  TEXT DEFAULT (datetime('now','localtime')),
                is_active    INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS classrooms (
                classroom_id TEXT PRIMARY KEY,
                camera_id    TEXT UNIQUE,
                class_name   TEXT DEFAULT '',
                floor        INTEGER DEFAULT 1,
                notes        TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS attendance (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id   TEXT NOT NULL REFERENCES students(student_id),
                camera_id    TEXT NOT NULL,
                classroom_id TEXT DEFAULT '',
                detected_at  TEXT NOT NULL,
                date         TEXT NOT NULL,
                confidence   REAL DEFAULT 0,
                status       TEXT DEFAULT 'present'
            );

            CREATE TABLE IF NOT EXISTS class_sections (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                class_name TEXT NOT NULL,
                stream     TEXT NOT NULL DEFAULT '',
                section    TEXT NOT NULL,
                UNIQUE(class_name, stream, section)
            );

            CREATE INDEX IF NOT EXISTS idx_att_student_date ON attendance(student_id, date);
            CREATE INDEX IF NOT EXISTS idx_att_date         ON attendance(date);
        """)
    log.info("Database ready at %s", config.DB_PATH)


# ── Class sections ─────────────────────────────────────────────────────────────

def list_sections(class_name: str, stream: str = "") -> List[str]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT section FROM class_sections WHERE class_name=? AND stream=? ORDER BY section",
            (class_name, stream)
        ).fetchall()
    return [r["section"] for r in rows]


def add_section(class_name: str, section: str, stream: str = "") -> bool:
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO class_sections (class_name, stream, section) VALUES (?,?,?)",
                (class_name, stream, section.upper())
            )
        return True
    except Exception as e:
        log.error("add_section: %s", e); return False


def remove_section(class_name: str, section: str, stream: str = "") -> bool:
    try:
        with get_db() as conn:
            conn.execute(
                "DELETE FROM class_sections WHERE class_name=? AND stream=? AND section=?",
                (class_name, stream, section.upper())
            )
        return True
    except Exception as e:
        log.error("remove_section: %s", e); return False


def ensure_default_sections(class_names: List[str]):
    """Seed Section A for every class that has no sections yet."""
    for cls in class_names:
        if cls in config.STREAM_CLASSES:
            for stream in config.STREAMS:
                if not list_sections(cls, stream):
                    add_section(cls, "A", stream)
        else:
            if not list_sections(cls, ""):
                add_section(cls, "A", "")


def list_classes() -> List[str]:
    """
    Return all distinct class names known to the system,
    sourced from the class_sections table plus any students already enrolled.
    Ordered by the canonical school sequence.
    """
    _ORDER = {
        "Nursery": 0, "LKG": 1, "UKG": 2,
        "I": 3, "II": 4, "III": 5, "IV": 6, "V": 7,
        "VI": 8, "VII": 9, "VIII": 10, "IX": 11, "X": 12,
        "XI": 13, "XII": 14,
    }
    with get_db() as conn:
        from_sections = {
            r[0] for r in conn.execute(
                "SELECT DISTINCT class_name FROM class_sections"
            ).fetchall()
        }
        from_students = {
            r[0] for r in conn.execute(
                "SELECT DISTINCT class_name FROM students WHERE is_active=1"
            ).fetchall()
        }
    all_classes = from_sections | from_students
    return sorted(all_classes, key=lambda c: (_ORDER.get(c, 99), c))


# ── Students ───────────────────────────────────────────────────────────────────

def add_student(student_id: str, name: str, class_name: str,
                stream: str = "", section: str = "",
                roll_no: int = 0, photo_path: str = "") -> bool:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO students (student_id,name,class_name,stream,section,roll_no,photo_path)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(student_id) DO UPDATE SET
                 name=excluded.name, class_name=excluded.class_name,
                 stream=excluded.stream, section=excluded.section,
                 roll_no=excluded.roll_no, photo_path=excluded.photo_path, is_active=1""",
            (student_id, name, class_name, stream, section.upper(), roll_no, photo_path)
        )
    return True


def get_student(student_id: str) -> Optional[Dict]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM students WHERE student_id=? AND is_active=1", (student_id,)
        ).fetchone()
    return dict(row) if row else None


def list_students(class_name: str = None, stream: str = None,
                  section: str = None) -> List[Dict]:
    clauses, params = ["is_active=1"], []
    if class_name:
        clauses.append("class_name=?"); params.append(class_name)
    if stream is not None and stream != "":
        clauses.append("stream=?"); params.append(stream)
    if section:
        clauses.append("section=?"); params.append(section.upper())
    where = " AND ".join(clauses)
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM students WHERE {where} ORDER BY class_name,stream,section,roll_no",
            params
        ).fetchall()
    return [dict(r) for r in rows]


def delete_student(student_id: str):
    with get_db() as conn:
        conn.execute("UPDATE students SET is_active=0 WHERE student_id=?", (student_id,))


# ── Classrooms ─────────────────────────────────────────────────────────────────

def upsert_classroom(classroom_id: str, camera_id: str,
                     class_name: str = "", floor: int = 1):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO classrooms (classroom_id,camera_id,class_name,floor)
               VALUES (?,?,?,?)
               ON CONFLICT(classroom_id) DO UPDATE SET
                 camera_id=excluded.camera_id, class_name=excluded.class_name""",
            (classroom_id, camera_id, class_name, floor)
        )


def get_classroom_by_camera(camera_id: str) -> Optional[Dict]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM classrooms WHERE camera_id=?", (camera_id,)
        ).fetchone()
    return dict(row) if row else None


def list_classrooms() -> list:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM classrooms ORDER BY classroom_id").fetchall()
    return [dict(r) for r in rows]


# ── Attendance ─────────────────────────────────────────────────────────────────

def mark_attendance(student_id: str, camera_id: str,
                    confidence: float, status: str = "present") -> bool:
    if not get_student(student_id):
        log.warning("Skipping attendance for '%s' — not in DB.", student_id)
        return False
    today     = date.today().isoformat()
    now_str   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    classroom = get_classroom_by_camera(camera_id)
    cid       = classroom["classroom_id"] if classroom else ""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO attendance (student_id,camera_id,classroom_id,detected_at,date,confidence,status)"
            " VALUES (?,?,?,?,?,?,?)",
            (student_id, camera_id, cid, now_str, today, confidence, status)
        )
    return True


def was_marked_today(student_id: str) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM attendance WHERE student_id=? AND date=date('now','localtime')",
            (student_id,)
        ).fetchone()
    return bool(row and row["cnt"] > 0)


def get_attendance_by_date(target_date: str, class_name: str = None,
                           stream: str = None, section: str = None) -> List[Dict]:
    clauses, params = ["a.date=?"], [target_date]
    if class_name:
        clauses.append("s.class_name=?"); params.append(class_name)
    if stream is not None and stream != "":
        clauses.append("s.stream=?"); params.append(stream)
    if section:
        clauses.append("s.section=?"); params.append(section.upper())
    where = " AND ".join(clauses)
    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT a.*, s.name, s.class_name, s.stream, s.section, s.roll_no
               FROM attendance a JOIN students s ON a.student_id=s.student_id
               WHERE {where} ORDER BY s.class_name, s.stream, s.section, a.detected_at""",
            params
        ).fetchall()
    return [dict(r) for r in rows]


def get_daily_stats(target_date: str) -> Dict:
    with get_db() as conn:
        present = conn.execute(
            """SELECT s.class_name, COUNT(DISTINCT a.student_id) AS present
               FROM attendance a JOIN students s ON a.student_id=s.student_id
               WHERE a.date=? GROUP BY s.class_name""", (target_date,)
        ).fetchall()
        totals = conn.execute(
            "SELECT class_name, COUNT(*) AS total FROM students WHERE is_active=1 GROUP BY class_name"
        ).fetchall()
    pm = {r["class_name"]: r["present"] for r in present}
    classes = []
    for row in totals:
        cls = row["class_name"]; total = row["total"]; pres = pm.get(cls, 0)
        classes.append({"class_name": cls, "total": total, "present": pres,
                         "absent": total-pres,
                         "percentage": round(pres/total*100, 1) if total else 0})
    return {"date": target_date, "classes": classes}


def get_recent_detections(limit: int = 25) -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT a.detected_at, a.student_id, s.name, s.class_name,
                      s.stream, s.section, a.camera_id, a.confidence
               FROM attendance a JOIN students s ON a.student_id=s.student_id
               ORDER BY a.detected_at DESC LIMIT ?""", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
