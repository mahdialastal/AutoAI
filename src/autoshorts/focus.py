"""Estimate horizontal focus point for smart vertical cropping.

Uses MediaPipe face detection on sampled frames within the segment
to find where faces are located horizontally.

Includes:
- estimate_focus_x(): one static focus point for the whole clip.
- estimate_focus_track(): dynamic focus positions over time.
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
    sample_times = [
        start_sec + step * (i + 1)
        for i in range(num_samples)
    ]

    xs: list[float] = []

    face_detection = mp.solutions.face_detection.FaceDetection(
        model_selection=0,
        min_detection_confidence=0.4,
    )

    try:
        for t in sample_times:
            cap.set(
                cv2.CAP_PROP_POS_MSEC,
                t * 1000.0,
            )

            ok, frame = cap.read()

            if not ok or frame is None:
                continue

            h, w = frame.shape[:2]

            if w <= 0 or h <= 0:
                continue

            rgb = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB,
            )

            result = face_detection.process(rgb)

            if not result.detections:
                continue

            # Take the highest-score detection
            best = max(
                result.detections,
                key=lambda d: (
                    d.score[0]
                    if d.score
                    else 0.0
                ),
            )

            box = (
                best.location_data
                .relative_bounding_box
            )

            cx = box.xmin + box.width / 2.0

            if 0.0 <= cx <= 1.0:
                xs.append(cx)

    finally:
        face_detection.close()
        cap.release()

    if not xs:
        return None

    m = mean(xs)

    # Avoid extreme edges to reduce chance
    # of cropping off important content.
    return max(
        0.1,
        min(0.9, float(m)),
    )


def estimate_focus_track(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    sample_interval: float = 0.5,
    smoothing: float = 0.35,
    dead_zone: float = 0.025,
) -> list[tuple[float, float]]:
    """
    Build a dynamic horizontal face-focus track.

    Returns a list of:

        (
            time_from_clip_start,
            normalized_focus_x,
        )

    Example:

        [
            (0.0, 0.28),
            (0.5, 0.30),
            (1.0, 0.68),
            (1.5, 0.72),
        ]

    normalized_focus_x is clamped between 0.1 and 0.9.

    This tracks visible/prominent faces over time.

    Important:
    This is visual face tracking.
    It does NOT yet determine the active speaker from audio.
    """
    duration = end_sec - start_sec

    if duration <= 0:
        return []

    if sample_interval <= 0:
        sample_interval = 0.5

    smoothing = max(
        0.0,
        min(1.0, smoothing),
    )

    dead_zone = max(
        0.0,
        dead_zone,
    )

    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        return []

    face_detection = mp.solutions.face_detection.FaceDetection(
        model_selection=0,
        min_detection_confidence=0.4,
    )

    track: list[tuple[float, float]] = []

    previous_x: Optional[float] = None

    try:
        relative_time = 0.0

        while relative_time <= duration:
            absolute_time = (
                start_sec + relative_time
            )

            cap.set(
                cv2.CAP_PROP_POS_MSEC,
                absolute_time * 1000.0,
            )

            ok, frame = cap.read()

            if not ok or frame is None:
                relative_time += sample_interval
                continue

            h, w = frame.shape[:2]

            if w <= 0 or h <= 0:
                relative_time += sample_interval
                continue

            rgb = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB,
            )

            result = face_detection.process(rgb)

            detected_x: Optional[float] = None

            if result.detections:
                candidates: list[
                    tuple[
                        float,
                        float,
                        float,
                    ]
                ] = []

                for detection in result.detections:
                    box = (
                        detection.location_data
                        .relative_bounding_box
                    )

                    cx = (
                        box.xmin
                        + box.width / 2.0
                    )

                    area = max(
                        0.0,
                        box.width * box.height,
                    )

                    score = (
                        detection.score[0]
                        if detection.score
                        else 0.0
                    )

                    if 0.0 <= cx <= 1.0:
                        candidates.append(
                            (
                                cx,
                                area,
                                score,
                            )
                        )

                if candidates:
                    if previous_x is None:
                        # At the beginning, prefer
                        # the most prominent face.
                        best = max(
                            candidates,
                            key=lambda item: (
                                item[1] * 2.0
                                + item[2]
                            ),
                        )

                    else:
                        # Prefer continuity, while allowing
                        # switching to another significantly
                        # more prominent face.
                        def candidate_score(
                            item: tuple[
                                float,
                                float,
                                float,
                            ]
                        ) -> float:
                            cx, area, score = item

                            distance = abs(
                                cx - previous_x
                            )

                            return (
                                area * 3.0
                                + score
                                - distance * 0.8
                            )

                        best = max(
                            candidates,
                            key=candidate_score,
                        )

                    detected_x = best[0]

            # If no face is detected,
            # keep following the previous position.
            if detected_x is None:
                if previous_x is None:
                    relative_time += sample_interval
                    continue

                detected_x = previous_x

            detected_x = max(
                0.1,
                min(0.9, detected_x),
            )

            if previous_x is None:
                smoothed_x = detected_x

            else:
                difference = (
                    detected_x - previous_x
                )

                # Ignore tiny detector movements.
                if abs(difference) < dead_zone:
                    smoothed_x = previous_x

                else:
                    # Smooth movement to reduce shaking.
                    smoothed_x = (
                        previous_x
                        + difference * smoothing
                    )

            smoothed_x = max(
                0.1,
                min(0.9, smoothed_x),
            )

            track.append(
                (
                    round(relative_time, 3),
                    float(smoothed_x),
                )
            )

            previous_x = smoothed_x

            relative_time += sample_interval

    finally:
        face_detection.close()
        cap.release()

    return track


def get_face_bbox(
    video_path: Path,
    at_sec: float = 2.0,
    padding: float = 0.15,
    prefer_bottom_half: bool = False,
) -> Optional[
    tuple[
        float,
        float,
        float,
        float,
    ]
]:
    """
    Get the bounding box of the largest face
    in a frame as:

        (
            xmin,
            ymin,
            xmax,
            ymax,
        )

    All values are normalized in [0,1].

    padding:
        Extra margin around the face.

    prefer_bottom_half:
        If True, prefer faces whose center
        is in the bottom half of the frame.

        This can help detect a streamer's
        webcam instead of a face in the
        main content.

    Returns None if no face is detected.
    """
    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        return None

    cap.set(
        cv2.CAP_PROP_POS_MSEC,
        at_sec * 1000.0,
    )

    ok, frame = cap.read()

    cap.release()

    if not ok or frame is None:
        return None

    h, w = frame.shape[:2]

    if w <= 0 or h <= 0:
        return None

    rgb = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2RGB,
    )

    face_detection = mp.solutions.face_detection.FaceDetection(
        model_selection=0,
        min_detection_confidence=0.4,
    )

    try:
        result = face_detection.process(rgb)

        if not result.detections:
            return None

        candidates = result.detections

        if prefer_bottom_half:
            bottom_half = [
                d
                for d in candidates
                if (
                    d.location_data
                    .relative_bounding_box
                    .ymin
                    + d.location_data
                    .relative_bounding_box
                    .height
                    / 2.0
                )
                >= 0.5
            ]

            if bottom_half:
                candidates = bottom_half

        best = max(
            candidates,
            key=lambda d: (
                d.score[0]
                if d.score
                else 0.0
            ),
        )

        box = (
            best.location_data
            .relative_bounding_box
        )

        xmin = max(
            0.0,
            box.xmin - padding,
        )

        ymin = max(
            0.0,
            box.ymin - padding,
        )

        xmax = min(
            1.0,
            box.xmin
            + box.width
            + padding,
        )

        ymax = min(
            1.0,
            box.ymin
            + box.height
            + padding,
        )

        if (
            xmax <= xmin + 0.05
            or ymax <= ymin + 0.05
        ):
            return None

        return (
            xmin,
            ymin,
            xmax,
            ymax,
        )

    finally:
        face_detection.close()


def _expand_bbox_for_webcam(
    bbox: tuple[
        float,
        float,
        float,
        float,
    ],
    expand_factor: float = 1.65,
) -> tuple[
    float,
    float,
    float,
    float,
]:
    """
    Expand a face bbox so the webcam crop
    shows head + shoulders instead of
    only a tight face.
    """
    xmin, ymin, xmax, ymax = bbox

    cx = (
        xmin + xmax
    ) / 2.0

    cy = (
        ymin + ymax
    ) / 2.0

    hw = (
        xmax - xmin
    ) / 2.0

    hh = (
        ymax - ymin
    ) / 2.0

    # Use the larger dimension so the
    # crop is more square-like.
    r = max(
        hw,
        hh,
    ) * expand_factor

    new_xmin = max(
        0.0,
        cx - r,
    )

    new_ymin = max(
        0.0,
        cy - r,
    )

    new_xmax = min(
        1.0,
        cx + r,
    )

    new_ymax = min(
        1.0,
        cy + r,
    )

    if (
        new_xmax
        <= new_xmin + 0.02
        or new_ymax
        <= new_ymin + 0.02
    ):
        return bbox

    return (
        new_xmin,
        new_ymin,
        new_xmax,
        new_ymax,
    )


def detect_webcam_chat_regions(
    video_path: Path,
    at_sec: float = 2.0,
    chat_width_ratio: float = 0.35,
    expand_webcam: bool = True,
    bottom_half_layout: bool = True,
) -> tuple[
    tuple[
        float,
        float,
        float,
        float,
    ],
    tuple[
        float,
        float,
        float,
        float,
    ],
]:
    """
    Detect webcam and chat regions for stacking.

    Returns:

        (
            webcam_bbox,
            chat_bbox,
        )

    Each bbox is:

        (
            left,
            top,
            right,
            bottom,
        )

    Values are normalized in [0,1].
    """
    if bottom_half_layout:
        face = get_face_bbox(
            video_path,
            at_sec=at_sec,
            prefer_bottom_half=True,
        )

        if face is not None:
            webcam_bbox = (
                _expand_bbox_for_webcam(face)
                if expand_webcam
                else face
            )

        else:
            # Fallback: bottom-left region.
            webcam_bbox = (
                0.0,
                0.4,
                0.5,
                1.0,
            )

        # Bottom-right region for chat.
        chat_bbox = (
            0.5,
            0.5,
            1.0,
            1.0,
        )

        return (
            webcam_bbox,
            chat_bbox,
        )

    face = get_face_bbox(
        video_path,
        at_sec=at_sec,
    )

    if face is not None:
        webcam_bbox = (
            _expand_bbox_for_webcam(face)
            if expand_webcam
            else face
        )

    else:
        webcam_bbox = (
            0.25,
            0.0,
            0.75,
            1.0,
        )

    chat_left = (
        1.0 - chat_width_ratio
    )

    chat_bbox = (
        chat_left,
        0.0,
        1.0,
        1.0,
    )

    return (
        webcam_bbox,
        chat_bbox,
    )


def suggest_layout(
    video_path: Path,
    at_sec: float = 2.0,
) -> str:
    """
    Suggest layout from one frame.

    If one face is detected in the left half,
    assume streaming-style layout.

    Returns:
        "webcam_chat_stack"
        or
        "center"
    """
    face = get_face_bbox(
        video_path,
        at_sec=at_sec,
        padding=0.1,
    )

    if face is None:
        return "center"

    xmin, _, xmax, _ = face

    cx = (
        xmin + xmax
    ) / 2.0

    if cx < 0.5:
        return "webcam_chat_stack"

    return "center"
