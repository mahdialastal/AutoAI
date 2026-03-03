"""Estimate horizontal focus point for smart vertical cropping.

Uses MediaPipe face detection on a few sampled frames within the segment
to find where faces tend to be located horizontally (left/center/right).
Returns a normalized x coordinate in [0, 1] or None if no faces detected.
"""
from __future__ import annotations

from pathlib import Path
from statistics import mean
from typing import Optional

import cv2
import mediapipe as mp


def estimate_focus_x(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    num_samples: int = 8,
) -> Optional[float]:
    """Return normalized x in [0,1] where we should center the crop.

    If no reliable faces are found, returns None and callers should
    fall back to center crop.
    """
    duration = max(0.1, end_sec - start_sec)
    if duration <= 0:
        return None

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None

    # Sample timestamps within the segment (avoid exact boundaries)
    step = duration / (num_samples + 1)
    sample_times = [start_sec + step * (i + 1) for i in range(num_samples)]

    xs: list[float] = []
    face_detection = mp.solutions.face_detection.FaceDetection(
        model_selection=0,
        min_detection_confidence=0.4,
    )
    try:
        for t in sample_times:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            h, w = frame.shape[:2]
            if w <= 0 or h <= 0:
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = face_detection.process(rgb)
            if not result.detections:
                continue

            # Take the highest-score detection
            best = max(
                result.detections,
                key=lambda d: (d.score[0] if d.score else 0.0),
            )
            box = best.location_data.relative_bounding_box
            cx = box.xmin + box.width / 2.0
            if 0.0 <= cx <= 1.0:
                xs.append(cx)
    finally:
        face_detection.close()
        cap.release()

    if not xs:
        return None

    m = mean(xs)
    # Avoid extreme edges to reduce chance of cropping off content
    return max(0.1, min(0.9, float(m)))


def get_face_bbox(
    video_path: Path,
    at_sec: float = 2.0,
    padding: float = 0.15,
) -> Optional[tuple[float, float, float, float]]:
    """
    Get the bounding box of the largest face in a frame as (xmin, ymin, xmax, ymax) normalized in [0,1].
    padding: extra margin around the face (e.g. 0.15 = 15% on each side).
    Returns None if no face detected.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_POS_MSEC, at_sec * 1000.0)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return None

    h, w = frame.shape[:2]
    if w <= 0 or h <= 0:
        return None

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    face_detection = mp.solutions.face_detection.FaceDetection(
        model_selection=0,
        min_detection_confidence=0.4,
    )
    try:
        result = face_detection.process(rgb)
        if not result.detections:
            return None
        best = max(
            result.detections,
            key=lambda d: (d.score[0] if d.score else 0.0),
        )
        box = best.location_data.relative_bounding_box
        xmin = max(0.0, box.xmin - padding)
        ymin = max(0.0, box.ymin - padding)
        xmax = min(1.0, box.xmin + box.width + padding)
        ymax = min(1.0, box.ymin + box.height + padding)
        if xmax <= xmin + 0.05 or ymax <= ymin + 0.05:
            return None
        return (xmin, ymin, xmax, ymax)
    finally:
        face_detection.close()


def _expand_bbox_for_webcam(
    bbox: tuple[float, float, float, float],
    expand_factor: float = 1.65,
) -> tuple[float, float, float, float]:
    """
    Expand a face bbox so the webcam crop shows head+shoulders, not just a tight face.
    expand_factor: scale the box around its center (1.65 = ~65% larger each side).
    """
    xmin, ymin, xmax, ymax = bbox
    cx = (xmin + xmax) / 2.0
    cy = (ymin + ymax) / 2.0
    hw = (xmax - xmin) / 2.0
    hh = (ymax - ymin) / 2.0
    # Use the larger dimension so the crop is more square-like (webcam window)
    r = max(hw, hh) * expand_factor
    new_xmin = max(0.0, cx - r)
    new_ymin = max(0.0, cy - r)
    new_xmax = min(1.0, cx + r)
    new_ymax = min(1.0, cy + r)
    if new_xmax <= new_xmin + 0.02 or new_ymax <= new_ymin + 0.02:
        return bbox
    return (new_xmin, new_ymin, new_xmax, new_ymax)


def detect_webcam_chat_regions(
    video_path: Path,
    at_sec: float = 2.0,
    chat_width_ratio: float = 0.35,
    expand_webcam: bool = True,
) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]]:
    """
    Detect webcam (face) and chat (right-side strip) regions for stacking.
    Returns (webcam_bbox, chat_bbox) each (left, top, right, bottom) in [0,1].
    If no face is found, webcam_bbox is center 50% of frame.
    Chat is always the right chat_width_ratio of the frame (e.g. 0.35 = right 35%).
    When expand_webcam is True, the face bbox is expanded so the crop shows head+shoulders.
    """
    face = get_face_bbox(video_path, at_sec=at_sec)
    if face is not None:
        webcam_bbox = _expand_bbox_for_webcam(face) if expand_webcam else face
    else:
        # Fallback: center 50% width, full height (approximate webcam)
        webcam_bbox = (0.25, 0.0, 0.75, 1.0)

    # Chat: right portion of the frame (typical stream layout)
    chat_left = 1.0 - chat_width_ratio
    chat_bbox = (chat_left, 0.0, 1.0, 1.0)

    return webcam_bbox, chat_bbox

