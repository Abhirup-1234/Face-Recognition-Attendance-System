"""
Face detection (RetinaFace) + recognition (ArcFace) via InsightFace.
Models are downloaded automatically on first run into ~/.insightface/models/
No manual model download required.
"""
import threading
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

import config
from preprocessing import enhance_frame

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
    """Thread-safe store — holds mean embedding per student."""

    def __init__(self):
        self._lock   = threading.RLock()
        self._raw:    dict                  = {}
        self._ids:    List[str]             = []
        self._matrix: Optional[np.ndarray] = None

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
            ids, means = [], []
            for sid, embs in self._raw.items():
                mean = np.mean(embs, axis=0)
                n    = np.linalg.norm(mean)
                if n > 1e-10:
                    mean /= n
                ids.append(sid)
                means.append(mean)
            self._ids    = ids
            self._matrix = np.array(means, dtype=np.float32) if means else None

    def query(self, emb: np.ndarray) -> Tuple[Optional[str], float]:
        with self._lock:
            if self._matrix is None or not self._ids:
                return None, 0.0
            sims = cosine_similarity(emb.reshape(1, -1), self._matrix)[0]
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

        # ── Build provider list with OpenVINO auto-detection ──────────────
        providers = self._select_providers()
        log.info("ONNX providers (requested): %s", [p if isinstance(p, str) else p[0] for p in providers])

        # buffalo_l pack:
        #   det_10g.onnx     -> RetinaFace detector
        #   w600k_r50.onnx   -> ArcFace ResNet50 recognizer (512-d embeddings)
        self._app = FaceAnalysis(
            name="buffalo_l",
            providers=providers,
        )
        self._app.prepare(
            ctx_id=0,
            det_size=(640, 640),
            det_thresh=config.DET_THRESH,
        )

        self._store:         EmbeddingStore = EmbeddingStore()
        self._student_names: dict           = {}
        self._initialized = True
        log.info("FaceEngine ready — RetinaFace + ArcFace loaded.")

    # ── Provider selection ─────────────────────────────────────────────────────

    @staticmethod
    def _select_providers():
        """
        Build the best provider list by trying OpenVINO devices in priority
        order (GPU → CPU) with a quick validation, then falling back to the
        plain ONNX CPUExecutionProvider if OpenVINO is unavailable.
        """
        import os, sys
        import onnxruntime as ort

        # ── Windows DLL fix: add OpenVINO libs dir to DLL search path ─────
        # onnxruntime-openvino needs openvino.dll which lives inside the
        # openvino Python package's libs/ directory.
        try:
            import openvino as _ov
            ov_libs = os.path.join(os.path.dirname(_ov.__file__), "libs")
            if os.path.isdir(ov_libs):
                if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
                    os.add_dll_directory(ov_libs)
                # Also add to PATH as a fallback for older mechanisms
                if ov_libs not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = ov_libs + os.pathsep + os.environ.get("PATH", "")
                log.info("Added OpenVINO DLL path: %s", ov_libs)
        except ImportError:
            log.warning("openvino package not installed — OpenVINO EP will not be available.")
            return ["CPUExecutionProvider"]

        available = ort.get_available_providers()
        log.info("ONNX Runtime %s — available EPs: %s", ort.__version__, available)

        if "OpenVINOExecutionProvider" not in available:
            log.warning("OpenVINOExecutionProvider not available — using CPUExecutionProvider.")
            return ["CPUExecutionProvider"]

        # Ensure the cache directory exists
        cache_dir = config.OPENVINO_CACHE_DIR
        Path(cache_dir).mkdir(parents=True, exist_ok=True)

        # Try each device in priority order
        for device in config.OPENVINO_DEVICE_PRIORITY:
            provider_opts = {
                "device_type": device,
                "cache_dir":   cache_dir,
            }
            if config.OPENVINO_NUM_THREADS > 0 and device == "CPU":
                provider_opts["num_of_threads"] = str(config.OPENVINO_NUM_THREADS)

            provider_tuple = ("OpenVINOExecutionProvider", provider_opts)

            if FaceEngine._validate_provider(provider_tuple, device):
                log.info("✓ OpenVINO %s device validated successfully.", device)
                return [provider_tuple, "CPUExecutionProvider"]
            else:
                log.warning("✗ OpenVINO %s device failed validation — trying next.", device)

        # All OpenVINO devices failed — fall back
        log.warning("All OpenVINO devices failed — falling back to CPUExecutionProvider.")
        return ["CPUExecutionProvider"]

    # Known OpenVINO GPU-backend CISA kernel error signatures.
    # These appear in stderr/logs when buffalo_l models run on the iGPU.
    _OPENVINO_GPU_FATAL_ERRORS = (
        "KERNEL HEADER ERRORS FOUND",
        "intersects with",
        "Explicit input",
        "must not follow an implicit input",
        "Error in CISA routine",
    )

    @staticmethod
    def _validate_provider(provider_tuple, device: str) -> bool:
        """
        Run a dummy inference to verify the provider works at runtime.

        For GPU devices we also intercept stderr to catch the silent OpenVINO
        GPU-backend CISA kernel errors that surface when the real buffalo_l
        models are loaded.  A tiny Add-graph passes even on a broken GPU driver,
        so we use a slightly larger Conv graph to stress the kernel compiler
        while also monitoring error output.
        """
        import io, sys, contextlib
        import numpy as _np
        import onnxruntime as ort
        from onnxruntime import InferenceSession

        log.info("  Testing OpenVINO %s device...", device)

        try:
            import onnx
            from onnx import helper, TensorProto, numpy_helper

            # ── Build a Conv graph (more representative than Add) ─────────
            # Input: [1, 1, 8, 8]  Weight: [1, 1, 3, 3]  Output: [1, 1, 6, 6]
            X = helper.make_tensor_value_info("X", TensorProto.FLOAT, [1, 1, 8, 8])
            Y = helper.make_tensor_value_info("Y", TensorProto.FLOAT, [1, 1, 6, 6])
            W_data = _np.ones((1, 1, 3, 3), dtype=_np.float32)
            W_init = numpy_helper.from_array(W_data, name="W")
            node   = helper.make_node("Conv", ["X", "W"], ["Y"], kernel_shape=[3, 3])
            graph  = helper.make_graph([node], "conv_test", [X], [Y], [W_init])
            model  = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
            model_bytes = model.SerializeToString()

            # ── Capture stderr to detect silent GPU kernel errors ─────────
            stderr_capture = io.StringIO()
            try:
                with contextlib.redirect_stderr(stderr_capture):
                    sess = InferenceSession(
                        model_bytes,
                        providers=[provider_tuple, "CPUExecutionProvider"],
                    )
                    _ = sess.run(None, {"X": _np.ones((1, 1, 8, 8), dtype=_np.float32)})
                    active = sess.get_providers()
            except Exception as e:
                log.warning("  OpenVINO %s session error: %s", device, e)
                return False

            captured = stderr_capture.getvalue()
            if any(sig in captured for sig in FaceEngine._OPENVINO_GPU_FATAL_ERRORS):
                log.warning(
                    "  OpenVINO %s rejected: GPU kernel errors detected in stderr.\n"
                    "  (buffalo_l ONNX models are incompatible with the iGPU backend — "
                    "using OpenVINO CPU instead, which is faster on this hardware.)",
                    device,
                )
                return False

            log.info("  Active providers after test: %s", active)
            return "OpenVINOExecutionProvider" in active

        except ImportError:
            # onnx not installed — do minimal check with just the Add graph
            log.info("  onnx not available; performing lightweight EP check.")
            try:
                # At minimum just verify the EP can be listed as active
                available = ort.get_available_providers()
                ok = "OpenVINOExecutionProvider" in available
                if not ok:
                    log.warning("  OpenVINO %s: EP not in available providers.", device)
                return ok
            except Exception as e:
                log.warning("  OpenVINO %s lightweight check failed: %s", device, e)
                return False

        except Exception as e:
            log.warning("  OpenVINO %s validation failed: %s", device, e)
            return False

    # ── Enrollment ──────────────────────────────────────────────────────────────

    def load_known_faces(self):
        import database as db
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
        log.info("Loaded embeddings for %d student(s).", loaded)
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
        bgr = self._normalise(bgr)
        if bgr is None:
            return []

        try:
            enhanced, scale = enhance_frame(bgr)
        except Exception as e:
            log.warning("Preprocessing failed: %s", e)
            enhanced, scale = bgr, 1.0

        # InsightFace expects RGB
        rgb = cv2.cvtColor(enhanced, cv2.COLOR_BGR2RGB)

        try:
            raw_faces = self._app.get(rgb)
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
            if scale != 1.0:
                bbox /= scale

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
