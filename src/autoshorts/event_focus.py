"""Event/news/rescue footage: person and group tracking for smart cropping.

Uses YOLOv8 + ByteTrack to detect and track all persons in a segment,
then computes a single crop region that keeps the group/action in frame
with optional downward bias for ground-level rescue/chaotic footage.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2


# COCO person class id
COCO_PERSON_ID = 0


def _ensure_yolo():
    try:
        from ultralytics import YOLO
        return YOLO
    except ImportError:
        return None


def estimate_event_crop(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    *,
    padding: float = 0.12,
    ground_bias: float = 0.15,
    sample_fps: float = 2.0,
    min_box_area: float = 0.001,
    focus_region: str = "full",
) -> Optional[tuple[float, float, float, float]]:
    """
    Estimate a single crop region (normalized [0,1]) that contains all detected
    persons. When focus_region == "center", runs on the center 70%×90% of each
    frame (screen recording) and returns bbox in coords of that center region.
    """
    YOLOCls = _ensure_yolo()
    if YOLOCls is None:
        # No YOLO: return default region (center 90%, lower 85%) for ground/event footage
        return (0.05, 0.15, 0.95, 0.95)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    if focus_region == "center":
        cw, ch = int(w * 0.7), int(h * 0.9)
        cx0, cy0 = (w - cw) // 2, int(h * 0.05)
    else:
        cw, ch, cx0, cy0 = w, h, 0, 0

    duration = end_sec - start_sec
    n_want = max(5, int(duration * sample_fps))
    step = duration / (n_want + 1) if n_want else 0
    frame_times = [start_sec + step * (i + 1) for i in range(n_want)] if step > 0 else [start_sec + duration / 2.0]

    if not frame_times:
        return None

    model = YOLOCls("yolov8n.pt")
    all_boxes: list[tuple[float, float, float, float]] = []
    low_frame_boxes: list[tuple[float, float, float, float]] = []

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None
    try:
        for t in frame_times:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            if focus_region == "center":
                frame = frame[cy0 : cy0 + ch, cx0 : cx0 + cw]
            fh, fw = frame.shape[:2]
            if fw <= 0 or fh <= 0:
                continue
            # YOLO expects BGR; ultralytics returns list of Results (one per frame)
            results = model.track(
                frame,
                persist=True,
                classes=[COCO_PERSON_ID],
                conf=0.25,
                verbose=False,
            )
            if not results:
                continue
            # Single frame → results is list of one Results object
            res_list = results if isinstance(results, list) else [results]
            for r in res_list:
                if r.boxes is None:
                    continue
                for j in range(len(r.boxes)):
                    xyxy = r.boxes.xyxy[j].cpu().numpy()
                    if xyxy.ndim == 2:
                        xyxy = xyxy[0]
                    xmin, ymin, xmax, ymax = float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])
                    # Normalize to [0,1]
                    xn_min = xmin / fw
                    yn_min = ymin / fh
                    xn_max = xmax / fw
                    yn_max = ymax / fh
                    area = (xn_max - xn_min) * (yn_max - yn_min)
                    if area < min_box_area:
                        continue
                    all_boxes.append((xn_min, yn_min, xn_max, yn_max))
                    cy = (yn_min + yn_max) / 2.0
                    if cy > 0.5:
                        low_frame_boxes.append((xn_min, yn_min, xn_max, yn_max))
    finally:
        cap.release()

    if not all_boxes:
        # No persons detected: return a sensible default for ground/event footage
        # (center 90% width, lower 85% of frame so we don't crop off ground action)
        return (0.05, 0.15, 0.95, 0.95)

    # Union bbox of all person boxes
    xmin = min(b[0] for b in all_boxes)
    ymin = min(b[1] for b in all_boxes)
    xmax = max(b[2] for b in all_boxes)
    ymax = max(b[3] for b in all_boxes)

    # Padding
    pad_x = (xmax - xmin) * padding + 0.02
    pad_y = (ymax - ymin) * padding + 0.02
    xmin = max(0.0, xmin - pad_x)
    ymin = max(0.0, ymin - pad_y)
    xmax = min(1.0, xmax + pad_x)
    ymax = min(1.0, ymax + pad_y)

    # Ground-level rescue heuristic: if most action is in lower half, bias crop downward
    if low_frame_boxes and len(low_frame_boxes) >= 0.4 * len(all_boxes):
        extend_bottom = ground_bias
        ymax = min(1.0, ymax + extend_bottom)

    # Ensure minimal size and valid range
    if xmax - xmin < 0.1:
        cx = (xmin + xmax) / 2.0
        xmin = max(0.0, cx - 0.15)
        xmax = min(1.0, cx + 0.15)
    if ymax - ymin < 0.1:
        cy = (ymin + ymax) / 2.0
        ymin = max(0.0, cy - 0.2)
        ymax = min(1.0, cy + 0.2)

    return (xmin, ymin, xmax, ymax)


def should_use_event_fallback(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    sample_fps: float = 2.0,
    face_fail_ratio_threshold: float = 0.3,
) -> bool:
    """
    Returns True if face detection fails in more than face_fail_ratio_threshold
    of sampled frames (e.g. >30%) → caller should prefer event/group crop.
    """
    from .focus import get_face_bbox

    duration = end_sec - start_sec
    if duration <= 0:
        return True
    n_samples = max(2, int(duration * sample_fps))
    step = duration / (n_samples + 1)
    sample_times = [start_sec + step * (i + 1) for i in range(n_samples)]
    failed = 0
    for t in sample_times:
        if get_face_bbox(video_path, at_sec=t) is None:
            failed += 1
    return (failed / len(sample_times)) > face_fail_ratio_threshold
