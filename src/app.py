"""
FaceTrack AI — Flask application factory + all routes.
"""
import sys, logging, socket, threading, webbrowser, re
from datetime import date
from functools import wraps
from pathlib import Path

from flask import Flask, Response, jsonify, request, session, send_from_directory
from flask_socketio import SocketIO, emit

import config
import database as db
from camera_processor import CameraManager
from face_engine import FaceEngine
from report_generator import generate_pdf_report, generate_excel_report

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

socketio = SocketIO(async_mode="threading", cors_allowed_origins="*",
                    logger=False, engineio_logger=False)

camera_manager: CameraManager = None
engine: FaceEngine = None

# ── Class sort order ──────────────────────────────────────────────────────────
_CLASS_ORDER = {
    "Nursery": 0, "LKG": 1, "UKG": 2,
    "I": 3, "II": 4, "III": 5, "IV": 6, "V": 7,
    "VI": 8, "VII": 9, "VIII": 10, "IX": 11, "X": 12,
    "XI": 13, "XII": 14,
}

def sort_classes(classes):
    def key(c):
        return (_CLASS_ORDER.get(c, 99), c)
    return sorted(classes, key=key)


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
    socketio.init_app(app)
    _register_routes(app)
    return app


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify({"error": "Unauthorised"}), 401
        return f(*args, **kwargs)
    return decorated


def get_enrolled_count() -> int:
    try:    return len(db.list_students())
    except: return 0


def startup(app):
    global camera_manager, engine
    log.info("=" * 60)
    log.info("  FaceTrack AI — starting up")
    log.info("=" * 60)

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
          f"\n  Pass  : {config.ADMIN_PASSWORD}\n  Ctrl+C to stop\n{'='*60}\n", flush=True)

    threading.Timer(2.0, lambda: webbrowser.open(local_url)).start()


def _serve_spa():
    dist = config.FRONTEND_DIST
    if not (dist / "index.html").exists():
        return ("<h2>Frontend not built.</h2><p>Run: cd frontend && npm install && npm run build</p>", 503)
    return send_from_directory(str(dist), "index.html")


def _register_routes(app: Flask):

    # ── Auth ───────────────────────────────────────────────────────────────────
    @app.route("/api/auth/status")
    def api_auth_status():
        if session.get("logged_in"):
            return jsonify({"logged_in": True, "username": session.get("username", ""),
                            "enrolled": get_enrolled_count()})
        return jsonify({"logged_in": False, "enrolled": 0})

    @app.route("/login", methods=["POST"])
    def login_post():
        if request.is_json:
            data = request.json or {}
            username, password = data.get("username","").strip(), data.get("password","")
        else:
            username = request.form.get("username","").strip()
            password = request.form.get("password","")
        if username == config.ADMIN_USERNAME and password == config.ADMIN_PASSWORD:
            session["logged_in"] = True; session["username"] = username
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "Invalid username or password."}), 401

    @app.route("/logout")
    def logout():
        session.clear(); return jsonify({"ok": True})

    # ── Snapshot / stream ──────────────────────────────────────────────────────
    @app.route("/snapshot/<camera_id>")
    @login_required
    def snapshot(camera_id):
        jpg = camera_manager.get_jpeg(camera_id) if camera_manager else b""
        if not jpg:
            import base64
            blank = base64.b64decode(
                "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoH"
                "BwYIDAoMCwsKCwsNCxAQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/wAAR"
                "CAABAAEDASIA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAA"
                "AAAAAAAP/xAAUAQEAAAAAAAAAAAAAAAAAAAAA/8QAFBEBAAAAAAAAAAAAAAAA"
                "AAAA/9oADAMBAAIRAxEAPwCwABmX/9k=")
            return Response(blank, mimetype="image/jpeg")
        return Response(jpg, mimetype="image/jpeg")

    @app.route("/stream/<camera_id>")
    @login_required
    def stream(camera_id):
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
        import sqlite3 as _sql
        target = request.args.get("date", date.today().isoformat())
        try:
            c = _sql.connect(config.DB_PATH)
            c.execute("DELETE FROM attendance WHERE date=?", (target,))
            c.commit(); c.close()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/attendance/clear_all", methods=["DELETE"])
    @login_required
    def api_clear_all_attendance():
        import sqlite3 as _sql
        try:
            c = _sql.connect(config.DB_PATH)
            c.execute("DELETE FROM attendance"); c.commit(); c.close()
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

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
        db.delete_student(student_id)
        if engine: engine.remove_student(student_id)
        return jsonify({"ok": True})

    @app.route("/api/enroll", methods=["POST"])
    @login_required
    def api_enroll():
        from enroll import enroll_student
        import tempfile, shutil

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

    # ── Classes ────────────────────────────────────────────────────────────────
    @app.route("/api/classes", methods=["GET"])
    @login_required
    def api_get_classes():
        # Classes come entirely from the DB — no config list involved
        return jsonify(db.list_classes())

    @app.route("/api/classes", methods=["POST"])
    @login_required
    def api_add_class():
        name = (request.json or {}).get("name", "").strip()
        if not name: return jsonify({"error": "Class name required"}), 400
        # Seed default section(s) — this is how a class is registered in the DB
        db.ensure_default_sections([name])
        return jsonify({"ok": True})

    @app.route("/api/classes/<path:class_name>", methods=["DELETE"])
    @login_required
    def api_delete_class(class_name):
        # Remove all sections for this class from the DB
        # (students are NOT deleted — they keep their class_name field)
        import sqlite3 as _sql
        try:
            c = _sql.connect(config.DB_PATH)
            c.execute("DELETE FROM class_sections WHERE class_name=?", (class_name,))
            c.commit(); c.close()
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        return jsonify({"ok": True})

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
        # stream will be the literal string "__none__" when empty (URL-safe)
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
        if config.save_settings(data): return jsonify({"ok": True})
        return jsonify({"error": "Failed to save"}), 500

    @app.route("/api/settings/password", methods=["POST"])
    @login_required
    def api_change_password():
        pwd = (request.json or {}).get("password", "").strip()
        if len(pwd) < 6: return jsonify({"error": "Minimum 6 characters"}), 400
        try:
            env_path = config.BASE_DIR / ".env"
            text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
            if "ADMIN_PASSWORD=" in text:
                text = re.sub(r"^ADMIN_PASSWORD=.*$", f"ADMIN_PASSWORD={pwd}",
                              text, flags=re.MULTILINE)
            else:
                text += f"\nADMIN_PASSWORD={pwd}\n"
            env_path.write_text(text, encoding="utf-8")
            config.ADMIN_PASSWORD = pwd
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ── Reset ──────────────────────────────────────────────────────────────────
    @app.route("/api/reset_all", methods=["DELETE"])
    @login_required
    def api_reset_all():
        import sqlite3 as _sql, shutil
        try:
            c = _sql.connect(config.DB_PATH)
            c.execute("DELETE FROM attendance")
            c.execute("UPDATE students SET is_active=0")
            c.commit(); c.close()
            shutil.rmtree(config.EMBEDDINGS_DIR, ignore_errors=True)
            config.EMBEDDINGS_DIR.mkdir(exist_ok=True)
            if engine: engine.load_known_faces()
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
