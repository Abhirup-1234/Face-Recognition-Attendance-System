"""
Comprehensive camera test.
Run with: python test_camera.py
Close ALL other apps using the camera before running.
"""
import cv2

backends = [
    ("CAP_ANY",  cv2.CAP_ANY),
    ("CAP_MSMF", cv2.CAP_MSMF),
    ("CAP_DSHOW",cv2.CAP_DSHOW),
    ("CAP_V4L2", getattr(cv2, 'CAP_V4L2', None)),
]

indices = [0, 1, 2]

found = False
for idx in indices:
    for name, backend in backends:
        if backend is None:
            continue
        try:
            cap = cv2.VideoCapture(idx, backend)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    print(f"SUCCESS: index={idx} backend={name} size={frame.shape}")
                    found = True
                else:
                    print(f"Opened but no frame: index={idx} backend={name}")
            else:
                cap.release()
        except Exception as e:
            print(f"Exception: index={idx} backend={name}: {e}")

if not found:
    print("\nNo working camera found.")
    print("Make sure Windows Camera app and browser are fully closed.")
else:
    print("\nUse the working index and backend above in config.py")
