"""
Training data augmentation for enrollment images.
Generates varied versions of each photo to improve robustness.
"""
import random
import cv2
import numpy as np


def augment_image(bgr: np.ndarray, n: int = 4) -> list:
    """Return n augmented variants of the input image."""
    fns = [_flip, _brightness, _contrast, _rotate,
           _blur, _noise, _distance_sim, _shadow]
    results = []
    for _ in range(n):
        img     = bgr.copy()
        chosen  = random.sample(fns, k=random.randint(2, 4))
        for fn in chosen:
            img = fn(img)
        results.append(img)
    return results


def _flip(img):
    return cv2.flip(img, 1)


def _brightness(img):
    f = random.uniform(0.5, 1.6)
    return np.clip(img.astype(np.float32) * f, 0, 255).astype(np.uint8)


def _contrast(img):
    f    = random.uniform(0.7, 1.4)
    mean = img.mean()
    return np.clip((img.astype(np.float32) - mean) * f + mean,
                   0, 255).astype(np.uint8)


def _rotate(img):
    angle = random.uniform(-20, 20)
    h, w  = img.shape[:2]
    M     = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, M, (w, h),
                          borderMode=cv2.BORDER_REFLECT_101)


def _blur(img):
    k = random.choice([3, 5])
    return cv2.GaussianBlur(img, (k, k), 0)


def _noise(img):
    noise = np.random.normal(0, random.uniform(5, 20),
                             img.shape).astype(np.float32)
    return np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def _distance_sim(img):
    """Downscale then upscale to simulate a far-away face."""
    h, w  = img.shape[:2]
    s     = random.uniform(0.3, 0.6)
    small = cv2.resize(img, (int(w * s), int(h * s)),
                       interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def _shadow(img):
    """Add a partial shadow to simulate classroom lighting."""
    out = img.copy().astype(np.float32)
    h, w = img.shape[:2]
    pts  = np.array([
        [random.randint(0, w // 2), 0],
        [random.randint(w // 2, w), 0],
        [random.randint(w // 2, w), h],
        [random.randint(0, w // 2), h],
    ], dtype=np.int32)
    mask  = np.zeros((h, w), dtype=np.float32)
    cv2.fillPoly(mask, [pts], 1.0)
    alpha = random.uniform(0.2, 0.5)
    for c in range(3):
        out[:, :, c] -= out[:, :, c] * mask * alpha
    return np.clip(out, 0, 255).astype(np.uint8)
