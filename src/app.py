"""
FaceTrack AI — Flask application factory + all routes.
"""
import sys
import logging
import socket
import threading
import webbrowser
import re
import shutil
import base64
import zipfile
import io
from datetime import date, datetime
from functools import wraps
from pathlib import Path

from flask import Flask, Response, jsonify, request, session, send_from_directory
from flask_socketio import SocketIO, emit
from werkzeug.security import check_password_hash, generate_password_hash

import config
import database as db
from camera_processor import CameraManager
from face_engine import FaceEngine
from report_generator import generate_pdf_report, generate_excel_report
from utils import sort_classes

# ── Logging ───────────────────────────────────────────────────────────────────
_fmt = logging.Formatter("%(asctime)s [%(levelname)-8s] %(name)s: %(message)s")
try:
    _sh = logging.StreamHandler(open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1))
except Exception:
    _sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(_fmt)
_fh = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
_fh.setFormatter(_fmt)
logging.basicConfig(level=getattr(logging, config.LOG_LEVEL), handlers=[_sh, _fh])
log = logging.getLogger(__name__)

class _WFilter(logging.Filter):
    def filter(self, r): return "write() before start_response" not in r.getMessage()
logging.getLogger("werkzeug").addFilter(_WFilter())

socketio = SocketIO(
    async_mode="threading",
    cors_allowed_origins=config.CORS_ORIGINS,
    logger=False,
    engineio_logger=False,
    allow_upgrades=False
)

camera_manager: CameraManager = None   # type: ignore[assignment]
engine: FaceEngine = None               # type: ignore[assignment]

# ── Password hashing helpers ──────────────────────────────────────────────────
# Passwords in .env may be plaintext (legacy) or hashed (pbkdf2:sha256:...)
# We auto-detect and upgrade on first successful login.

def _is_hashed(pw: str) -> bool:
    return pw.startswith("pbkdf2:") or pw.startswith("scrypt:")


def _check_admin_password(password: str) -> bool:
    stored = config.ADMIN_PASSWORD
    if _is_hashed(stored):
        return check_password_hash(stored, password)
    # Legacy plaintext — check directly
    return password == stored


def _hash_and_upgrade_password(password: str):
    """Hash the admin password and persist it to .env on first login."""
    if _is_hashed(config.ADMIN_PASSWORD):
        return  # Already hashed
    hashed = generate_password_hash(password)
    env_path = config.BASE_DIR / ".env"
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    if "ADMIN_PASSWORD=" in text:
        text = re.sub(r"^ADMIN_PASSWORD=.*$", f"ADMIN_PASSWORD={hashed}",
                      text, flags=re.MULTILINE)
    else:
        text += f"\nADMIN_PASSWORD={hashed}\n"
    env_path.write_text(text, encoding="utf-8")
    config.ADMIN_PASSWORD = hashed
    log.info("Admin password has been hashed and persisted.")


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]; s.close(); return ip
    except Exception:
        return "localhost"


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY

    # Rate limiting
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address
        limiter = Limiter(
            get_remote_address,
            app=app,
            default_limits=[],
            storage_uri="memory://",
        )
    except ImportError:
        limiter = None
        log.warning("flask-limiter not installed — login rate limiting disabled.")

    socketio.init_app(app)
    _register_routes(app, limiter)
    return app


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify({"error": "Unauthorised"}), 401
        return f(*args, **kwargs)
    return decorated


def _get_username() -> str:
    """Get current session username for audit logging."""
    return session.get("username", "unknown")


def get_enrolled_count() -> int:
    try:
        return len(db.list_students())
    except Exception:
        return 0


def startup(app):
    global camera_manager, engine
    log.info("=" * 60)
    log.info("  FaceTrack AI — starting up")
    log.info("=" * 60)

    # Immediately hash plaintext passwords on startup
    _hash_and_upgrade_password(config.ADMIN_PASSWORD)

    db.init_db()
    db.ensure_default_sections(config.DEFAULT_CLASSES)

    for cam_id in config.CAMERAS:
        room_id = cam_id.replace("CAM-", "")
        db.upsert_classroom(room_id, cam_id, f"Room {room_id}")

    engine = FaceEngine()
    engine.load_known_faces()

    camera_manager = CameraManager(socketio=socketio)
    camera_manager.start_all()

    local_url = f"http://127.0.0.1:{config.PORT}"
    lan_url   = f"http://{get_local_ip()}:{config.PORT}"
    print(f"\n{'='*60}\n  FaceTrack AI is READY\n  Local : {local_url}"
          f"\n  LAN   : {lan_url}\n  User  : {config.ADMIN_USERNAME}"
          f"\n  Ctrl+C to stop\n{'='*60}\n", flush=True)

    threading.Timer(2.0, lambda: webbrowser.open(local_url)).start()


def _serve_spa():
    dist = config.FRONTEND_DIST
    if not (dist / "index.html").exists():
        return ("<h2>Frontend not built.</h2><p>Run: cd frontend && npm install && npm run build</p>", 503)
    return send_from_directory(str(dist), "index.html")


# ── Blank JPEG for snapshot fallback ──────────────────────────────────────────
_BLANK_JPEG = base64.b64decode(
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof"
    "Hh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAHwAA"
    "AQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQR"
    "BRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RF"
    "RkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ip"
    "qrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/9oACAEB"
    "AAA/APvSiigD/9k="
)


def _register_routes(app: Flask, limiter=None):

    # ── Auth ───────────────────────────────────────────────────────────────────
    @app.route("/api/auth/status")
    def api_auth_status():
        if session.get("logged_in"):
            return jsonify({"logged_in": True, "username": session.get("username", ""),
                            "enrolled": get_enrolled_count()})
        return jsonify({"logged_in": False, "enrolled": 0})

    def _conditionally_limit(limit_string):
        def decorator(f):
            if limiter:
                return limiter.limit(limit_string)(f)
            return f
        return decorator

    @app.route("/login", methods=["POST"])
    @_conditionally_limit(config.RATE_LIMIT_LOGIN)
    def login_post():
        if request.is_json:
            data = request.json or {}
            username, password = data.get("username","").strip(), data.get("password","")
        else:
            username = request.form.get("username","").strip()
            password = request.form.get("password","")
        if username == config.ADMIN_USERNAME and _check_admin_password(password):
            session["logged_in"] = True; session["username"] = username
            # Auto-upgrade plaintext password to hashed on first successful login
            _hash_and_upgrade_password(password)
            db.log_audit("LOGIN", f"Admin login from {request.remote_addr}", username)
            return jsonify({"ok": True})
        db.log_audit("LOGIN_FAILED", f"Failed login attempt for '{username}' from {request.remote_addr}")
        return jsonify({"ok": False, "error": "Invalid username or password."}), 401

    @app.route("/logout")
    def logout():
        user = _get_username()
        session.clear()
        db.log_audit("LOGOUT", "", user)
        return jsonify({"ok": True})

    # ── Snapshot / stream ──────────────────────────────────────────────────────
    @app.route("/snapshot/<camera_id>")
    @login_required
    def snapshot(camera_id):
        jpg = camera_manager.get_jpeg(camera_id) if camera_manager else b""
        if not jpg:
            return Response(_BLANK_JPEG, mimetype="image/jpeg")
        return Response(jpg, mimetype="image/jpeg")

    @app.route("/stream/<camera_id>")
    @login_required
    def stream(camera_id):
        import time
        def generate():
            while True:
                jpg = camera_manager.get_jpeg(camera_id)
                if jpg:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n"
                time.sleep(1 / max(1, config.STREAM_FPS))
        return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

    # ── Stats ──────────────────────────────────────────────────────────────────
    @app.route("/api/stats")
    @login_required
    def api_stats():
        today = date.today().isoformat()
        return jsonify({"daily": db.get_daily_stats(today),
                        "cameras": camera_manager.get_stats() if camera_manager else {},
                        "enrolled": get_enrolled_count()})

    # ── Attendance ─────────────────────────────────────────────────────────────
    @app.route("/api/attendance")
    @login_required
    def api_attendance():
        target  = request.args.get("date", date.today().isoformat())
        cls     = request.args.get("class")   or None
        stream  = request.args.get("stream")  or None
        section = request.args.get("section") or None
        return jsonify(db.get_attendance_by_date(target, cls, stream, section))

    @app.route("/api/attendance/clear", methods=["DELETE"])
    @login_required
    def api_clear_attendance():
        target = request.args.get("date", date.today().isoformat())
        if db.clear_attendance_by_date(target):
            db.log_audit("CLEAR_ATTENDANCE", f"Cleared attendance for {target}", _get_username())
            return jsonify({"ok": True})
        return jsonify({"error": "Failed to clear attendance"}), 500

    @app.route("/api/attendance/clear_all", methods=["DELETE"])
    @login_required
    def api_clear_all_attendance():
        if db.clear_all_attendance():
            db.log_audit("CLEAR_ALL_ATTENDANCE", "Cleared all attendance records", _get_username())
            return jsonify({"ok": True})
        return jsonify({"error": "Failed to clear attendance"}), 500

    # ── Students ───────────────────────────────────────────────────────────────
    @app.route("/api/students")
    @login_required
    def api_students():
        cls     = request.args.get("class")   or None
        stream  = request.args.get("stream")  or None
        section = request.args.get("section") or None
        return jsonify(db.list_students(cls, stream, section))

    @app.route("/api/students/<student_id>", methods=["DELETE"])
    @login_required
    def api_delete_student(student_id):
        student = db.get_student(student_id)
        db.delete_student(student_id)
        if engine: engine.remove_student(student_id)
        db.log_audit("DELETE_STUDENT",
                     f"Deleted {student['name'] if student else student_id} ({student_id})",
                     _get_username())
        return jsonify({"ok": True})

    @app.route("/api/enroll", methods=["POST"])
    @login_required
    def api_enroll():
        from enroll import enroll_student
        import tempfile

        sid        = request.form.get("student_id", "").strip()
        name       = request.form.get("name",       "").strip()
        class_name = request.form.get("class_name", "").strip()
        stream     = request.form.get("stream",     "").strip()
        section    = request.form.get("section",    "").strip().upper()
        roll_no    = int(request.form.get("roll_no", 0) or 0)

        if not all([sid, name, class_name, section]):
            return jsonify({"error": "student_id, name, class_name, section required"}), 400

        # For stream classes, stream is required
        if class_name in config.STREAM_CLASSES and not stream:
            return jsonify({"error": f"Stream is required for Class {class_name}"}), 400

        existing = db.get_student(sid)
        if existing:
            return jsonify({"error":
                f"Student ID '{sid}' already enrolled "
                f"({existing['name']}, Class {existing['class_name']} "
                f"{'/ ' + existing['stream'] + ' ' if existing.get('stream') else ''}"
                f"Sec {existing['section']}). Remove first."}), 409

        # Roll uniqueness: class + stream + section
        if roll_no > 0:
            dupe = next((s for s in db.list_students(class_name, stream or None, section)
                         if s["roll_no"] == roll_no), None)
            if dupe:
                return jsonify({"error":
                    f"Roll No. {roll_no} already taken by "
                    f"{dupe['name']} ({dupe['student_id']}) "
                    f"in Class {class_name}"
                    f"{' / ' + stream if stream else ''} Sec {section}."}), 409

        files = request.files.getlist("photos")
        if not files:
            return jsonify({"error": "No photos uploaded"}), 400

        tmpdir = Path(tempfile.mkdtemp())
        try:
            paths = []
            for f in files:
                dest = tmpdir / (f.filename or "photo.jpg")
                f.save(str(dest)); paths.append(str(dest))
            ok = enroll_student(student_id=sid, name=name, class_name=class_name,
                                section=section, roll_no=roll_no, image_paths=paths,
                                stream=stream)
            if ok:
                db.log_audit("ENROLL_STUDENT",
                             f"Enrolled {name} ({sid}) Class {class_name}", _get_username())
                return jsonify({"ok": True, "student_id": sid})
            return jsonify({"error": "No face detected in uploaded images"}), 422
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ── Cameras ────────────────────────────────────────────────────────────────
    @app.route("/api/cameras")
    @login_required
    def api_cameras():
        return jsonify(camera_manager.get_stats() if camera_manager else {})

    @app.route("/api/cameras/<camera_id>/start", methods=["POST"])
    @login_required
    def api_start_camera(camera_id):
        source = config.CAMERAS.get(camera_id)
        if source is None: return jsonify({"error": "Unknown camera"}), 404
        camera_manager.start_camera(camera_id, source)
        return jsonify({"ok": True})

    @app.route("/api/cameras/<camera_id>/stop", methods=["POST"])
    @login_required
    def api_stop_camera(camera_id):
        if camera_id not in config.CAMERAS: return jsonify({"error": "Unknown camera"}), 404
        camera_manager.stop_camera(camera_id); return jsonify({"ok": True})

    @app.route("/api/cameras/<camera_id>/restart", methods=["POST"])
    @login_required
    def api_restart_camera(camera_id):
        source = config.CAMERAS.get(camera_id)
        if source is None: return jsonify({"error": "Unknown camera"}), 404
        camera_manager.start_camera(camera_id, source); return jsonify({"ok": True})

    @app.route("/api/cameras/<camera_id>/recognition", methods=["POST"])
    @login_required
    def api_toggle_recognition(camera_id):
        enabled = bool((request.json or {}).get("enabled", False))
        if camera_manager.set_recognition(camera_id, enabled):
            return jsonify({"ok": True, "enabled": enabled})
        return jsonify({"error": "Camera not running"}), 404

    @app.route("/api/push_frame/<camera_id>", methods=["POST"])
    def api_push_frame(camera_id):
        """
        Accept a raw JPEG frame pushed from a browser client.

        Designed for Google Colab where the backend VM has no physical camera.
        A JavaScript snippet in the Colab notebook captures the browser webcam
        and POSTs each frame here as application/octet-stream.  The frame is
        forwarded to the PushCameraProcessor queue, which runs face detection
        and recognition on the Colab GPU — exactly like the live camera path.

        No @login_required: the endpoint is ephemeral (random Cloudflare URL)
        and is never reachable on the local PC (push:// cameras are only
        configured inside the Colab notebook).
        """
        data = request.data
        if not data and "frame" in request.files:
            data = request.files["frame"].read()
        if not data:
            return jsonify({"error": "No frame data"}), 400
        if camera_manager:
            if camera_manager.push_frame(camera_id, data):
                return jsonify({"ok": True}), 200
            return jsonify({"error": "Camera not found or not a push camera"}), 404
        return jsonify({"error": "Camera manager not ready"}), 503

    @app.route("/api/preview_frame/<camera_id>", methods=["POST"])
    @login_required
    def api_preview_frame(camera_id):
        """
        Accept a raw JPEG frame, run inline GPU face detection/identification,
        and return JSON bounding-box data for the Live Cameras overlay.

        Also pushes the frame to PushCameraProcessor (if present) so that
        the confirmation buffer runs in the background for attendance marking.
        ONNX Runtime's InferenceSession is thread-safe, so concurrent calls
        from this route and the processor thread are safe.
        """
        import time as _t, numpy as _np, cv2 as _cv2

        data = request.data
        if not data:
            return jsonify({"error": "No frame data"}), 400

        # Push to queue for attendance marking (non-blocking)
        if camera_manager:
            camera_manager.push_frame(camera_id, data)

        # Inline detection for immediate visual feedback
        if engine is None:
            return jsonify({"faces": [], "inference_ms": 0})

        arr   = _np.frombuffer(data, _np.uint8)
        frame = _cv2.imdecode(arr, _cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({"error": "Bad frame data"}), 400

        t0    = _t.monotonic()
        faces = engine.detect(frame)
        face_data = []
        for face in faces:
            sid, sim = engine.identify(face)
            name = engine.get_student_name(sid) if sid else None
            x, y, w, h = face.bbox.astype(int).tolist()
            face_data.append({
                "bbox":       [x, y, w, h],
                "name":       name or "Unknown",
                "similarity": round(float(sim), 3),
                "known":      sid is not None,
            })
        inference_ms = round((_t.monotonic() - t0) * 1000)

        return jsonify({"faces": face_data, "inference_ms": inference_ms})

    # ── Classes ────────────────────────────────────────────────────────────────
    @app.route("/api/classes", methods=["GET"])
    @login_required
    def api_get_classes():
        return jsonify(db.list_classes())

    @app.route("/api/classes", methods=["POST"])
    @login_required
    def api_add_class():
        name = (request.json or {}).get("name", "").strip()
        if not name: return jsonify({"error": "Class name required"}), 400
        db.ensure_default_sections([name])
        db.log_audit("ADD_CLASS", f"Added class {name}", _get_username())
        return jsonify({"ok": True})

    @app.route("/api/classes/<path:class_name>", methods=["DELETE"])
    @login_required
    def api_delete_class(class_name):
        if db.delete_class_sections(class_name):
            db.log_audit("DELETE_CLASS", f"Deleted class {class_name}", _get_username())
            return jsonify({"ok": True})
        return jsonify({"error": "Failed to delete class"}), 500

    # ── Sections ───────────────────────────────────────────────────────────────
    @app.route("/api/sections", methods=["GET"])
    @login_required
    def api_get_sections():
        cls    = request.args.get("class",  "").strip()
        stream = request.args.get("stream", "").strip()
        if not cls: return jsonify([])
        return jsonify(db.list_sections(cls, stream))

    @app.route("/api/sections", methods=["POST"])
    @login_required
    def api_add_section():
        data    = request.json or {}
        cls     = data.get("class_name", "").strip()
        stream  = data.get("stream",     "").strip()
        section = data.get("section",    "").strip().upper()
        if not cls or not section: return jsonify({"error": "class_name and section required"}), 400
        db.add_section(cls, section, stream)
        return jsonify({"ok": True})

    @app.route("/api/sections/<class_name>/<stream>/<section>", methods=["DELETE"])
    @login_required
    def api_delete_section(class_name, stream, section):
        actual_stream = "" if stream == "__none__" else stream
        enrolled = db.list_students(class_name, actual_stream if actual_stream else None, section)
        if enrolled:
            return jsonify({"error":
                f"Cannot remove: {len(enrolled)} student(s) enrolled. Remove them first."}), 409
        db.remove_section(class_name, section, actual_stream)
        return jsonify({"ok": True})

    # ── Streams (read-only — fixed in config) ──────────────────────────────────
    @app.route("/api/streams")
    @login_required
    def api_streams():
        cls = request.args.get("class", "").strip()
        if cls in config.STREAM_CLASSES:
            return jsonify(config.STREAMS)
        return jsonify([])

    # ── Classrooms ─────────────────────────────────────────────────────────────
    @app.route("/api/classrooms", methods=["GET"])
    @login_required
    def api_classrooms():
        return jsonify(db.list_classrooms())

    @app.route("/api/classrooms/<classroom_id>", methods=["POST"])
    @login_required
    def api_update_classroom(classroom_id):
        data = request.json or {}
        db.upsert_classroom(classroom_id, data.get("camera_id",""),
                            data.get("class_name",""), int(data.get("floor",1)))
        return jsonify({"ok": True})

    # ── Reports ────────────────────────────────────────────────────────────────
    @app.route("/reports/pdf")
    @login_required
    def report_pdf():
        d       = request.args.get("date", date.today().isoformat())
        cls     = request.args.get("class")   or None
        stream  = request.args.get("stream")  or None
        section = request.args.get("section") or None
        p = generate_pdf_report(d, cls, stream, section)
        return send_from_directory(config.REPORT_DIR, Path(p).name, as_attachment=True)

    @app.route("/reports/excel")
    @login_required
    def report_excel():
        d       = request.args.get("date", date.today().isoformat())
        cls     = request.args.get("class")   or None
        stream  = request.args.get("stream")  or None
        section = request.args.get("section") or None
        p = generate_excel_report(d, cls, stream, section)
        return send_from_directory(config.REPORT_DIR, Path(p).name, as_attachment=True)

    # ── Settings ───────────────────────────────────────────────────────────────
    @app.route("/api/settings", methods=["GET"])
    @login_required
    def api_get_settings():
        return jsonify(config.get_settings())

    @app.route("/api/settings", methods=["POST"])
    @login_required
    def api_save_settings():
        data = request.json or {}
        if config.save_settings(data):
            db.log_audit("SAVE_SETTINGS", "Settings updated", _get_username())
            return jsonify({"ok": True})
        return jsonify({"error": "Failed to save"}), 500

    @app.route("/api/settings/password", methods=["POST"])
    @login_required
    def api_change_password():
        pwd = (request.json or {}).get("password", "").strip()
        if len(pwd) < 6: return jsonify({"error": "Minimum 6 characters"}), 400
        try:
            hashed = generate_password_hash(pwd)
            env_path = config.BASE_DIR / ".env"
            text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
            if "ADMIN_PASSWORD=" in text:
                text = re.sub(r"^ADMIN_PASSWORD=.*$", f"ADMIN_PASSWORD={hashed}",
                              text, flags=re.MULTILINE)
            else:
                text += f"\nADMIN_PASSWORD={hashed}\n"
            env_path.write_text(text, encoding="utf-8")
            config.ADMIN_PASSWORD = hashed
            db.log_audit("CHANGE_PASSWORD", "Admin password changed", _get_username())
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Audit log ──────────────────────────────────────────────────────────────
    @app.route("/api/audit")
    @login_required
    def api_audit_log():
        limit = int(request.args.get("limit", 100))
        return jsonify(db.get_audit_log(limit))

    # ── Backup & Restore ────────────────────────────────────────────────────────
    @app.route("/api/backup/create", methods=["POST"])
    @login_required
    def api_backup_create():
        """Create a timestamped zip of all data and return it as a download."""
        try:
            ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
            name = f"facetrack_backup_{ts}.zip"
            buf  = io.BytesIO()

            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                # Database
                if config.DB_PATH.exists():
                    zf.write(config.DB_PATH, "data/attendance.db")
                # Embeddings
                for f in config.EMBEDDINGS_DIR.rglob("*"):
                    if f.is_file():
                        zf.write(f, f"data/embeddings/{f.name}")
                # Student photos
                for f in config.STUDENT_IMG_DIR.rglob("*"):
                    if f.is_file():
                        rel = f.relative_to(config.STUDENT_IMG_DIR)
                        zf.write(f, f"data/student_photos/{rel}")
                # Settings
                if config.SETTINGS_FILE.exists():
                    zf.write(config.SETTINGS_FILE, "settings.json")
                # Manifest
                zf.writestr("BACKUP_MANIFEST.txt",
                    f"FaceTrack AI Backup\nCreated: {ts}\nVersion: 1.0\n")

            buf.seek(0)
            db.log_audit("BACKUP_CREATE", f"Backup created: {name}", _get_username())
            return Response(
                buf.read(),
                mimetype="application/zip",
                headers={"Content-Disposition": f'attachment; filename="{name}"'},
            )
        except Exception as e:
            log.error("Backup creation failed: %s", e)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/backup/restore", methods=["POST"])
    @login_required
    def api_backup_restore():
        """Restore data from an uploaded backup zip, then auto-restart cameras."""
        if "backup" not in request.files:
            return jsonify({"error": "No file provided"}), 400
        f = request.files["backup"]
        if not f.filename.endswith(".zip"):
            return jsonify({"error": "File must be a .zip backup"}), 400
        try:
            data = f.read()
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = zf.namelist()
                # Validate — must contain the manifest
                if "BACKUP_MANIFEST.txt" not in names:
                    return jsonify({"error": "Invalid backup file — missing manifest"}), 400

                # Stop cameras before touching files
                if camera_manager:
                    camera_manager.stop_all()

                # Restore database
                if "data/attendance.db" in names:
                    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
                    config.DB_PATH.write_bytes(zf.read("data/attendance.db"))

                # Restore embeddings
                shutil.rmtree(config.EMBEDDINGS_DIR, ignore_errors=True)
                config.EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)
                for entry in names:
                    if entry.startswith("data/embeddings/") and not entry.endswith("/"):
                        dest = config.EMBEDDINGS_DIR / Path(entry).name
                        dest.write_bytes(zf.read(entry))

                # Restore student photos
                shutil.rmtree(config.STUDENT_IMG_DIR, ignore_errors=True)
                config.STUDENT_IMG_DIR.mkdir(parents=True, exist_ok=True)
                for entry in names:
                    if entry.startswith("data/student_photos/") and not entry.endswith("/"):
                        # Preserve sub-folder structure
                        rel  = entry[len("data/student_photos/"):]
                        dest = config.STUDENT_IMG_DIR / rel
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(zf.read(entry))

                # Restore settings
                if "settings.json" in names:
                    config.SETTINGS_FILE.write_bytes(zf.read("settings.json"))
                    config.load_settings()

            # Reload face embeddings into memory
            if engine:
                engine.load_known_faces()

            # Auto-restart cameras (Option A)
            if camera_manager:
                camera_manager.start_all()

            db.log_audit("BACKUP_RESTORE", f"Backup restored: {f.filename}", _get_username())
            return jsonify({"ok": True, "message": "Backup restored. Cameras restarted."})
        except zipfile.BadZipFile:
            return jsonify({"error": "Corrupt or invalid zip file"}), 400
        except Exception as e:
            log.error("Backup restore failed: %s", e)
            return jsonify({"error": str(e)}), 500

    # ── Reset ──────────────────────────────────────────────────────────────────
    @app.route("/api/reset_all", methods=["DELETE"])
    @login_required
    def api_reset_all():
        try:
            db.reset_all_data()
            shutil.rmtree(config.EMBEDDINGS_DIR, ignore_errors=True)
            config.EMBEDDINGS_DIR.mkdir(exist_ok=True)
            if engine: engine.load_known_faces()
            db.log_audit("RESET_ALL", "Full system reset — all data cleared", _get_username())
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── SocketIO ───────────────────────────────────────────────────────────────
    @socketio.on("connect")
    def on_connect(): emit("connected", {"status": "ok"})

    @socketio.on("disconnect")
    def on_disconnect(): pass

    # ── Frontend ───────────────────────────────────────────────────────────────
    @app.route("/assets/<path:filename>")
    def frontend_assets(filename):
        return send_from_directory(str(config.FRONTEND_DIST / "assets"), filename)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def spa(path):
        return _serve_spa()
