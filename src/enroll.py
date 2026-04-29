"""
Student enrollment.
Saves raw photo embeddings — NO augmentation.

InsightFace (ArcFace R100 in buffalo_l) is trained on millions of faces with
all natural variations (lighting, pose, expression, age). Adding aggressive
augmentation (extreme brightness, 30 % downscale, rotation) during enrollment
introduces out-of-distribution embeddings that pollute the stored template and
degrade recognition accuracy. Raw photos from the webcam enrollment flow are
already diverse enough.
"""
import logging
from pathlib import Path

import cv2
import numpy as np

import config
import database as db
from face_engine import FaceEngine

log = logging.getLogger(__name__)


def _save_profile_photo(student_id: str, img: np.ndarray, engine: FaceEngine) -> str:
    """Crop the best detected face with padding and save as profile photo."""
    try:
        faces = engine.detect(img)
        if not faces:
            return ""
        best  = max(faces, key=lambda f: f.score)
        x, y, w, h = best.bbox.astype(int)
        ih, iw = img.shape[:2]
        px = int(w * 0.40)
        py = int(h * 0.50)
        x1 = max(0, x - px);  y1 = max(0, y - py)
        x2 = min(iw, x + w + px); y2 = min(ih, y + h + py)
        crop = img[y1:y2, x1:x2]
        if crop.size == 0:
            return ""
        crop = cv2.resize(crop, (224, 224), interpolation=cv2.INTER_LANCZOS4)
        dst  = config.STUDENT_IMG_DIR / f"{student_id}.jpg"
        cv2.imwrite(str(dst), crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
        log.info("Profile photo saved: %s", dst)
        return str(dst)
    except Exception as e:
        log.warning("Profile photo failed for %s: %s", student_id, e)
        return ""


def enroll_student(student_id: str, name: str, class_name: str,
                   stream: str = "", section: str = "", roll_no: int = 0,
                   image_paths: list = None) -> bool:
    engine = FaceEngine()
    if not image_paths:
        log.error("No images provided for %s.", student_id)
        return False

    all_embeds: list = []
    first_face_img   = None

    for img_path in image_paths:
        img = cv2.imread(img_path)
        if img is None:
            log.warning("Cannot read image: %s", img_path)
            continue
        # Use the raw, un-augmented image directly.
        # InsightFace handles lighting/pose/expression internally.
        emb = engine.get_embedding(img)
        if emb is not None:
            all_embeds.append(emb)
            if first_face_img is None:
                first_face_img = img.copy()
        else:
            log.warning("No face detected in: %s", img_path)

    if not all_embeds:
        log.error("No faces detected for student %s in any image.", student_id)
        return False

    embeds = np.stack(all_embeds, axis=0)
    log.info("Storing %d embedding(s) for %s.", len(embeds), student_id)

    npy_path = config.EMBEDDINGS_DIR / f"{student_id}.npy"
    np.save(str(npy_path), embeds)

    # Profile photo
    photo_path = ""
    if first_face_img is not None:
        photo_path = _save_profile_photo(student_id, first_face_img, engine)

    db.add_student(student_id, name, class_name, stream, section, roll_no, photo_path)
    engine.reload_student(student_id)
    log.info("[OK] Enrolled: %s (%s) Class %s%s Sec %s — %d photo(s)",
             name, student_id, class_name,
             f"/{stream}" if stream else "", section, len(all_embeds))
    return True
