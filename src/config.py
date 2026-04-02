"""
FaceTrack AI — Configuration
Classes are managed entirely in the database (class_sections table).
They are no longer stored in settings.json.
"""
import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR        = BASE_DIR / "data"
DB_PATH         = DATA_DIR / "attendance.db"
EMBEDDINGS_DIR  = DATA_DIR / "embeddings"
STUDENT_IMG_DIR = DATA_DIR / "student_photos"
LOG_DIR         = DATA_DIR / "logs"
REPORT_DIR      = DATA_DIR / "reports"
FRONTEND_DIST   = BASE_DIR / "frontend" / "dist"
SETTINGS_FILE   = BASE_DIR / "settings.json"

# Only directories that must always exist (models dir removed — InsightFace
# downloads its own models to ~/.insightface automatically)
for _d in [DATA_DIR, EMBEDDINGS_DIR, STUDENT_IMG_DIR, LOG_DIR, REPORT_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ── Load .env ──────────────────────────────────────────────────────────────────
load_dotenv(BASE_DIR / ".env")

# ── Secrets ────────────────────────────────────────────────────────────────────
SECRET_KEY     = os.getenv("SECRET_KEY",     "facetrack-dev-key-change-in-production")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
_SECRETS = {"SECRET_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD"}

# ── Flask ──────────────────────────────────────────────────────────────────────
DEBUG      = False
HOST       = "0.0.0.0"
PORT       = 5000
ASYNC_MODE = "threading"

# ── Cameras ────────────────────────────────────────────────────────────────────
CAMERAS = {"CAM-101": 1}
FRAME_WIDTH        = 1280
FRAME_HEIGHT       = 720
PROCESS_EVERY_N    = 5
STREAM_FPS         = 10
USE_DSHOW          = False
IMAGE_FOLDER_DELAY = 2.0

# ── RetinaFace / ArcFace ───────────────────────────────────────────────────────
DET_THRESH             = 0.5
REC_THRESHOLD          = 0.4
EMBEDDINGS_PER_STUDENT = 20
CONFIRM_FRAMES         = 3

# ── Preprocessing ──────────────────────────────────────────────────────────────
ENABLE_CLAHE     = True
CLAHE_CLIP_LIMIT = 2.5
CLAHE_TILE_SIZE  = (8, 8)
ENABLE_DENOISE   = True
SUPER_RES_SCALE  = 2

# ── School ─────────────────────────────────────────────────────────────────────
SCHOOL_NAME        = "Narula Public School"
ADMIN_DISPLAY_NAME = "Administrator"

# ── Default class list — seeded into DB on first startup only ─────────────────
# After first run, classes live entirely in the class_sections DB table.
# This list is NEVER written to settings.json.
DEFAULT_CLASSES = [
    "Nursery", "LKG", "UKG",
    "I", "II", "III", "IV", "V",
    "VI", "VII", "VIII", "IX", "X",
    "XI", "XII",
]

# Fixed streams — only applicable to XI and XII
STREAMS        = ["Science", "Commerce", "Humanities"]
STREAM_CLASSES = {"XI", "XII"}

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
LOG_FILE  = LOG_DIR / "attendance.log"

# ── Runtime settings (never includes CLASSES) ─────────────────────────────────
_RUNTIME_KEYS = {
    "REC_THRESHOLD", "DET_THRESH", "CONFIRM_FRAMES", "EMBEDDINGS_PER_STUDENT",
    "USE_DSHOW", "PROCESS_EVERY_N", "STREAM_FPS", "FRAME_WIDTH", "FRAME_HEIGHT",
    "ENABLE_CLAHE", "CLAHE_CLIP_LIMIT", "ENABLE_DENOISE", "SUPER_RES_SCALE",
    "SCHOOL_NAME", "ADMIN_DISPLAY_NAME",
}

log = logging.getLogger(__name__)


def get_settings() -> dict:
    import sys
    module = sys.modules[__name__]
    return {k: getattr(module, k, None) for k in _RUNTIME_KEYS}


def apply_settings(data: dict):
    import sys
    module = sys.modules[__name__]
    for key, val in data.items():
        if key in _SECRETS or key not in _RUNTIME_KEYS:
            continue
        setattr(module, key, val)


def save_settings(data: dict) -> bool:
    try:
        current = {}
        if SETTINGS_FILE.exists():
            try:
                current = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                for k in _SECRETS:
                    current.pop(k, None)
                # Strip any stale CLASSES key that may be in an old file
                current.pop("CLASSES", None)
            except Exception:
                current = {}
        safe = {k: v for k, v in data.items()
                if k not in _SECRETS and k in _RUNTIME_KEYS}
        current.update(safe)
        SETTINGS_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")
        apply_settings(current)
        return True
    except Exception as e:
        log.error("Failed to save settings: %s", e)
        return False


def load_settings():
    if not SETTINGS_FILE.exists():
        return
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        for k in _SECRETS:
            data.pop(k, None)
        data.pop("CLASSES", None)   # ignore stale key
        apply_settings(data)
    except Exception as e:
        log.warning("Could not load settings.json: %s — using defaults", e)


load_settings()
