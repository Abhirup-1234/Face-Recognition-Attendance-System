"""
FaceTrack AI — Configuration
Classes are managed entirely in the database (class_sections table).
They are no longer stored in settings.json.
"""
import os
import json
import secrets
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
BACKUP_DIR      = DATA_DIR / "backups"
FRONTEND_DIST   = BASE_DIR / "frontend" / "dist"
SETTINGS_FILE   = BASE_DIR / "settings.json"

# Only directories that must always exist (models dir removed — InsightFace
# downloads its own models to ~/.insightface automatically)
for _d in [DATA_DIR, EMBEDDINGS_DIR, STUDENT_IMG_DIR, LOG_DIR, REPORT_DIR, BACKUP_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ── Load .env ──────────────────────────────────────────────────────────────────
# Override ambient OS/user environment variables so the project's .env remains
# the source of truth for app credentials/settings.
load_dotenv(BASE_DIR / ".env", override=True)


def _ensure_secret_key() -> str:
    """Generate a strong SECRET_KEY and persist it to .env if missing.
    Also ensures default admin credentials are in the file for new users."""
    env_path = BASE_DIR / ".env"
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    changed = False

    key = os.getenv("SECRET_KEY", "").strip()
    if not key or key == "key":
        key = secrets.token_hex(32)
        if "SECRET_KEY=" in text:
            import re
            text = re.sub(r"^SECRET_KEY=.*$", f"SECRET_KEY={key}", text, flags=re.MULTILINE)
        else:
            text += f"\nSECRET_KEY={key}\n"
        os.environ["SECRET_KEY"] = key
        changed = True

    if "ADMIN_USERNAME=" not in text:
        text += "ADMIN_USERNAME=admin\n"
        changed = True
    if "ADMIN_PASSWORD=" not in text:
        text += "ADMIN_PASSWORD=admin123\n"
        changed = True

    if changed:
        env_path.write_text(text.strip() + "\n", encoding="utf-8")
        
    return key


# ── Secrets ────────────────────────────────────────────────────────────────────
SECRET_KEY     = _ensure_secret_key()
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
_SECRETS = {"SECRET_KEY", "ADMIN_USERNAME", "ADMIN_PASSWORD"}

# ── Flask ──────────────────────────────────────────────────────────────────────
DEBUG      = False
HOST       = "0.0.0.0"
PORT       = 5000
ASYNC_MODE = "threading"

# ── CORS / Security ───────────────────────────────────────────────────────────
# For a local school server, allow localhost and LAN origins
CORS_ORIGINS = [
    f"http://127.0.0.1:{PORT}",
    f"http://localhost:{PORT}",
]

# Rate limiting
RATE_LIMIT_LOGIN = "5/minute"

# ── Cameras ────────────────────────────────────────────────────────────────────
CAMERAS = {
        "CAM-101": 1,
        # "ACTORS": "testvid2.mp4"
        # "HARRY POTTER": "C:/Users/Abhirup/Desktop/Dataset/Harry Potter/Testing"
    }
FRAME_WIDTH        = 1280
FRAME_HEIGHT       = 720
PROCESS_EVERY_N    = 5
STREAM_FPS         = 10
USE_DSHOW          = False
IMAGE_FOLDER_DELAY = 3.0

# ── RetinaFace / ArcFace ───────────────────────────────────────────────────────
DET_THRESH             = 0.5
REC_THRESHOLD          = 0.4
EMBEDDINGS_PER_STUDENT = 20
CONFIRM_FRAMES         = 3

# ── Inference Provider (OpenVINO) ──────────────────────────────────────────────
# NOTE: GPU (Intel iGPU) has been disabled.
# The buffalo_l (RetinaFace + ArcFace) ONNX models trigger two known OpenVINO
# GPU-backend kernel errors:
#   • "Input VX intersects with VY" — register-allocation bug in CISA GPU backend
#   • "Explicit input N must not follow an implicit input 0" — I/O ordering bug
# These cause silent GPU→CPU fallback with extra overhead, making GPU SLOWER than
# plain CPU. OpenVINO CPU (with AVX/VNNI optimisations) outperforms ONNX CPU
# and is the correct backend for this hardware.
OPENVINO_DEVICE_PRIORITY = ["CPU"]   # GPU removed — kernel errors on buffalo_l
# 0 = auto (use all available cores); set >0 to reserve cores for Flask/cameras
OPENVINO_NUM_THREADS     = 0
# Enable OpenVINO model caching — speeds up subsequent launches dramatically
OPENVINO_CACHE_DIR       = str(DATA_DIR / "openvino_cache")

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
