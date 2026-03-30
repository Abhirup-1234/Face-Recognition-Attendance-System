"""
SQLite database layer.
Tables: students, classrooms, attendance, daily_summary
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
        _local.conn = sqlite3.connect(
            config.DB_PATH,
            check_same_thread=False,
            # No detect_types - store timestamps as plain strings
        )
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


@contextmanager
def get_db():
    conn = _get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ── Schema ─────────────────────────────────────────────────────────────────────

def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS students (
                student_id   TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                class_name   TEXT NOT NULL,
                section      TEXT DEFAULT '',
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
                frame_path   TEXT DEFAULT '',
                status       TEXT DEFAULT 'present'
            );

            CREATE INDEX IF NOT EXISTS idx_att_student_date
                ON attendance(student_id, date);
            CREATE INDEX IF NOT EXISTS idx_att_date
                ON attendance(date);
        """)
    log.info("Database initialised at %s", config.DB_PATH)


# ── Students ───────────────────────────────────────────────────────────────────

def add_student(student_id: str, name: str, class_name: str,
                section: str = "", roll_no: int = 0,
                photo_path: str = "") -> bool:
    with get_db() as conn:
        conn.execute(
            """INSERT INTO students
               (student_id, name, class_name, section, roll_no, photo_path)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(student_id) DO UPDATE SET
                 name=excluded.name, class_name=excluded.class_name,
                 section=excluded.section, roll_no=excluded.roll_no,
                 photo_path=excluded.photo_path, is_active=1""",
            (student_id, name, class_name, section, roll_no, photo_path),
        )
    return True


def get_student(student_id: str) -> Optional[Dict]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM students WHERE student_id=? AND is_active=1",
            (student_id,)
        ).fetchone()
    return dict(row) if row else None


def list_students(class_name: str = None) -> List[Dict]:
    with get_db() as conn:
        if class_name:
            rows = conn.execute(
                "SELECT * FROM students WHERE class_name=? AND is_active=1"
                " ORDER BY roll_no",
                (class_name,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM students WHERE is_active=1"
                " ORDER BY class_name, roll_no"
            ).fetchall()
    return [dict(r) for r in rows]


def delete_student(student_id: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE students SET is_active=0 WHERE student_id=?",
            (student_id,)
        )


# ── Classrooms ─────────────────────────────────────────────────────────────────

def upsert_classroom(classroom_id: str, camera_id: str,
                     class_name: str = "", floor: int = 1):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO classrooms (classroom_id, camera_id, class_name, floor)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(classroom_id) DO UPDATE SET
                 camera_id=excluded.camera_id,
                 class_name=excluded.class_name""",
            (classroom_id, camera_id, class_name, floor),
        )


def get_classroom_by_camera(camera_id: str) -> Optional[Dict]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM classrooms WHERE camera_id=?", (camera_id,)
        ).fetchone()
    return dict(row) if row else None


def list_classrooms() -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM classrooms ORDER BY classroom_id"
        ).fetchall()
    return [dict(r) for r in rows]


# ── Attendance ─────────────────────────────────────────────────────────────────

def mark_attendance(student_id: str, camera_id: str,
                    confidence: float, status: str = "present") -> bool:
    # Guard: student must exist in DB
    if not get_student(student_id):
        log.warning(
            "Skipping attendance for '%s' - not in database. "
            "Re-enroll or delete data/embeddings/%s.npy",
            student_id, student_id
        )
        return False

    today      = date.today().isoformat()
    now_str    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    classroom  = get_classroom_by_camera(camera_id)
    classroom_id = classroom["classroom_id"] if classroom else ""

    with get_db() as conn:
        conn.execute(
            """INSERT INTO attendance
               (student_id, camera_id, classroom_id, detected_at, date,
                confidence, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (student_id, camera_id, classroom_id, now_str, today,
             confidence, status),
        )
    return True


def was_marked_today(student_id: str) -> bool:
    """Returns True if student was marked present today on ANY camera."""
    with get_db() as conn:
        row = conn.execute(
            """SELECT COUNT(*) as cnt FROM attendance
               WHERE student_id = ?
                 AND date = date('now','localtime')""",
            (student_id,),
        ).fetchone()
    return bool(row and row["cnt"] > 0)


def get_attendance_by_date(target_date: str,
                           class_name: str = None) -> List[Dict]:
    with get_db() as conn:
        if class_name:
            rows = conn.execute(
                """SELECT a.*, s.name, s.class_name, s.section, s.roll_no
                   FROM attendance a
                   JOIN students s ON a.student_id = s.student_id
                   WHERE a.date=? AND s.class_name=?
                   ORDER BY a.detected_at""",
                (target_date, class_name)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT a.*, s.name, s.class_name, s.section, s.roll_no
                   FROM attendance a
                   JOIN students s ON a.student_id = s.student_id
                   WHERE a.date=?
                   ORDER BY a.detected_at""",
                (target_date,)
            ).fetchall()
    return [dict(r) for r in rows]


def get_attendance_for_student(student_id: str,
                                start_date: str,
                                end_date: str) -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM attendance
               WHERE student_id=? AND date BETWEEN ? AND ?
               ORDER BY detected_at""",
            (student_id, start_date, end_date)
        ).fetchall()
    return [dict(r) for r in rows]


def get_daily_stats(target_date: str) -> Dict:
    with get_db() as conn:
        present_rows = conn.execute(
            """SELECT s.class_name, COUNT(DISTINCT a.student_id) AS present
               FROM attendance a
               JOIN students s ON a.student_id = s.student_id
               WHERE a.date=?
               GROUP BY s.class_name""",
            (target_date,)
        ).fetchall()
        total_rows = conn.execute(
            """SELECT class_name, COUNT(*) AS total
               FROM students WHERE is_active=1
               GROUP BY class_name"""
        ).fetchall()

    present_map = {r["class_name"]: r["present"] for r in present_rows}
    classes = []
    for row in total_rows:
        cls     = row["class_name"]
        total   = row["total"]
        present = present_map.get(cls, 0)
        classes.append({
            "class_name": cls,
            "total":      total,
            "present":    present,
            "absent":     total - present,
            "percentage": round(present / total * 100, 1) if total else 0,
        })
    return {"date": target_date, "classes": classes}


def get_recent_detections(limit: int = 25) -> List[Dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT a.detected_at, a.student_id, s.name,
                      s.class_name, s.section, a.camera_id, a.confidence
               FROM attendance a
               JOIN students s ON a.student_id = s.student_id
               ORDER BY a.detected_at DESC LIMIT ?""",
            (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
