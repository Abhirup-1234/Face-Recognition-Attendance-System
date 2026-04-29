"""
Face detection (RetinaFace) + recognition (ArcFace) via InsightFace.
Models are downloaded automatically on first run into ~/.insightface/models/
No manual model download required.

IMPORTANT: Do NOT apply custom preprocessing (CLAHE, gamma, bilateral filter)
to frames before passing them to InsightFace.  ArcFace was trained on clean,
aligned face crops — modifying pixel distributions causes embedding drift
and random/wrong recognition.
"""
import threading
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

import config

log = logging.getLogger(__name__)


@dataclass
class FaceResult:
    bbox:         np.ndarray
    score:        float
    embedding:    np.ndarray
    landmarks:    Optional[np.ndarray] = None
    student_id:   Optional[str]        = None
    student_name: Optional[str]        = None
    similarity:   float                = 0.0


class EmbeddingStore:
    """Thread-safe store — computes and caches a mean (centroid) embedding
    per student.  Cosine similarity between the query and each student centroid
    is fast and robust for clean (non-augmented) enrolment sets."""

    def __init__(self):
        self._lock   = threading.RLock()
        self._raw:    dict                  = {}   # sid -> list of L2-normed ndarray
        self._ids:    List[str]             = []
        self._matrix: Optional[np.ndarray] = None  # (N, 512) centroid matrix

    def clear(self):
        """Wipe all embeddings.  Call before a full reload to prevent ghosts."""
        with self._lock:
            self._raw.clear()
            self._ids    = []
            self._matrix = None

    def add(self, student_id: str, embeddings: List[np.ndarray]):
        with self._lock:
            self._raw[student_id] = embeddings
        self._rebuild()

    def remove(self, student_id: str):
        with self._lock:
            self._raw.pop(student_id, None)
        self._rebuild()

    def _rebuild(self):
        with self._lock:
            ids, centroids = [], []
            for sid, embs in self._raw.items():
                centroid = np.mean(embs, axis=0).astype(np.float32)
                n = np.linalg.norm(centroid)
                if n > 1e-10:
                    centroid /= n
                ids.append(sid)
                centroids.append(centroid)
            self._ids    = ids
            self._matrix = np.stack(centroids, axis=0) if centroids else None

    def query(self, emb: np.ndarray) -> Tuple[Optional[str], float]:
        with self._lock:
            if self._matrix is None or not self._ids:
                return None, 0.0
            n = np.linalg.norm(emb)
            q = (emb / n) if n > 1e-10 else emb
            sims = self._matrix @ q          # (N,) cosine similarities
            best = int(np.argmax(sims))
            return self._ids[best], float(sims[best])

    def __len__(self):
        with self._lock:
            return len(self._ids)


class FaceEngine:
    """
    Singleton — RetinaFace (detection) + ArcFace (recognition) via InsightFace.
    Thread-safe after init. Models auto-downloaded on first run (~500 MB).
    """

    _instance  = None
    _init_lock = threading.Lock()

    def __new__(cls):
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        log.info("Loading InsightFace (RetinaFace + ArcFace) ...")
        log.info("Models auto-download on first run (~500 MB) — please wait.")

        try:
            from insightface.app import FaceAnalysis
        except ImportError:
            raise ImportError(
                "InsightFace not installed. "
                "Run: pip install insightface onnxruntime"
            )

        # buffalo_l pack:
        #   det_10g.onnx     -> RetinaFace detector
        #   w600k_r50.onnx   -> ArcFace ResNet50 recognizer (512-d embeddings)
        self._app = FaceAnalysis(
            name="buffalo_l",
            providers=["CPUExecutionProvider"],
        )
        self._app.prepare(
            ctx_id=0,
            det_size=(640, 640),
            det_thresh=config.DET_THRESH,
        )

        self._store:         EmbeddingStore = EmbeddingStore()
        self._student_names: dict           = {}
        self._initialized = True
        log.info("FaceEngine ready — RetinaFace + ArcFace loaded (CPUExecutionProvider).")

    # ── Enrollment ──────────────────────────────────────────────────────────────

    def load_known_faces(self):
        """Reload all embeddings from disk into the in-memory store.

        IMPORTANT: clears the store first so stale ghost embeddings left
        over from previous enrollments (or a Reset) cannot persist.
        """
        import database as db

        # ── Clear everything before rebuilding ──────────────────────────────
        self._store.clear()
        self._student_names = {}

        students = db.list_students()
        self._student_names = {s["student_id"]: s["name"] for s in students}
        loaded = 0
        for npy in config.EMBEDDINGS_DIR.glob("*.npy"):
            sid  = npy.stem
            embs = np.load(str(npy))
            if embs.ndim == 1:
                embs = embs.reshape(1, -1)
            self._store.add(sid, list(embs))
            loaded += 1
        log.info("Loaded embeddings for %d student(s) (store cleared before reload).", loaded)
        return loaded

    def reload_student(self, student_id: str):
        import database as db
        s = db.get_student(student_id)
        if s:
            self._student_names[student_id] = s["name"]
        npy = config.EMBEDDINGS_DIR / f"{student_id}.npy"
        if npy.exists():
            embs = np.load(str(npy))
            if embs.ndim == 1:
                embs = embs.reshape(1, -1)
            self._store.add(student_id, list(embs))

    def remove_student(self, student_id: str):
        self._student_names.pop(student_id, None)
        self._store.remove(student_id)
        p = config.EMBEDDINGS_DIR / f"{student_id}.npy"
        if p.exists():
            p.unlink()

    def get_student_name(self, student_id: str) -> Optional[str]:
        """Public accessor for student names — avoids private member access."""
        return self._student_names.get(student_id)

    # ── Frame normalisation ─────────────────────────────────────────────────────

    @staticmethod
    def _normalise(bgr: np.ndarray) -> Optional[np.ndarray]:
        if bgr is None or bgr.size == 0:
            return None
        if len(bgr.shape) == 2:
            bgr = cv2.cvtColor(bgr, cv2.COLOR_GRAY2BGR)
        elif bgr.shape[2] == 4:
            bgr = cv2.cvtColor(bgr, cv2.COLOR_BGRA2BGR)
        elif bgr.shape[2] == 1:
            bgr = cv2.cvtColor(bgr, cv2.COLOR_GRAY2BGR)
        h, w = bgr.shape[:2]
        if h < 32 or w < 32:
            return None
        if max(h, w) > 2560:
            s = 2560 / max(h, w)
            bgr = cv2.resize(bgr, (int(w * s), int(h * s)))
        return bgr

    # ── Detection ───────────────────────────────────────────────────────────────

    def detect(self, bgr: np.ndarray) -> List[FaceResult]:
        """Detect faces and extract ArcFace embeddings.

        NO custom preprocessing (CLAHE, gamma, bilateral) is applied here.
        InsightFace does its own internal alignment and normalisation on
        each detected face crop.  Altering pixel distributions beforehand
        causes embedding drift and random recognition.
        """
        bgr = self._normalise(bgr)
        if bgr is None:
            return []

        # Pass the clean frame directly to InsightFace (expects BGR)
        try:
            raw_faces = self._app.get(bgr)
        except Exception as e:
            log.warning("RetinaFace detection error: %s", e)
            return []

        results: List[FaceResult] = []
        for f in raw_faces:
            if f.embedding is None:
                continue

            # bbox from InsightFace: [x1, y1, x2, y2]
            x1, y1, x2, y2 = f.bbox.astype(int)
            # Convert to (x, y, w, h) for draw_results compatibility
            bbox = np.array([x1, y1, x2 - x1, y2 - y1], dtype=np.float32)

            emb = f.embedding.copy().flatten().astype(np.float32)
            n = np.linalg.norm(emb)
            if n > 1e-10:
                emb /= n

            results.append(FaceResult(
                bbox=bbox,
                score=float(f.det_score),
                embedding=emb,
                landmarks=f.kps if hasattr(f, "kps") else None,
            ))

        return results

    # ── Identification ──────────────────────────────────────────────────────────

    def identify(self, face: FaceResult) -> Tuple[Optional[str], float]:
        if len(self._store) == 0:
            return None, 0.0
        sid, sim = self._store.query(face.embedding)
        if sim < config.REC_THRESHOLD:
            return None, sim
        return sid, sim

    # ── Embedding extraction (used by enroll.py) ────────────────────────────────

    def get_embedding(self, bgr: np.ndarray) -> Optional[np.ndarray]:
        faces = self.detect(bgr)
        if not faces:
            return None
        return max(faces, key=lambda f: f.score).embedding.copy()

    def get_embeddings_from_images(self, paths: List[str]) -> np.ndarray:
        out = []
        for p in paths:
            try:
                img = cv2.imread(p)
            except Exception:
                log.warning("Cannot read: %s", p)
                continue
            if img is None:
                log.warning("Cannot read: %s", p)
                continue
            emb = self.get_embedding(img)
            if emb is not None:
                out.append(emb)
            else:
                log.warning("No face in: %s", p)
        # ArcFace = 512-dimensional embeddings
        return np.stack(out) if out else np.empty((0, 512), dtype=np.float32)

    # ── Drawing ─────────────────────────────────────────────────────────────────

    @staticmethod
    def draw_results(bgr: np.ndarray, faces: List[FaceResult]) -> np.ndarray:
        out = bgr.copy()
        for face in faces:
            x, y, w, h = face.bbox.astype(int)
            color = (0, 210, 70) if face.student_id else (30, 30, 220)
            cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)
            label = face.student_name or "Unknown"
            if face.student_id:
                label += f" ({face.similarity:.3f})"
            (tw, th), _ = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            cv2.rectangle(out, (x, y - th - 8), (x + tw + 4, y), color, -1)
            cv2.putText(out, label, (x + 2, y - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        return out
