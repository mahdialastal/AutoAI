"""Per-frame subject tracking with temporal smoothing for dynamic vertical crop.

Produces a time-series of (t, cx, cy) that follows the subject across a clip
so the 9:16 crop window can pan with the subject instead of sitting on a single
static position. See export.render_dynamic_crop for how this is consumed.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

TrackerMode = Literal["auto", "face", "person", "off"]

COCO_PERSON_ID = 0


@dataclass
class TrackConfig:
    mode: TrackerMode = "auto"
    sample_fps: float = 6.0
    ema_alpha: float = 0.18
    deadzone: float = 0.05
    max_speed: float = 0.40
    min_confidence: float = 0.35
    max_gap_sec: float = 1.5


@dataclass
class TrackPoint:
    t: float
    cx: float
    cy: float
    detected: bool


def _detect_faces_frame(frame, face_detector) -> tuple[float, float, float] | None:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = face_detector.process(rgb)
    if not result.detections:
        return None
    best = max(result.detections, key=lambda d: (d.score[0] if d.score else 0.0))
    conf = float(best.score[0]) if best.score else 0.0
    box = best.location_data.relative_bounding_box
    cx = box.xmin + box.width / 2.0
    cy = box.ymin + box.height / 2.0
    if not (0.0 <= cx <= 1.0 and 0.0 <= cy <= 1.0):
        return None
    return cx, cy, conf


def _detect_person_frame(frame, yolo_model) -> tuple[float, float, float] | None:
    h, w = frame.shape[:2]
    results = yolo_model.predict(
        frame, classes=[COCO_PERSON_ID], conf=0.3, verbose=False
    )
    if not results:
        return None
    r = results[0]
    if r.boxes is None or len(r.boxes) == 0:
        return None
    best_area = -1.0
    best_cx = best_cy = 0.5
    best_conf = 0.0
    for i in range(len(r.boxes)):
        xyxy = r.boxes.xyxy[i].cpu().numpy()
        if xyxy.ndim == 2:
            xyxy = xyxy[0]
        x0, y0, x1, y1 = [float(v) for v in xyxy[:4]]
        area = (x1 - x0) * (y1 - y0)
        if area > best_area:
            best_area = area
            best_cx = ((x0 + x1) / 2.0) / w
            best_cy = ((y0 + y1) / 2.0) / h
            best_conf = float(r.boxes.conf[i].cpu().numpy()) if r.boxes.conf is not None else 0.5
    if best_area <= 0:
        return None
    return best_cx, best_cy, best_conf


def _open_face_detector():
    import mediapipe as mp
    return mp.solutions.face_detection.FaceDetection(
        model_selection=1, min_detection_confidence=0.35
    )


def _open_yolo():
    try:
        from ultralytics import YOLO
        return YOLO("yolov8n.pt")
    except Exception:
        return None


def build_track(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    config: TrackConfig = TrackConfig(),
) -> list[TrackPoint]:
    """Sample frames at config.sample_fps, detect subject, return raw track.

    Gaps (no detection) get detected=False; the caller smooths/interpolates.
    """
    if config.mode == "off":
        return []
    duration = end_sec - start_sec
    if duration <= 0:
        return []

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []
    try:
        n = max(2, int(duration * config.sample_fps))
        times = [start_sec + duration * i / (n - 1) for i in range(n)]

        face_det = None
        yolo = None
        use_mode = config.mode
        if use_mode in ("auto", "face"):
            try:
                face_det = _open_face_detector()
            except Exception:
                face_det = None
        if use_mode == "person":
            yolo = _open_yolo()

        raw: list[TrackPoint] = []
        face_hits = 0
        for t in times:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, frame = cap.read()
            if not ok or frame is None:
                raw.append(TrackPoint(t - start_sec, 0.5, 0.5, False))
                continue
            hit = None
            if face_det is not None:
                hit = _detect_faces_frame(frame, face_det)
                if hit is not None and hit[2] >= config.min_confidence:
                    face_hits += 1
            elif yolo is not None:
                hit = _detect_person_frame(frame, yolo)
            if hit is not None and hit[2] >= config.min_confidence:
                raw.append(TrackPoint(t - start_sec, hit[0], hit[1], True))
            else:
                raw.append(TrackPoint(t - start_sec, 0.5, 0.5, False))

        # Auto mode: if faces aren't reliable, make a second pass with YOLO to
        # fill in missing detections from persons.
        if use_mode == "auto" and face_hits < 0.5 * len(times):
            yolo = _open_yolo()
            if yolo is not None:
                for idx, tp in enumerate(raw):
                    if tp.detected:
                        continue
                    cap.set(cv2.CAP_PROP_POS_MSEC, (start_sec + tp.t) * 1000.0)
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        continue
                    hit = _detect_person_frame(frame, yolo)
                    if hit is not None and hit[2] >= config.min_confidence:
                        raw[idx] = TrackPoint(tp.t, hit[0], hit[1], True)

        if face_det is not None:
            face_det.close()
        return raw
    finally:
        cap.release()


def _interpolate_gaps(raw: list[TrackPoint], max_gap_sec: float) -> list[TrackPoint]:
    """Fill detected=False points by linear interp between nearest detected neighbors.

    Points whose gap exceeds max_gap_sec keep (0.5, 0.5) — caller will hold last-known
    or revert to center.
    """
    if not raw:
        return raw
    out = [TrackPoint(p.t, p.cx, p.cy, p.detected) for p in raw]
    n = len(out)
    for i in range(n):
        if out[i].detected:
            continue
        left = i - 1
        while left >= 0 and not out[left].detected:
            left -= 1
        right = i + 1
        while right < n and not out[right].detected:
            right += 1
        if left < 0 and right >= n:
            continue
        if left < 0:
            out[i] = TrackPoint(out[i].t, out[right].cx, out[right].cy, False)
            continue
        if right >= n:
            out[i] = TrackPoint(out[i].t, out[left].cx, out[left].cy, False)
            continue
        if out[right].t - out[left].t > max_gap_sec:
            out[i] = TrackPoint(out[i].t, out[left].cx, out[left].cy, False)
            continue
        f = (out[i].t - out[left].t) / max(1e-6, out[right].t - out[left].t)
        cx = out[left].cx + f * (out[right].cx - out[left].cx)
        cy = out[left].cy + f * (out[right].cy - out[left].cy)
        out[i] = TrackPoint(out[i].t, cx, cy, False)
    return out


def smooth_track(
    raw: list[TrackPoint], config: TrackConfig = TrackConfig()
) -> list[TrackPoint]:
    """Interpolate gaps, apply EMA, deadzone, and max-speed clamp."""
    if not raw:
        return raw
    filled = _interpolate_gaps(raw, config.max_gap_sec)
    out: list[TrackPoint] = []
    prev_cx = filled[0].cx
    prev_cy = filled[0].cy
    for i, p in enumerate(filled):
        if i == 0:
            out.append(TrackPoint(p.t, prev_cx, prev_cy, p.detected))
            continue
        dt = max(1e-3, p.t - out[-1].t)
        target_cx = p.cx
        target_cy = p.cy
        if abs(target_cx - prev_cx) < config.deadzone:
            target_cx = prev_cx
        if abs(target_cy - prev_cy) < config.deadzone:
            target_cy = prev_cy
        new_cx = prev_cx + config.ema_alpha * (target_cx - prev_cx)
        new_cy = prev_cy + config.ema_alpha * (target_cy - prev_cy)
        max_delta = config.max_speed * dt
        new_cx = prev_cx + max(-max_delta, min(max_delta, new_cx - prev_cx))
        new_cy = prev_cy + max(-max_delta, min(max_delta, new_cy - prev_cy))
        new_cx = max(0.0, min(1.0, new_cx))
        new_cy = max(0.0, min(1.0, new_cy))
        out.append(TrackPoint(p.t, new_cx, new_cy, p.detected))
        prev_cx, prev_cy = new_cx, new_cy
    return out


def resample_track(
    smoothed: list[TrackPoint], fps: float, duration: float
) -> list[TrackPoint]:
    """Linearly interpolate the smoothed sparse track to per-frame resolution."""
    if not smoothed or fps <= 0 or duration <= 0:
        return smoothed
    n = max(1, int(round(duration * fps)))
    ts = np.asarray([p.t for p in smoothed], dtype=np.float64)
    cxs = np.asarray([p.cx for p in smoothed], dtype=np.float64)
    cys = np.asarray([p.cy for p in smoothed], dtype=np.float64)
    target_ts = np.linspace(0.0, duration, n)
    ix = np.interp(target_ts, ts, cxs)
    iy = np.interp(target_ts, ts, cys)
    return [TrackPoint(float(t), float(x), float(y), True) for t, x, y in zip(target_ts, ix, iy)]


def track_coverage(raw: list[TrackPoint]) -> float:
    """Fraction of raw samples that had a real detection. Caller uses this to
    decide whether the track is trustworthy or should fall back to center."""
    if not raw:
        return 0.0
    return sum(1 for p in raw if p.detected) / len(raw)
