"""
Student enrollment — updated to accept stream parameter.
"""
import argparse, csv, logging, sys
from pathlib import Path

import cv2
import numpy as np

import config
import database as db
from face_engine import FaceEngine
from augment import augment_image

log = logging.getLogger(__name__)


def _fps_sample(embeddings: np.ndarray, k: int) -> np.ndarray:
    n = len(embeddings)
    if n <= k: return embeddings
    selected = [0]
    dists = np.full(n, np.inf)
    for _ in range(k - 1):
        last  = embeddings[selected[-1]]
        d     = 1.0 - embeddings @ last
        dists = np.minimum(dists, d)
        selected.append(int(np.argmax(dists)))
    return embeddings[selected]


def enroll_student(student_id: str, name: str, class_name: str,
                   stream: str = "", section: str = "", roll_no: int = 0,
                   image_paths: list = None) -> bool:
    engine = FaceEngine()
    if not image_paths:
        log.error("No images provided for %s.", student_id); return False

    all_embeds = []
    for img_path in image_paths:
        img = cv2.imread(img_path)
        if img is None: continue
        emb = engine.get_embedding(img)
        if emb is not None: all_embeds.append(emb)
        for aug in augment_image(img, n=4):
            e = engine.get_embedding(aug)
            if e is not None: all_embeds.append(e)

    if not all_embeds:
        log.error("No faces detected for %s.", student_id); return False

    embeds = np.stack(all_embeds, axis=0)
    if len(embeds) > config.EMBEDDINGS_PER_STUDENT:
        embeds = _fps_sample(embeds, config.EMBEDDINGS_PER_STUDENT)

    npy_path = config.EMBEDDINGS_DIR / f"{student_id}.npy"
    np.save(str(npy_path), embeds)

    db.add_student(student_id, name, class_name, stream, section, roll_no, str(image_paths[0]))
    engine.reload_student(student_id)
    log.info("[OK] Enrolled: %s (%s) Class %s%s Sec %s",
             name, student_id, class_name, f"/{stream}" if stream else "", section)
    return True
