"""
Student enrollment tool.

Usage:
  python enroll.py --id S001 --name "Name" --class "10-A" --photos ./photos/
  python enroll.py --id S001 --name "Name" --class "10-A" --webcam
  python enroll.py --id S001 --name "Name" --class "10-A" --photo face.jpg
  python enroll.py --batch students.csv --photos-root ./photos/
  python enroll.py --list
  python enroll.py --remove S001
"""
import argparse
import csv
import logging
import sys
from pathlib import Path

import cv2
import numpy as np

import config
import database as db
from face_engine import FaceEngine
from augment import augment_image

log = logging.getLogger(__name__)


def _fps_sample(embeddings: np.ndarray, k: int) -> np.ndarray:
    """Farthest-Point Sampling: pick k diverse embeddings."""
    n = len(embeddings)
    if n <= k:
        return embeddings
    selected = [0]
    dists    = np.full(n, np.inf)
    for _ in range(k - 1):
        last  = embeddings[selected[-1]]
        d     = 1.0 - embeddings @ last
        dists = np.minimum(dists, d)
        selected.append(int(np.argmax(dists)))
    return embeddings[selected]


def enroll_student(student_id: str, name: str, class_name: str,
                   section: str = "", roll_no: int = 0,
                   image_paths: list = None) -> bool:
    engine = FaceEngine()

    if not image_paths:
        log.error("No images provided for %s.", student_id)
        return False

    log.info("Extracting embeddings from %d source images ...",
             len(image_paths))

    all_embeds = []
    for img_path in image_paths:
        img = cv2.imread(img_path)
        if img is None:
            log.warning("Cannot read: %s", img_path)
            continue
        emb = engine.get_embedding(img)
        if emb is not None:
            all_embeds.append(emb)
        for aug in augment_image(img, n=4):
            e = engine.get_embedding(aug)
            if e is not None:
                all_embeds.append(e)

    if not all_embeds:
        log.error("No faces detected in any image for %s.", student_id)
        return False

    embeds = np.stack(all_embeds, axis=0)
    if len(embeds) > config.EMBEDDINGS_PER_STUDENT:
        embeds = _fps_sample(embeds, config.EMBEDDINGS_PER_STUDENT)

    npy_path = config.EMBEDDINGS_DIR / f"{student_id}.npy"
    np.save(str(npy_path), embeds)
    log.info("Saved %d embeddings -> %s", len(embeds), npy_path)

    db.add_student(student_id, name, class_name,
                   section, roll_no, str(image_paths[0]))
    engine.reload_student(student_id)

    log.info("[OK] Enrolled: %s (%s) - class %s", name, student_id, class_name)
    return True


def enroll_from_folder(student_id, name, class_name,
                       section, roll_no, folder) -> bool:
    folder = Path(folder)
    exts   = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    paths  = [str(p) for p in sorted(folder.iterdir())
               if p.suffix.lower() in exts]
    if not paths:
        log.error("No images in %s", folder)
        return False
    return enroll_student(student_id, name, class_name,
                          section, roll_no, paths)


def enroll_webcam(student_id, name, class_name,
                  section="", roll_no=0,
                  n_captures=20, cam_index=0) -> bool:
    cap = cv2.VideoCapture(cam_index)
    if not cap.isOpened():
        log.error("Cannot open webcam.")
        return False

    save_dir = config.STUDENT_IMG_DIR / student_id
    save_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    count = 0

    print(f"\nEnrolling: {name} ({student_id})")
    print(f"Capture {n_captures} photos.")
    print("Press SPACE to capture | Q to quit\n")

    while count < n_captures:
        ret, frame = cap.read()
        if not ret:
            break
        disp = frame.copy()
        cv2.putText(disp, f"{count}/{n_captures} captured",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 220, 80), 2)
        cv2.putText(disp, "SPACE=Capture  Q=Done",
                    (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)
        cv2.imshow(f"Enroll: {name}", disp)
        key = cv2.waitKey(1) & 0xFF
        if key == ord(" "):
            p = str(save_dir / f"{count:03d}.jpg")
            cv2.imwrite(p, frame)
            paths.append(p)
            count += 1
        elif key == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

    if not paths:
        log.error("No photos captured.")
        return False
    return enroll_student(student_id, name, class_name,
                          section, roll_no, paths)


def batch_enroll(csv_path: str, photos_root: str = ""):
    ok, failed = 0, 0
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            folder  = Path(photos_root) / row.get("photo_folder", row["student_id"])
            success = enroll_from_folder(
                row["student_id"], row["name"], row["class_name"],
                row.get("section", ""), int(row.get("roll_no", 0)),
                str(folder),
            )
            ok      += success
            failed  += not success
    log.info("Batch done. OK: %d | Failed: %d", ok, failed)


def main():
    db.init_db()
    p = argparse.ArgumentParser()
    p.add_argument("--id");    p.add_argument("--name")
    p.add_argument("--class",  dest="class_name")
    p.add_argument("--section", default="")
    p.add_argument("--roll",    type=int, default=0, dest="roll_no")
    p.add_argument("--photos");  p.add_argument("--photo")
    p.add_argument("--webcam",   action="store_true")
    p.add_argument("--batch");   p.add_argument("--photos-root", default="")
    p.add_argument("--list",     action="store_true")
    p.add_argument("--remove")
    args = p.parse_args()

    if args.list:
        students = db.list_students()
        print(f"\n{'ID':<12} {'Name':<25} {'Class':<15} {'Roll'}")
        print("-" * 60)
        for s in students:
            print(f"{s['student_id']:<12} {s['name']:<25}"
                  f" {s['class_name']:<15} {s['roll_no']}")
        print(f"\nTotal: {len(students)}")
        return

    if args.remove:
        db.delete_student(args.remove)
        FaceEngine().remove_student(args.remove)
        print(f"Removed: {args.remove}")
        return

    if args.batch:
        batch_enroll(args.batch, args.photos_root)
        return

    if not all([args.id, args.name, args.class_name]):
        p.error("--id, --name, --class required")

    if args.photos:
        enroll_from_folder(args.id, args.name, args.class_name,
                           args.section, args.roll_no, args.photos)
    elif args.photo:
        enroll_student(args.id, args.name, args.class_name,
                       args.section, args.roll_no, [args.photo])
    elif args.webcam:
        enroll_webcam(args.id, args.name, args.class_name,
                      args.section, args.roll_no)
    else:
        p.error("Provide --photos, --photo, or --webcam")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    main()
