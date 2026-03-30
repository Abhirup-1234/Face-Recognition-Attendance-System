"""
FaceTrack AI — Configuration

Single source of truth for all settings.
- Secrets (passwords, keys) come from .env
- Runtime-editable settings are stored in settings.json (excluded from git)
- All other defaults live here

Usage anywhere in the codebase:
    import config
    print(config.REC_THRESHOLD)
    config.save_settings({"REC_THRESHOLD": 0.45})
"""
import os
import json
import logging
from pathlib import Path

from dotenv import load_dotenv

# ── Paths ──────────────────────────────────────────────────────────────────────
# src/config.py → src/ → project_root/
BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR        = BASE_DIR / "data"
DB_PATH         = DATA_DIR / "attendance.db"
EMBEDDINGS_DIR  = DATA_DIR / "embeddings"
STUDENT_IMG_DIR = DATA_DIR / "student_photos"
LOG_DIR         = DATA_DIR / "logs"
REPORT_DIR      = DATA_DIR / "reports"
MODELS_DIR      = BASE_DIR / "models"
FRONTEND_DIST   = BASE_DIR / "frontend" / "dist"
SETTINGS_FILE   = BASE_DIR / "settings.json"

for _d in [DATA_DIR, EMBEDDINGS_DIR, STUDENT_IMG_DIR, LOG_DIR, REPORT_DIR, MODELS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ── Load .env ──────────────────────────────────────────────────────────────────
load_dotenv(BASE_DIR / ".env")

# ── Secrets (from .env only — never in settings.json or git) ──────────────────
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
# int = USB webcam index, str = RTSP URL or folder path for test feed
CAMERAS = {
    "CAM-101": 1,
}

FRAME_WIDTH     = 1280
FRAME_HEIGHT    = 720
PROCESS_EVERY_N = 5
STREAM_FPS      = 10
USE_DSHOW       = False
IMAGE_FOLDER_DELAY = 2.0   # seconds per image in folder test feed

# ── RetinaFace detector ────────────────────────────────────────────────────────
DET_THRESH = 0.5

# ── ArcFace recognizer ─────────────────────────────────────────────────────────
# Genuine pairs score ~0.40–0.75. Raise if getting false matches.
REC_THRESHOLD          = 0.4
EMBEDDINGS_PER_STUDENT = 20
CONFIRM_FRAMES         = 3

# ── Preprocessing ──────────────────────────────────────────────────────────────
ENABLE_CLAHE     = True
CLAHE_CLIP_LIMIT = 2.5
CLAHE_TILE_SIZE  = (8, 8)
ENABLE_DENOISE   = True
SUPER_RES_SCALE  = 2

# ── School ────────────────────────────────────────────────────────────────────
SCHOOL_NAME        = "Narula Public School"
ADMIN_DISPLAY_NAME = "Administrator"

# ── Classes (shown in enrollment dropdown) ─────────────────────────────────────
CLASSES = [
    "6-A", "6-B",
    "7-A", "7-B",
    "8-A", "8-B",
    "9-A", "9-B",
    "10-A", "10-B",
    "11-Science", "11-Commerce", "11-Humanities",
    "12-Science", "12-Commerce", "12-Humanities",
]

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
LOG_FILE  = LOG_DIR / "attendance.log"

# ── Runtime settings management ───────────────────────────────────────────────
# Keys that can be changed via the Settings UI and are saved to settings.json.
# Secrets are never included here.
_RUNTIME_KEYS = {
    "REC_THRESHOLD", "DET_THRESH", "CONFIRM_FRAMES", "EMBEDDINGS_PER_STUDENT",
    "USE_DSHOW", "PROCESS_EVERY_N", "STREAM_FPS", "FRAME_WIDTH", "FRAME_HEIGHT",
    "ENABLE_CLAHE", "CLAHE_CLIP_LIMIT", "ENABLE_DENOISE", "SUPER_RES_SCALE",
    "SCHOOL_NAME", "ADMIN_DISPLAY_NAME", "CLASSES",
}

log = logging.getLogger(__name__)


def get_settings() -> dict:
    """Return all runtime-editable settings (no secrets)."""
    import sys
    module = sys.modules[__name__]
    result = {}
    for key in _RUNTIME_KEYS:
        val = getattr(module, key, None)
        if isinstance(val, list):
            result[key] = list(val)
        else:
            result[key] = val
    return result


def apply_settings(data: dict):
    """Apply a settings dict to this module's globals at runtime."""
    import sys
    module = sys.modules[__name__]
    for key, val in data.items():
        if key in _SECRETS:
            continue   # never overwrite secrets from settings.json
        if hasattr(module, key):
            if key == "CLASSES" and isinstance(val, list):
                CLASSES[:] = val
            else:
                setattr(module, key, val)


def save_settings(data: dict) -> bool:
    """Persist runtime settings to settings.json and apply immediately."""
    try:
        # Load existing, strip any secrets that snuck in
        current = {}
        if SETTINGS_FILE.exists():
            try:
                current = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                for k in _SECRETS:
                    current.pop(k, None)
            except Exception:
                current = {}

        # Merge new data (secrets stripped)
        safe = {k: v for k, v in data.items() if k not in _SECRETS and k in _RUNTIME_KEYS}
        current.update(safe)

        SETTINGS_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")
        apply_settings(current)
        return True
    except Exception as e:
        log.error("Failed to save settings: %s", e)
        return False


def load_settings():
    """Load settings.json overrides on startup. Called once at import."""
    if not SETTINGS_FILE.exists():
        return
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        # Strip secrets just in case they're in an old file
        for k in _SECRETS:
            data.pop(k, None)
        apply_settings(data)
        log.debug("Settings loaded from %s", SETTINGS_FILE)
    except Exception as e:
        log.warning("Could not load settings.json: %s — using defaults", e)


# Load on import
load_settings()
