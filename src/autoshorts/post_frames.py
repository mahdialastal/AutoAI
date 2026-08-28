"""Smart single-frame extraction for Facebook/social post images.

The site samples several frames internally, scores them for visual quality,
returns ONE best frame, and leaves creative AI editing to n8n/image models.
"""
from __future__ import annotations

import math
import shutil
from datetime import datetime, timezone
from pathlib import Path

import cv2


ASPECT_RATIOS = {
    "4:5": 4 / 5,
    "1:1": 1.0,
}


def _load_cascade(filename: str):
    path = Path(cv2.data.haarcascades) / filename
    cascade = cv2.CascadeClassifier(str(path))
    return cascade if not cascade.empty() else None


_FACE_CASCADE = _load_cascade("haarcascade_frontalface_default.xml")
_EYE_CASCADE = _load_cascade("haarcascade_eye_tree_eyeglasses.xml")


def _detect_faces_and_eyes(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)

    faces = []
    if _FACE_CASCADE is not None:
        detected = _FACE_CASCADE.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(60, 60),
        )
        faces = [tuple(map(int, face)) for face in detected]

    eye_count = 0
    if _EYE_CASCADE is not None:
        for x, y, w, h in faces:
            upper_face = gray[y:y + max(1, int(h * 0.65)), x:x + w]
            if upper_face.size == 0:
                continue
            eyes = _EYE_CASCADE.detectMultiScale(
                upper_face,
                scaleFactor=1.1,
                minNeighbors=4,
                minSize=(15, 15),
            )
            eye_count += min(2, len(eyes))

    return faces, eye_count


def _frame_quality(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    faces, eye_count = _detect_faces_and_eyes(frame)

    exposure_score = max(0.0, 100.0 - abs(brightness - 128.0) * 0.9)
    sharpness_score = min(
        180.0,
        math.sqrt(max(0.0, blur_variance)) * 12.0,
    )
    face_score = min(3, len(faces)) * 140.0
    eye_score = min(4, eye_count) * 45.0
    score = face_score + eye_score + sharpness_score + exposure_score

    return {
        "score": float(score),
        "faces": faces,
        "face_count": len(faces),
        "eye_count": int(eye_count),
        "blur_variance": round(blur_variance, 2),
        "brightness": round(brightness, 2),
    }


def _crop_to_aspect(frame, target_ratio, faces):
    height, width = frame.shape[:2]
    if width <= 0 or height <= 0:
        raise ValueError("Invalid frame dimensions")

    current_ratio = width / height

    if current_ratio > target_ratio:
        crop_w = max(1, int(round(height * target_ratio)))

        if faces:
            centers = [x + w / 2 for x, y, w, h in faces]
            weights = [max(1.0, w * h) for x, y, w, h in faces]
            center_x = (
                sum(c * wt for c, wt in zip(centers, weights))
                / sum(weights)
            )
        else:
            center_x = width / 2

        left = int(round(center_x - crop_w / 2))
        left = max(0, min(width - crop_w, left))
        return frame[:, left:left + crop_w]

    crop_h = max(1, int(round(width / target_ratio)))

    if faces:
        centers = [y + h / 2 for x, y, w, h in faces]
        weights = [max(1.0, w * h) for x, y, w, h in faces]
        center_y = (
            sum(c * wt for c, wt in zip(centers, weights))
            / sum(weights)
        )
    else:
        center_y = height / 2

    top = int(round(center_y - crop_h / 2))
    top = max(0, min(height - crop_h, top))
    return frame[top:top + crop_h, :]


def extract_best_post_frame(
    video_path: Path,
    output_root: Path,
    start: float,
    end: float,
    aspect_ratio: str = "4:5",
    sample_count: int = 9,
):
    """Sample the story window and save ONE best social-post frame."""
    video_path = Path(video_path)
    output_root = Path(output_root)

    if not video_path.is_file():
        raise FileNotFoundError(f"Source video not found: {video_path}")

    start = max(0.0, float(start))
    end = float(end)

    if end <= start:
        raise ValueError("end must be greater than start")

    if aspect_ratio not in ASPECT_RATIOS:
        raise ValueError("aspect_ratio must be one of: 4:5, 1:1")

    sample_count = max(5, min(15, int(sample_count)))
    duration = end - start

    if duration <= 2.0:
        timestamps = [start + duration / 2]
    else:
        edge_padding = min(1.0, duration * 0.08)
        inner_start = start + edge_padding
        inner_end = end - edge_padding

        if inner_end <= inner_start:
            inner_start = start
            inner_end = end

        timestamps = [
            inner_start
            + (inner_end - inner_start) * index / (sample_count - 1)
            for index in range(sample_count)
        ]

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Could not open source video: {video_path}")

    candidates = []

    try:
        for timestamp in timestamps:
            capture.set(
                cv2.CAP_PROP_POS_MSEC,
                float(timestamp) * 1000.0,
            )
            ok, frame = capture.read()

            if not ok or frame is None or frame.size == 0:
                continue

            quality = _frame_quality(frame)
            candidates.append(
                {
                    "timestamp": float(timestamp),
                    "frame": frame,
                    **quality,
                }
            )
    finally:
        capture.release()

    if not candidates:
        raise RuntimeError(
            "Could not decode any usable frame from the requested period"
        )

    candidates.sort(
        key=lambda item: (
            item["face_count"] > 0,
            item["eye_count"] > 0,
            item["score"],
        ),
        reverse=True,
    )
    best = candidates[0]

    cropped = _crop_to_aspect(
        best["frame"],
        ASPECT_RATIOS[aspect_ratio],
        best["faces"],
    )

    if aspect_ratio == "4:5":
        target_w, target_h = 1080, 1350
    else:
        target_w, target_h = 1080, 1080

    resized = cv2.resize(
        cropped,
        (target_w, target_h),
        interpolation=cv2.INTER_LANCZOS4,
    )

    job_id = datetime.now(timezone.utc).strftime(
        "frame_%Y%m%d_%H%M%S_%f"
    )
    job_dir = output_root / job_id
    job_dir.mkdir(parents=True, exist_ok=False)

    frame_path = job_dir / "frame.jpg"

    saved = cv2.imwrite(
        str(frame_path),
        resized,
        [int(cv2.IMWRITE_JPEG_QUALITY), 94],
    )

    if not saved:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise RuntimeError("Failed to save extracted post frame")

    return {
        "frame_job_id": job_id,
        "frame_path": str(frame_path),
        "timestamp": round(float(best["timestamp"]), 3),
        "face_count": int(best["face_count"]),
        "eye_count": int(best["eye_count"]),
        "blur_variance": float(best["blur_variance"]),
        "brightness": float(best["brightness"]),
        "sampled_frames": len(candidates),
        "aspect_ratio": aspect_ratio,
        "resolution": f"{target_w}x{target_h}",
    }
