"""
Per-camera background thread.
Reads frames -> preprocesses -> detects faces -> identifies -> marks attendance.
Caches last detections for smooth bounding box display on skipped frames.
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
        self.camera_id   = camera_id
        self.source      = source
        self.socketio    = socketio

        self._engine     = FaceEngine()
        self._stop_evt   = threading.Event()
        self._frame_lock = threading.Lock()
        self._latest_jpg: bytes = b""

        # Debounce buffers
        self._confirm_buf: dict = defaultdict(list)
        self._last_marked: dict = {}   # student_id -> timestamp
        self._last_faces:  list = []   # cached for skipped frames

        self.stats = {
            "capture_fps":         0.0,   # camera's native read rate
            "stream_fps":          config.STREAM_FPS,  # browser stream rate (from config)
            "faces_detected":      0,
            "recognitions_today":  0,
            "status":              "stopped",
        }

    def stop(self):
        self._stop_evt.set()

    def get_jpeg(self) -> bytes:
        with self._frame_lock:
            return self._latest_jpg

    def run(self):
        log.info("[%s] Starting ...", self.camera_id)

        # Check if source is an image folder
        if isinstance(self.source, str) and Path(self.source).is_dir():
            self._run_folder()
        else:
            self._run_capture()

    def _run_folder(self):
        """Slideshow mode: load images from a folder, loop forever."""
        EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tiff'}
        folder = Path(self.source)

        images = sorted([
            p for p in folder.iterdir()
            if p.suffix.lower() in EXTS
        ])

        if not images:
            log.error("[%s] No images found in folder: %s", self.camera_id, self.source)
            self.stats["status"] = "error"
            return

        log.info("[%s] Image folder mode: %d images, %.1fs each",
                 self.camera_id, len(images), config.IMAGE_FOLDER_DELAY)

        self.stats["status"] = "running"
        self.stats["capture_fps"] = round(1.0 / max(0.1, config.IMAGE_FOLDER_DELAY), 1)

        idx = 0
        while not self._stop_evt.is_set():
            img_path = images[idx % len(images)]
            idx += 1

            try:
                frame = cv2.imread(str(img_path))
            except Exception as e:
                log.warning("[%s] Error reading image %s: %s", self.camera_id, img_path.name, e)
                continue
            if frame is None:
                log.warning("[%s] Could not read image: %s", self.camera_id, img_path.name)
                continue

            # Overlay filename at top-left so you know which image is shown
            label = img_path.name
            cv2.putText(frame, label, (10, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

            # Run detection + identification
            try:
                faces = self._engine.detect(frame)
                self.stats["faces_detected"] = len(faces)

                identified: list = []
                for face in faces:
                    sid, sim = self._engine.identify(face)
                    face.student_id   = sid
                    face.student_name = (
                        self._engine._student_names.get(sid) if sid else None
                    )
                    face.similarity   = sim
    
                    if sid and self._should_mark(sid, sim):
                        self._mark(face)
                        self.stats["recognitions_today"] += 1

                    identified.append(face)

                self._last_faces = identified
                ann = FaceEngine.draw_results(frame, identified)
                self._encode(ann)
            except Exception as e:
                log.warning("[%s] Detection error on %s: %s — skipping",
                            self.camera_id, img_path.name, e)
                self._encode(frame)  # show raw frame even if detection fails

            # Hold this image for IMAGE_FOLDER_DELAY seconds
            # Sleep in small intervals so stop() is responsive
            deadline = time.time() + config.IMAGE_FOLDER_DELAY
            while time.time() < deadline and not self._stop_evt.is_set():
                time.sleep(0.05)

        self.stats["status"] = "stopped"
        log.info("[%s] Folder feed stopped.", self.camera_id)

    def _run_capture(self):
        """Normal mode: live camera or video file."""
        cap = self._open_capture()
        if cap is None:
            self.stats["status"] = "error"
            return

        self.stats["status"] = "running"
        frame_count = 0
        fps_count   = 0
        fps_ts      = time.time()

        while not self._stop_evt.is_set():
            ret, frame = cap.read()
            if not ret:
                log.warning("[%s] Frame read failed - reconnecting ...", self.camera_id)
                cap.release()
                time.sleep(2)
                cap = self._open_capture()
                if cap is None:
                    self.stats["status"] = "error"
                    break
                continue

            frame_count += 1
            fps_count   += 1
            now = time.time()
            if now - fps_ts >= 3.0:
                self.stats["capture_fps"] = round(fps_count / (now - fps_ts), 1)
                fps_count = 0
                fps_ts    = now

            # On skipped frames, redraw last known boxes for smooth display
            if frame_count % config.PROCESS_EVERY_N != 0:
                if self._last_faces:
                    ann = FaceEngine.draw_results(frame, self._last_faces)
                    self._encode(ann)
                else:
                    self._encode(frame)
                continue

            # -- Detection + identification --
            faces = self._engine.detect(frame)
            self.stats["faces_detected"] = len(faces)

            identified: list = []
            for face in faces:
                sid, sim = self._engine.identify(face)
                face.student_id   = sid
                face.student_name = (
                    self._engine._student_names.get(sid) if sid else None
                )
                face.similarity   = sim

                if sid and self._should_mark(sid, sim):
                    self._mark(face)
                    self.stats["recognitions_today"] += 1

                identified.append(face)

            self._last_faces = identified
            ann = FaceEngine.draw_results(frame, identified)
            self._encode(ann)

        cap.release()
        self.stats["status"] = "stopped"
        log.info("[%s] Stopped.", self.camera_id)

    def _open_capture(self):
        for attempt in range(5):
            cap = cv2.VideoCapture(self.source)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH,  config.FRAME_WIDTH)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                return cap
            log.warning("[%s] Cannot open source (attempt %d/5)",
                        self.camera_id, attempt + 1)
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
        if len(buf) > config.CONFIRM_FRAMES:
            buf.pop(0)
        if len(buf) < config.CONFIRM_FRAMES or not all(buf):
            return False
        # Fast in-memory check: already marked today on any camera?
        if self._last_marked.get(student_id):
            return False
        # DB check: marked today on any camera (cross-camera dedup)
        if db.was_marked_today(student_id):
            self._last_marked[student_id] = True
            return False
        return True

    def _mark(self, face: FaceResult):
        ok = db.mark_attendance(
            student_id=face.student_id,
            camera_id=self.camera_id,
            confidence=face.similarity,   # store raw cosine similarity (0-1)
        )
        if not ok:
            return

        self._last_marked[face.student_id] = True
        self._confirm_buf[face.student_id] = []

        log.info("[%s] Marked: %s (%s) | similarity=%.3f",
                 self.camera_id, face.student_name,
                 face.student_id, face.similarity)

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
            proc.stop()
            proc.join(timeout=5)

    def stop_all(self):
        for cam_id in list(self._procs):
            self.stop_camera(cam_id)

    def get_jpeg(self, camera_id: str) -> bytes:
        proc = self._procs.get(camera_id)
        return proc.get_jpeg() if proc else b""

    def get_stats(self) -> dict:
        import config as _cfg
        stats = {}
        # Include all configured cameras, even stopped ones
        for cam_id in _cfg.CAMERAS:
            if cam_id in self._procs:
                stats[cam_id] = self._procs[cam_id].stats
            else:
                stats[cam_id] = {
                    "capture_fps": 0.0,
                    "stream_fps":  _cfg.STREAM_FPS,
                    "faces_detected": 0,
                    "recognitions_today": 0,
                    "status": "stopped",
                }
        return stats

    def is_running(self, camera_id: str) -> bool:
        return camera_id in self._procs
