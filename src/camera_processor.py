"""
Per-camera background thread.
Reads frames → encodes for streaming always.
Face detection + identification only when recognition_enabled = True.

Includes a robust reconnect watchdog for RTSP/USB cameras:
- Infinite reconnect loop on frame failure
- 15-second frozen-stream watchdog (handles silently-stuck RTSP)
- Emits camera_status Socket.IO events on state changes
"""
import time
import logging
import threading
import queue
from collections import defaultdict
from datetime import datetime

import cv2
import numpy as np
from pathlib import Path

import config
import database as db
from face_engine import FaceEngine, FaceResult

log = logging.getLogger(__name__)

# How long (seconds) to wait between reconnect attempts
_RECONNECT_DELAY   = 5
# How long (seconds) without a new frame before forcing a reconnect
_WATCHDOG_TIMEOUT  = 15
# Seconds to sleep between reconnect bursts after many failures
_LONG_SLEEP        = 30
# Attempts per burst before taking a long sleep
_ATTEMPTS_PER_BURST = 5


class CameraProcessor(threading.Thread):

    def __init__(self, camera_id: str, source, socketio=None):
        super().__init__(daemon=True, name=f"cam-{camera_id}")
        self.camera_id  = camera_id
        self.source     = source
        self.socketio   = socketio

        self._engine      = FaceEngine()
        self._stop_evt    = threading.Event()
        self._frame_lock  = threading.Lock()
        self._latest_jpg: bytes = b""

        # Recognition gate — OFF by default to protect system on startup
        self._recognition_lock    = threading.Lock()
        self._recognition_enabled = False

        self._confirm_buf: dict = defaultdict(list)
        self._last_marked: dict = {}
        self._last_faces:  list = []

        self.stats = {
            "capture_fps":        0.0,
            "stream_fps":         config.STREAM_FPS,
            "faces_detected":     0,
            "recognitions_today": 0,
            "status":             "stopped",
            "recognition_enabled": False,
        }

    def stop(self):
        self._stop_evt.set()

    def get_jpeg(self) -> bytes:
        with self._frame_lock:
            return self._latest_jpg

    def set_recognition(self, enabled: bool):
        with self._recognition_lock:
            self._recognition_enabled = enabled
            self.stats["recognition_enabled"] = enabled
        if not enabled:
            self._confirm_buf.clear()
            self._last_faces = []
        log.info("[%s] Recognition %s", self.camera_id, "ON" if enabled else "OFF")

    @property
    def recognition_enabled(self) -> bool:
        with self._recognition_lock:
            return self._recognition_enabled

    def _emit_status(self, status: str):
        """Update stats and emit a Socket.IO event so the UI reacts instantly."""
        self.stats["status"] = status
        if self.socketio:
            try:
                self.socketio.emit("camera_status", {
                    "camera_id": self.camera_id,
                    "status":    status,
                })
            except Exception:
                pass

    def run(self):
        if isinstance(self.source, str) and Path(self.source).is_dir():
            self._run_folder()
        else:
            self._run_capture()

    # ── Folder / image slideshow mode ──────────────────────────────────────────
    def _run_folder(self):
        EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tiff'}
        folder = Path(self.source)
        images = sorted([p for p in folder.iterdir() if p.suffix.lower() in EXTS])
        if not images:
            self._emit_status("error"); return

        self._emit_status("running")
        self.stats["capture_fps"] = round(1.0 / max(0.1, config.IMAGE_FOLDER_DELAY), 1)
        idx = 0

        while not self._stop_evt.is_set():
            img_path = images[idx % len(images)]; idx += 1
            try:
                frame = cv2.imread(str(img_path))
            except Exception:
                continue
            if frame is None:
                continue

            cv2.putText(frame, img_path.name, (10, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

            if self.recognition_enabled:
                try:
                    faces = self._engine.detect(frame)
                    identified = self._identify_and_mark(faces)
                    self._last_faces = identified
                    self.stats["faces_detected"] = len(identified)
                    ann = FaceEngine.draw_results(frame, identified)
                    self._encode(ann)
                except Exception as e:
                    log.warning("[%s] Detection error: %s", self.camera_id, e)
                    self._encode(frame)
            else:
                self._last_faces = []
                self.stats["faces_detected"] = 0
                self._encode(frame)

            deadline = time.time() + config.IMAGE_FOLDER_DELAY
            while time.time() < deadline and not self._stop_evt.is_set():
                time.sleep(0.05)

        self._emit_status("stopped")

    # ── Live camera mode with watchdog reconnection ─────────────────────────────
    def _run_capture(self):
        cap = self._open_capture()
        if cap is None:
            self._emit_status("error")
            return

        self._emit_status("running")
        frame_count     = 0
        fps_count       = 0
        fps_ts          = time.time()
        last_frame_ts   = time.time()   # watchdog timestamp

        while not self._stop_evt.is_set():

            # ── Frozen-stream watchdog ────────────────────────────────────────
            if time.time() - last_frame_ts > _WATCHDOG_TIMEOUT:
                log.warning(
                    "[%s] No new frame for %ds — stream may be frozen, reconnecting",
                    self.camera_id, _WATCHDOG_TIMEOUT,
                )
                cap.release()
                cap = self._reconnect_loop()
                if cap is None:
                    break
                last_frame_ts = time.time()
                continue

            ret, frame = cap.read()

            if not ret or frame is None:
                log.warning("[%s] cap.read() returned no frame — entering reconnect loop", self.camera_id)
                cap.release()
                cap = self._reconnect_loop()
                if cap is None:
                    break
                last_frame_ts = time.time()
                continue

            # Successful frame
            last_frame_ts = time.time()
            frame_count  += 1
            fps_count    += 1
            now = time.time()
            if now - fps_ts >= 3.0:
                self.stats["capture_fps"] = round(fps_count / (now - fps_ts), 1)
                fps_count = 0; fps_ts = now

            # Always stream — recognition gate determines whether we detect
            if not self.recognition_enabled:
                self._last_faces = []
                self.stats["faces_detected"] = 0
                self._encode(frame)
                continue

            # On skipped frames redraw last known boxes
            if frame_count % config.PROCESS_EVERY_N != 0:
                ann = FaceEngine.draw_results(frame, self._last_faces) if self._last_faces else frame
                self._encode(ann)
                continue

            faces = self._engine.detect(frame)
            identified = self._identify_and_mark(faces)
            self._last_faces = identified
            self.stats["faces_detected"] = len(identified)
            self._encode(FaceEngine.draw_results(frame, identified))

        if cap:
            cap.release()
        self._emit_status("stopped")

    def _reconnect_loop(self):
        """
        Keep trying to reconnect until successful or stop is requested.
        Backs off after _ATTEMPTS_PER_BURST failures to avoid hammering the source.
        Returns a working VideoCapture, or None if stopped.
        """
        self._emit_status("reconnecting")
        attempt = 0

        while not self._stop_evt.is_set():
            attempt += 1
            log.info("[%s] Reconnect attempt %d…", self.camera_id, attempt)
            cap = self._open_capture(max_attempts=1)
            if cap is not None:
                log.info("[%s] Reconnected successfully on attempt %d", self.camera_id, attempt)
                self._emit_status("running")
                return cap

            # After a burst of failed attempts, take a longer break
            if attempt % _ATTEMPTS_PER_BURST == 0:
                log.warning(
                    "[%s] %d consecutive reconnect failures — sleeping %ds before next burst",
                    self.camera_id, attempt, _LONG_SLEEP,
                )
                self._stop_evt.wait(timeout=_LONG_SLEEP)
            else:
                self._stop_evt.wait(timeout=_RECONNECT_DELAY)

        return None   # Stop was requested

    def _identify_and_mark(self, faces):
        identified = []
        for face in faces:
            sid, sim = self._engine.identify(face)
            face.student_id   = sid
            face.student_name = self._engine.get_student_name(sid) if sid else None
            face.similarity   = sim
            if sid and self._should_mark(sid, sim):
                self._mark(face)
                self.stats["recognitions_today"] += 1
            identified.append(face)
        return identified

    def _open_capture(self, max_attempts: int = 5):
        for attempt in range(max_attempts):
            backend = cv2.CAP_DSHOW if config.USE_DSHOW else cv2.CAP_ANY
            cap = cv2.VideoCapture(self.source, backend)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH,  config.FRAME_WIDTH)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                return cap
            cap.release()
            if max_attempts > 1:
                log.warning("[%s] Cannot open (attempt %d/%d)", self.camera_id, attempt + 1, max_attempts)
                time.sleep(3)
        if max_attempts > 1:
            log.error("[%s] Failed to open camera after %d attempts.", self.camera_id, max_attempts)
        return None

    def _encode(self, bgr: np.ndarray):
        ret, jpg = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 72])
        if ret:
            with self._frame_lock:
                self._latest_jpg = jpg.tobytes()

    def _should_mark(self, student_id: str, sim: float) -> bool:
        buf = self._confirm_buf[student_id]
        buf.append(True)
        if len(buf) > config.CONFIRM_FRAMES: buf.pop(0)
        if len(buf) < config.CONFIRM_FRAMES or not all(buf): return False
        if self._last_marked.get(student_id): return False
        if db.was_marked_today(student_id):
            self._last_marked[student_id] = True; return False
        return True

    def _mark(self, face: FaceResult):
        ok = db.mark_attendance(face.student_id, self.camera_id, face.similarity)
        if not ok: return
        self._last_marked[face.student_id] = True
        self._confirm_buf[face.student_id] = []
        log.info("[%s] Marked: %s | sim=%.3f", self.camera_id, face.student_name, face.similarity)
        if self.socketio:
            self.socketio.emit("attendance_marked", {
                "camera_id":    self.camera_id,
                "student_id":   face.student_id,
                "student_name": face.student_name,
                "confidence":   round(face.similarity, 3),
                "timestamp":    datetime.now().strftime("%H:%M:%S"),
            })


# ── Push-camera processor (used in Colab / no-backend-camera environments) ────

class PushCameraProcessor(threading.Thread):
    """
    Camera processor fed by HTTP-pushed JPEG frames instead of cv2.VideoCapture.

    Used in Google Colab where the backend VM has no physical camera.  The
    browser-side webcam is captured with JavaScript and each frame is POSTed
    as raw JPEG bytes to /api/push_frame/<camera_id>.  This processor dequeues
    those frames, runs face detection/recognition (on GPU via CUDA EP), encodes
    the annotated result, and makes it available via get_jpeg() — exactly like
    CameraProcessor, so the rest of the stack (streaming, SocketIO events,
    attendance marking) works without any changes.
    """

    def __init__(self, camera_id: str, socketio=None):
        super().__init__(daemon=True, name=f"push-cam-{camera_id}")
        self.camera_id = camera_id
        self.socketio  = socketio

        self._engine     = FaceEngine()
        self._stop_evt   = threading.Event()
        self._frame_lock = threading.Lock()
        self._latest_jpg: bytes       = b""
        self._queue:      queue.Queue = queue.Queue(maxsize=2)

        self._recognition_lock    = threading.Lock()
        self._recognition_enabled = False

        self._confirm_buf: dict = defaultdict(list)
        self._last_marked: dict = {}
        self._last_faces:  list = []

        self.stats = {
            "capture_fps":         0.0,
            "stream_fps":          config.STREAM_FPS,
            "faces_detected":      0,
            "recognitions_today":  0,
            "status":              "waiting",
            "recognition_enabled": False,
        }

    # ── Public interface (mirrors CameraProcessor) ───────────────────────────

    def push_frame(self, jpeg_bytes: bytes):
        """Inject a JPEG frame from the HTTP push endpoint (thread-safe)."""
        try:
            self._queue.put_nowait(jpeg_bytes)
        except queue.Full:
            # Drop oldest frame and enqueue the fresh one
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(jpeg_bytes)
            except Exception:
                pass

    def stop(self):
        self._stop_evt.set()

    def get_jpeg(self) -> bytes:
        with self._frame_lock:
            return self._latest_jpg

    def set_recognition(self, enabled: bool):
        with self._recognition_lock:
            self._recognition_enabled = enabled
            self.stats["recognition_enabled"] = enabled
        if not enabled:
            self._confirm_buf.clear()
            self._last_faces = []
        log.info("[%s] Recognition %s", self.camera_id, "ON" if enabled else "OFF")

    @property
    def recognition_enabled(self) -> bool:
        with self._recognition_lock:
            return self._recognition_enabled

    # ── Internal helpers ────────────────────────────────────────────────────

    def _emit_status(self, status: str):
        self.stats["status"] = status
        if self.socketio:
            try:
                self.socketio.emit("camera_status", {
                    "camera_id": self.camera_id,
                    "status":    status,
                })
            except Exception:
                pass

    def run(self):
        self._emit_status("waiting")
        fps_count   = 0
        fps_ts      = time.time()
        frame_count = 0

        while not self._stop_evt.is_set():
            try:
                jpeg_bytes = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue

            arr   = np.frombuffer(jpeg_bytes, np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                continue

            self._emit_status("running")
            fps_count   += 1
            frame_count += 1
            now = time.time()
            if now - fps_ts >= 3.0:
                self.stats["capture_fps"] = round(fps_count / (now - fps_ts), 1)
                fps_count = 0
                fps_ts    = now

            if not self.recognition_enabled:
                self._last_faces = []
                self.stats["faces_detected"] = 0
                self._encode_frame(frame)
                continue

            if frame_count % config.PROCESS_EVERY_N != 0:
                ann = FaceEngine.draw_results(frame, self._last_faces) if self._last_faces else frame
                self._encode_frame(ann)
                continue

            faces      = self._engine.detect(frame)
            identified = self._identify_and_mark(faces)
            self._last_faces             = identified
            self.stats["faces_detected"] = len(identified)
            self._encode_frame(FaceEngine.draw_results(frame, identified))

        self._emit_status("stopped")

    def _identify_and_mark(self, faces):
        identified = []
        for face in faces:
            sid, sim = self._engine.identify(face)
            face.student_id   = sid
            face.student_name = self._engine.get_student_name(sid) if sid else None
            face.similarity   = sim
            if sid and self._should_mark(sid, sim):
                self._mark(face)
                self.stats["recognitions_today"] += 1
            identified.append(face)
        return identified

    def _should_mark(self, student_id: str, sim: float) -> bool:
        buf = self._confirm_buf[student_id]
        buf.append(True)
        if len(buf) > config.CONFIRM_FRAMES: buf.pop(0)
        if len(buf) < config.CONFIRM_FRAMES or not all(buf): return False
        if self._last_marked.get(student_id): return False
        if db.was_marked_today(student_id):
            self._last_marked[student_id] = True; return False
        return True

    def _mark(self, face: FaceResult):
        ok = db.mark_attendance(face.student_id, self.camera_id, face.similarity)
        if not ok: return
        self._last_marked[face.student_id] = True
        self._confirm_buf[face.student_id] = []
        log.info("[%s] Marked: %s | sim=%.3f", self.camera_id, face.student_name, face.similarity)
        if self.socketio:
            self.socketio.emit("attendance_marked", {
                "camera_id":    self.camera_id,
                "student_id":   face.student_id,
                "student_name": face.student_name,
                "confidence":   round(face.similarity, 3),
                "timestamp":    datetime.now().strftime("%H:%M:%S"),
            })

    def _encode_frame(self, bgr: np.ndarray):
        ret, jpg = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 72])
        if ret:
            with self._frame_lock:
                self._latest_jpg = jpg.tobytes()


class CameraManager:

    def __init__(self, socketio=None):
        self._procs: dict = {}
        self._socketio    = socketio

    def start_all(self):
        for cam_id, source in config.CAMERAS.items():
            self.start_camera(cam_id, source)

    def start_camera(self, camera_id: str, source):
        self.stop_camera(camera_id)
        # "push://" source → PushCameraProcessor (Colab / no-backend-camera mode)
        if isinstance(source, str) and source.startswith("push://"):
            proc = PushCameraProcessor(camera_id, self._socketio)
        else:
            proc = CameraProcessor(camera_id, source, self._socketio)
        self._procs[camera_id] = proc
        proc.start()

    def stop_camera(self, camera_id: str):
        proc = self._procs.pop(camera_id, None)
        if proc:
            proc.stop(); proc.join(timeout=5)

    def stop_all(self):
        for cam_id in list(self._procs):
            self.stop_camera(cam_id)

    def push_frame(self, camera_id: str, jpeg_bytes: bytes) -> bool:
        """Forward a JPEG frame to a PushCameraProcessor (Colab mode only)."""
        proc = self._procs.get(camera_id)
        if proc and isinstance(proc, PushCameraProcessor):
            proc.push_frame(jpeg_bytes)
            return True
        return False

    def get_jpeg(self, camera_id: str) -> bytes:
        proc = self._procs.get(camera_id)
        return proc.get_jpeg() if proc else b""

    def set_recognition(self, camera_id: str, enabled: bool) -> bool:
        proc = self._procs.get(camera_id)
        if proc:
            proc.set_recognition(enabled)
            return True
        return False

    def get_stats(self) -> dict:
        stats = {}
        for cam_id in config.CAMERAS:
            source = config.CAMERAS.get(cam_id)
            is_push_source = isinstance(source, str) and source.startswith("push://")
            if cam_id in self._procs:
                proc_stats = dict(self._procs[cam_id].stats)
                proc_stats["is_push_source"] = is_push_source
                stats[cam_id] = proc_stats
            else:
                stats[cam_id] = {
                    "capture_fps": 0.0, "stream_fps": config.STREAM_FPS,
                    "faces_detected": 0, "recognitions_today": 0,
                    "status": "stopped", "recognition_enabled": False,
                    "is_push_source": is_push_source,
                }
        return stats

    def is_running(self, camera_id: str) -> bool:
        return camera_id in self._procs
