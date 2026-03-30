"""
Image preprocessing pipeline.
Applied before face detection to handle:
- Poor / uneven classroom lighting  (CLAHE + gamma)
- Low-light noise                   (bilateral filter)
- Small / distant faces             (Lanczos upscale)
"""
import cv2
import numpy as np
from config import (
    ENABLE_CLAHE, CLAHE_CLIP_LIMIT, CLAHE_TILE_SIZE,
    ENABLE_DENOISE, SUPER_RES_SCALE,
)

_clahe = cv2.createCLAHE(
    clipLimit=CLAHE_CLIP_LIMIT,
    tileGridSize=CLAHE_TILE_SIZE,
)


def mean_brightness(bgr: np.ndarray) -> float:
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    return float(lab[:, :, 0].mean())


def gamma_correct(bgr: np.ndarray, brightness: float) -> np.ndarray:
    """Brighten dark frames. brightness 0-128 -> gamma 0.4-1.0."""
    if brightness > 140:
        return bgr
    gamma   = 0.40 + (brightness / 140.0) * 0.60
    inv_g   = 1.0 / gamma
    table   = np.array(
        [(i / 255.0) ** inv_g * 255 for i in range(256)], dtype=np.uint8
    )
    return cv2.LUT(bgr, table)


def apply_clahe(bgr: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = _clahe.apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def bilateral_denoise(bgr: np.ndarray, brightness: float) -> np.ndarray:
    if brightness > 150:
        return bgr
    d, sigma = (7, 50) if brightness > 80 else (9, 75)
    return cv2.bilateralFilter(bgr, d, sigma, sigma)


def maybe_upscale(bgr: np.ndarray):
    """Upscale large frames so the detector sees bigger faces."""
    h, w = bgr.shape[:2]
    if h >= 720 and SUPER_RES_SCALE > 1:
        new_w = int(w * SUPER_RES_SCALE)
        new_h = int(h * SUPER_RES_SCALE)
        return cv2.resize(bgr, (new_w, new_h),
                          interpolation=cv2.INTER_LANCZOS4), float(SUPER_RES_SCALE)
    return bgr, 1.0


def enhance_frame(bgr: np.ndarray):
    """
    Full pipeline. Returns (enhanced_frame, scale_factor).
    Caller must divide detected bbox coords by scale_factor.
    """
    brightness = mean_brightness(bgr)
    bgr = gamma_correct(bgr, brightness)
    if ENABLE_CLAHE:
        bgr = apply_clahe(bgr)
    if ENABLE_DENOISE:
        bgr = bilateral_denoise(bgr, brightness)
    bgr, scale = maybe_upscale(bgr)
    return bgr, scale


def enhance_face_crop(face_bgr: np.ndarray) -> np.ndarray:
    """Extra enhancement on the cropped face region before embedding."""
    h, _ = face_bgr.shape[:2]
    if h < 112:
        face_bgr = cv2.resize(face_bgr, (112, 112),
                              interpolation=cv2.INTER_LANCZOS4)
    b = mean_brightness(face_bgr)
    face_bgr = gamma_correct(face_bgr, b)
    face_bgr = apply_clahe(face_bgr)
    return face_bgr
