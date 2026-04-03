"""
Per-camera background thread.
Reads frames → encodes for streaming always.
Face detection + identification only when recognition_enabled = True.
"""
import time
import logging
import threading
from collections import defaultdict
from datetime import datetime

import cv2
import numpy as np
from pathlib import Path

import config
import database as db
from face_engine import FaceEngine, FaceResult

log = logging.getLogger(__name__)


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
            self.stats["status"] = "error"; return

        self.stats["status"] = "running"
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

        self.stats["status"] = "stopped"

    # ── Live camera mode ────────────────────────────────────────────────────────
    def _run_capture(self):
        cap = self._open_capture()
        if cap is None:
            self.stats["status"] = "error"; return

        self.stats["status"] = "running"
        frame_count = 0
        fps_count   = 0
        fps_ts      = time.time()

        while not self._stop_evt.is_set():
            ret, frame = cap.read()
            if not ret:
                log.warning("[%s] Frame read failed — reconnecting", self.camera_id)
                cap.release(); time.sleep(2)
                cap = self._open_capture()
                if cap is None:
                    self.stats["status"] = "error"; break
                continue

            frame_count += 1
            fps_count   += 1
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

        cap.release()
        self.stats["status"] = "stopped"

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

    def _open_capture(self):
        for attempt in range(5):
            cap = cv2.VideoCapture(self.source)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH,  config.FRAME_WIDTH)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                return cap
            log.warning("[%s] Cannot open (attempt %d/5)", self.camera_id, attempt + 1)
            time.sleep(3)
        log.error("[%s] Failed to open camera.", self.camera_id)
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


class CameraManager:

    def __init__(self, socketio=None):
        self._procs: dict = {}
        self._socketio    = socketio

    def start_all(self):
        for cam_id, source in config.CAMERAS.items():
            self.start_camera(cam_id, source)

    def start_camera(self, camera_id: str, source):
        self.stop_camera(camera_id)
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
            if cam_id in self._procs:
                stats[cam_id] = self._procs[cam_id].stats
            else:
                stats[cam_id] = {
                    "capture_fps": 0.0, "stream_fps": config.STREAM_FPS,
                    "faces_detected": 0, "recognitions_today": 0,
                    "status": "stopped", "recognition_enabled": False,
                }
        return stats

    def is_running(self, camera_id: str) -> bool:
        return camera_id in self._procs
