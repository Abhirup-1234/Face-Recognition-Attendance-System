"""
FaceTrack AI — Flask application factory + all routes.
"""
import sys
import logging
import socket
import threading
import webbrowser
import re
from datetime import date
from functools import wraps
from pathlib import Path

from flask import Flask, Response, jsonify, request, session, redirect, send_from_directory
from flask_socketio import SocketIO, emit

import config
import database as db
from camera_processor import CameraManager
from face_engine import FaceEngine
from report_generator import generate_pdf_report, generate_excel_report

# ── Logging ───────────────────────────────────────────────────────────────────
_fmt = logging.Formatter("%(asctime)s [%(levelname)-8s] %(name)s: %(message)s")
try:
    _sh = logging.StreamHandler(
        open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)
    )
except Exception:
    _sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(_fmt)
_fh = logging.FileHandler(config.LOG_FILE, encoding="utf-8")
_fh.setFormatter(_fmt)
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    handlers=[_sh, _fh]
)
log = logging.getLogger(__name__)

# Suppress werkzeug noise
class _WFilter(logging.Filter):
    def filter(self, r):
        return "write() before start_response" not in r.getMessage()
logging.getLogger("werkzeug").addFilter(_WFilter())

# ── SocketIO (module-level so run.py can import it) ───────────────────────────
socketio = SocketIO(
    async_mode="threading",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)

# ── Module-level state ────────────────────────────────────────────────────────
camera_manager: CameraManager = None
engine: FaceEngine = None


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


# ── Class sorting helper ──────────────────────────────────────────────────────
def sort_classes(classes):
    import re as _re
    STREAM_ORDER = {"science": 0, "commerce": 1, "humanities": 2}
    def key(cls):
        parts = _re.split(r'[-\s]', cls.strip(), maxsplit=1)
        try:    num = int(parts[0])
        except: num = 999
        rest = parts[1] if len(parts) > 1 else ""
        rest_lower = rest.lower()
        stream_rank, section = 99, rest
        for stream, rank in STREAM_ORDER.items():
            if stream in rest_lower:
                stream_rank = rank
                section = _re.sub(stream, "", rest_lower, flags=_re.IGNORECASE).strip("-_ ")
                break
        return (num, stream_rank, section.upper())
    return sorted(classes, key=key)


# ── App factory ───────────────────────────────────────────────────────────────
def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    socketio.init_app(app)
    _register_routes(app)
    return app


# ── Auth helper ───────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify({"error": "Unauthorised"}), 401
        return f(*args, **kwargs)
    return decorated


def get_enrolled_count() -> int:
    try:
        return len(db.list_students())
    except Exception:
        return 0


# ── Startup ───────────────────────────────────────────────────────────────────
def startup(app):
    global camera_manager, engine
    log.info("=" * 60)
    log.info("  FaceTrack AI — starting up")
    log.info("=" * 60)
    log.info("Settings loaded from %s", config.SETTINGS_FILE)

    db.init_db()

    for cam_id in config.CAMERAS:
        room_id = cam_id.replace("CAM-", "")
        db.upsert_classroom(room_id, cam_id, f"Room {room_id}")

    engine = FaceEngine()
    engine.load_known_faces()

    camera_manager = CameraManager(socketio=socketio)
    camera_manager.start_all()

    local_url = f"http://127.0.0.1:{config.PORT}"
    lan_url   = f"http://{get_local_ip()}:{config.PORT}"

    print("", flush=True)
    print("=" * 60, flush=True)
    print("  FaceTrack AI is READY",          flush=True)
    print(f"  This computer : {local_url}",   flush=True)
    print(f"  Other devices : {lan_url}",     flush=True)
    print(f"  Username      : {config.ADMIN_USERNAME}", flush=True)
    print(f"  Password      : {config.ADMIN_PASSWORD}", flush=True)
    print("  Press Ctrl+C to stop",           flush=True)
    print("=" * 60, flush=True)
    print("", flush=True)

    threading.Timer(2.0, lambda: webbrowser.open(local_url)).start()


# ── SPA serving ───────────────────────────────────────────────────────────────
def _serve_spa():
    dist = config.FRONTEND_DIST
    if not (dist / "index.html").exists():
        return (
            "<h2>Frontend not built yet.</h2>"
            "<p>Run: <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code></p>",
            503,
        )
    return send_from_directory(str(dist), "index.html")


# ── Route registration ────────────────────────────────────────────────────────
def _register_routes(app: Flask):

    # ── Auth ──────────────────────────────────────────────────────────────────
    @app.route("/api/auth/status")
    def api_auth_status():
        if session.get("logged_in"):
            return jsonify({
                "logged_in": True,
                "username":  session.get("username", ""),
                "enrolled":  get_enrolled_count(),
            })
        return jsonify({"logged_in": False, "enrolled": 0})

    @app.route("/login", methods=["POST"])
    def login_post():
        # Accept both form-encoded (browser default) and JSON
        if request.is_json:
            data     = request.json or {}
            username = data.get("username", "").strip()
            password = data.get("password", "")
        else:
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

        if username == config.ADMIN_USERNAME and password == config.ADMIN_PASSWORD:
            session["logged_in"] = True
            session["username"]  = username
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "Invalid username or password."}), 401

    @app.route("/logout")
    def logout():
        session.clear()
        return jsonify({"ok": True})

    # ── Snapshot (single JPEG — avoids Chrome loading spinner) ────────────────
    @app.route("/snapshot/<camera_id>")
    @login_required
    def snapshot(camera_id: str):
        jpg = camera_manager.get_jpeg(camera_id) if camera_manager else b""
        if not jpg:
            import base64
            blank = base64.b64decode(
                "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoH"
                "BwYIDAoMCwsKCwsNCxAQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/wAAR"
                "CAABAAEDASIA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAA"
                "AAAAAAAP/xAAUAQEAAAAAAAAAAAAAAAAAAAAA/8QAFBEBAAAAAAAAAAAAAAAA"
                "AAAA/9oADAMBAAIRAxEAPwCwABmX/9k="
            )
            return Response(blank, mimetype="image/jpeg")
        return Response(jpg, mimetype="image/jpeg")

    # ── MJPEG stream (kept for compatibility) ──────────────────────────────────
    @app.route("/stream/<camera_id>")
    @login_required
    def stream(camera_id: str):
        def generate():
            import time
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
        return jsonify({
            "daily":    db.get_daily_stats(today),
            "cameras":  camera_manager.get_stats() if camera_manager else {},
            "enrolled": get_enrolled_count(),
        })

    # ── Attendance ─────────────────────────────────────────────────────────────
    @app.route("/api/attendance")
    @login_required
    def api_attendance():
        target = request.args.get("date", date.today().isoformat())
        cls    = request.args.get("class") or None
        return jsonify(db.get_attendance_by_date(target, cls))

    @app.route("/api/attendance/clear", methods=["DELETE"])
    @login_required
    def api_clear_attendance():
        import sqlite3
        target = request.args.get("date", date.today().isoformat())
        try:
            conn = sqlite3.connect(config.DB_PATH)
            conn.execute("DELETE FROM attendance WHERE date=?", (target,))
            conn.commit(); conn.close()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/attendance/clear_all", methods=["DELETE"])
    @login_required
    def api_clear_all_attendance():
        import sqlite3
        try:
            conn = sqlite3.connect(config.DB_PATH)
            conn.execute("DELETE FROM attendance")
            conn.commit(); conn.close()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Students ───────────────────────────────────────────────────────────────
    @app.route("/api/students")
    @login_required
    def api_students():
        return jsonify(db.list_students(request.args.get("class")))

    @app.route("/api/students/<student_id>", methods=["DELETE"])
    @login_required
    def api_delete_student(student_id: str):
        db.delete_student(student_id)
        if engine:
            engine.remove_student(student_id)
        return jsonify({"ok": True})

    @app.route("/api/enroll", methods=["POST"])
    @login_required
    def api_enroll():
        from enroll import enroll_student
        import tempfile, shutil

        sid        = request.form.get("student_id", "").strip()
        name       = request.form.get("name", "").strip()
        class_name = request.form.get("class_name", "").strip()
        section    = request.form.get("section", "").strip()
        roll_no    = int(request.form.get("roll_no", 0) or 0)

        if not all([sid, name, class_name]):
            return jsonify({"error": "student_id, name, class_name required"}), 400

        # Duplicate checks
        existing = db.get_student(sid)
        if existing:
            return jsonify({
                "error": f"Student ID '{sid}' is already enrolled "
                         f"({existing['name']}, {existing['class_name']}). "
                         f"Remove the existing student first."
            }), 409

        if roll_no > 0:
            dupe = next((
                s for s in db.list_students()
                if s["class_name"] == class_name
                and s["section"].upper() == section.upper()
                and s["roll_no"] == roll_no
            ), None)
            if dupe:
                return jsonify({
                    "error": f"Roll No. {roll_no} in {class_name}-{section} is already "
                             f"taken by {dupe['name']} ({dupe['student_id']})."
                }), 409

        files = request.files.getlist("photos")
        if not files:
            return jsonify({"error": "No photos uploaded"}), 400

        tmpdir = Path(tempfile.mkdtemp())
        try:
            paths = []
            for f in files:
                dest = tmpdir / (f.filename or "photo.jpg")
                f.save(str(dest))
                paths.append(str(dest))

            ok = enroll_student(
                student_id=sid, name=name, class_name=class_name,
                section=section, roll_no=roll_no, image_paths=paths,
            )
            if ok:
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
    def api_start_camera(camera_id: str):
        source = config.CAMERAS.get(camera_id)
        if source is None:
            return jsonify({"error": "Unknown camera"}), 404
        stats = camera_manager.get_stats()
        if camera_id in stats and stats[camera_id]["status"] == "running":
            return jsonify({"ok": True, "message": "Already running"})
        camera_manager.start_camera(camera_id, source)
        return jsonify({"ok": True})

    @app.route("/api/cameras/<camera_id>/stop", methods=["POST"])
    @login_required
    def api_stop_camera(camera_id: str):
        if camera_id not in config.CAMERAS:
            return jsonify({"error": "Unknown camera"}), 404
        camera_manager.stop_camera(camera_id)
        return jsonify({"ok": True})

    @app.route("/api/cameras/<camera_id>/restart", methods=["POST"])
    @login_required
    def api_restart_camera(camera_id: str):
        source = config.CAMERAS.get(camera_id)
        if source is None:
            return jsonify({"error": "Unknown camera"}), 404
        camera_manager.start_camera(camera_id, source)
        return jsonify({"ok": True})

    # ── Classes ────────────────────────────────────────────────────────────────
    @app.route("/api/classes", methods=["GET"])
    @login_required
    def api_get_classes():
        students   = db.list_students()
        db_classes = {s["class_name"] for s in students}
        return jsonify(sort_classes(set(config.CLASSES) | db_classes))

    @app.route("/api/classes", methods=["POST"])
    @login_required
    def api_add_class():
        name = (request.json or {}).get("name", "").strip()
        if not name:
            return jsonify({"error": "Class name required"}), 400
        if name not in config.CLASSES:
            config.CLASSES.append(name)
            config.CLASSES[:] = sort_classes(config.CLASSES)
            config.save_settings({"CLASSES": config.CLASSES})
        return jsonify({"ok": True})

    @app.route("/api/classes/<path:class_name>", methods=["DELETE"])
    @login_required
    def api_delete_class(class_name: str):
        if class_name in config.CLASSES:
            config.CLASSES.remove(class_name)
            config.save_settings({"CLASSES": config.CLASSES})
        return jsonify({"ok": True})

    # ── Classrooms ─────────────────────────────────────────────────────────────
    @app.route("/api/classrooms", methods=["GET"])
    @login_required
    def api_classrooms():
        return jsonify(db.list_classrooms())

    @app.route("/api/classrooms/<classroom_id>", methods=["POST"])
    @login_required
    def api_update_classroom(classroom_id: str):
        data = request.json or {}
        db.upsert_classroom(
            classroom_id=classroom_id,
            camera_id=data.get("camera_id", ""),
            class_name=data.get("class_name", ""),
            floor=int(data.get("floor", 1)),
        )
        return jsonify({"ok": True})

    # ── Reports ────────────────────────────────────────────────────────────────
    @app.route("/reports/pdf")
    @login_required
    def report_pdf():
        d   = request.args.get("date", date.today().isoformat())
        cls = request.args.get("class") or None
        p   = generate_pdf_report(d, cls)
        return send_from_directory(config.REPORT_DIR, Path(p).name, as_attachment=True)

    @app.route("/reports/excel")
    @login_required
    def report_excel():
        d   = request.args.get("date", date.today().isoformat())
        cls = request.args.get("class") or None
        p   = generate_excel_report(d, cls)
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
            return jsonify({"ok": True})
        return jsonify({"error": "Failed to save"}), 500

    @app.route("/api/settings/password", methods=["POST"])
    @login_required
    def api_change_password():
        pwd = (request.json or {}).get("password", "").strip()
        if len(pwd) < 6:
            return jsonify({"error": "Password must be at least 6 characters"}), 400
        try:
            env_path = config.BASE_DIR / ".env"
            if env_path.exists():
                text = env_path.read_text(encoding="utf-8")
                if "ADMIN_PASSWORD=" in text:
                    text = re.sub(r"^ADMIN_PASSWORD=.*$", f"ADMIN_PASSWORD={pwd}", text, flags=re.MULTILINE)
                else:
                    text += f"\nADMIN_PASSWORD={pwd}\n"
            else:
                text = f"ADMIN_PASSWORD={pwd}\n"
            env_path.write_text(text, encoding="utf-8")
            config.ADMIN_PASSWORD = pwd
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Reset ──────────────────────────────────────────────────────────────────
    @app.route("/api/reset_all", methods=["DELETE"])
    @login_required
    def api_reset_all():
        import sqlite3, shutil
        try:
            conn = sqlite3.connect(config.DB_PATH)
            conn.execute("DELETE FROM attendance")
            conn.execute("UPDATE students SET is_active=0")
            conn.commit(); conn.close()
            shutil.rmtree(config.EMBEDDINGS_DIR, ignore_errors=True)
            config.EMBEDDINGS_DIR.mkdir(exist_ok=True)
            if engine:
                engine.load_known_faces()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── SocketIO events ────────────────────────────────────────────────────────
    @socketio.on("connect")
    def on_connect():
        emit("connected", {"status": "ok"})

    @socketio.on("disconnect")
    def on_disconnect():
        pass

    # ── Frontend static assets ─────────────────────────────────────────────────
    @app.route("/assets/<path:filename>")
    def frontend_assets(filename):
        return send_from_directory(str(config.FRONTEND_DIST / "assets"), filename)

    # ── SPA catch-all — MUST be last ──────────────────────────────────────────
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def spa(path):
        """Serve React SPA for all non-API routes."""
        # Let Flask handle /api/, /stream/, /snapshot/, /reports/ naturally
        # This route only catches unmatched paths
        return _serve_spa()
