"""Cut segments, crop to 9:16, and burn captions using FFmpeg."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tracking import TrackPoint


def _get_video_dimensions(video_path: Path) -> tuple[int, int] | None:
    """Return (width, height) via ffprobe, or None."""
    try:
        out = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0",
                str(video_path.resolve()),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        parts = out.stdout.strip().split(",")
        if len(parts) >= 2:
            return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return None


def make_short(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    output_path: Path,
    srt_path: Path | None = None,
    width: int = 1080,
    height: int = 1920,
    focus_x: float | None = None,
    crop_mode: str = "center",
    focus_region: str = "full",
    manual_top: float | None = None,
    manual_bottom: float | None = None,
    manual_left: float | None = None,
    manual_right: float | None = None,
    webcam_bbox: tuple[float, float, float, float] | None = None,
    chat_bbox: tuple[float, float, float, float] | None = None,
    center_bbox: tuple[float, float, float, float] | None = None,
    event_bbox: tuple[float, float, float, float] | None = None,
    letterbox_full_width: bool = False,
) -> Path:
    """
    Extract [start_sec, end_sec], crop to height x width (9:16), optionally burn SRT.
    letterbox_full_width: if True, scale to full width 1080 and pad top/bottom to 1920 (no horizontal crop).
    """
    duration = end_sec - start_sec
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Optional pre-crop used for screen recordings where a vertical short
    # is centered on the screen (e.g. X / TikTok / YouTube Shorts in a browser).
    # We keep a wide center region so embedded video players are included.
    if focus_region == "center":
        # 70% width, 90% height, centered (for screen recordings with video in the middle)
        center_crop = "crop=in_w*0.7:in_h*0.9:in_w*0.15:in_h*0.05"
    else:
        center_crop = None

    # Optional manual region: either vertical strip (top/bottom only) or full rectangle (left, right, top, bottom in [0,1]).
    manual_crop = None
    if manual_top is not None and manual_bottom is not None:
        t = max(0.0, min(manual_top, manual_bottom))
        b = min(1.0, max(manual_top, manual_bottom))
        if b - t > 0.01:  # avoid degenerate / zero-height crops
            if manual_left is not None and manual_right is not None:
                # Full rectangle: e.g. video player area on a YouTube page screenshot
                l_ = max(0.0, min(manual_left, manual_right))
                r_ = min(1.0, max(manual_left, manual_right))
                if r_ - l_ > 0.01:
                    w_expr = f"in_w*{r_ - l_:.4f}"
                    h_expr = f"in_h*{b - t:.4f}"
                    x_expr = f"in_w*{l_:.4f}"
                    y_expr = f"in_h*{t:.4f}"
                    manual_crop = f"crop={w_expr}:{h_expr}:{x_expr}:{y_expr}"
            if manual_crop is None:
                h_expr = f"in_h*{b - t:.4f}"
                y_expr = f"in_h*{t:.4f}"
                manual_crop = f"crop=in_w:{h_expr}:0:{y_expr}"

    if crop_mode == "bottom_strip_rotate":
        # Bottom half of frame → rotate 90° CW → left becomes top, right becomes bottom
        vf_parts = [
            "crop=in_w:in_h/2:0:in_h/2",
            "transpose=1",
            "scale=1080:-1",
            "crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2",
        ]
        if manual_crop:
            vf_parts = [manual_crop] + vf_parts
        elif center_crop:
            vf_parts = [center_crop] + vf_parts
    elif crop_mode == "bottom_split_stack":
        # Bottom-left quadrant on top, bottom-right on bottom, stacked vertically (no rotation)
        # Uses filter_complex; handled separately below
        vf_parts = None
    elif crop_mode == "bottom_split_stack_swapped":
        vf_parts = None
    elif crop_mode == "webcam_chat_stack":
        vf_parts = None  # uses filter_complex with webcam_bbox and chat_bbox; if missing, fallback in branch below
    elif crop_mode == "event":
        # Final step: fill 1080x1920 (crop) or full-width letterbox (no horizontal crop)
        if letterbox_full_width:
            scale_final = "scale=1080:-1,pad=1080:1920:0:(1920-ih)/2:black"
        else:
            scale_final = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
        if event_bbox is not None:
            xmin, ymin, xmax, ymax = event_bbox
            rw = max(0.02, xmax - xmin)
            rh = max(0.02, ymax - ymin)
            event_crop = f"crop=in_w*{rw:.4f}:in_h*{rh:.4f}:in_w*{xmin:.4f}:in_h*{ymin:.4f}"
            if focus_region == "center":
                center_crop_str = "crop=in_w*0.7:in_h*0.9:in_w*0.15:in_h*0.05"
                vf_parts = [center_crop_str, event_crop, scale_final]
            else:
                vf_parts = [event_crop, scale_final]
        else:
            vf_parts = [center_crop, scale_final] if center_crop else [scale_final]
    else:
        # center / speaker / event fallback
        if letterbox_full_width:
            scale_final = "scale=1080:-1,pad=1080:1920:0:(1920-ih)/2:black"
        else:
            scale_final = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
        if event_bbox is not None:
            xmin, ymin, xmax, ymax = event_bbox
            rw = xmax - xmin
            rh = ymax - ymin
            if rw < 0.02:
                rw = 0.02
            if rh < 0.02:
                rh = 0.02
            event_crop = f"crop=in_w*{rw:.4f}:in_h*{rh:.4f}:in_w*{xmin:.4f}:in_h*{ymin:.4f}"
            vf_parts = [event_crop, scale_final]
        elif focus_x is None:
            vf_parts = []
            if manual_crop:
                vf_parts.append(manual_crop)
            elif center_crop:
                vf_parts.append(center_crop)
            vf_parts.append(scale_final)
        else:
            cx_expr = f"in_w*{focus_x:.3f}"
            x_expr = f"min(max({cx_expr}-{width/2}, 0), in_w-{width})"
            crop = f"crop={width}:{height}:{x_expr}:(in_h-{height})/2"
            vf_parts = []
            if manual_crop:
                vf_parts.append(manual_crop)
            elif center_crop:
                vf_parts.append(center_crop)
            vf_parts.append(f"scale=-1:{height}:force_original_aspect_ratio=increase")
            vf_parts.append(crop)
    if srt_path and srt_path.exists():
        srt_name = srt_path.name
        if vf_parts is not None:
            vf_parts.append(f"subtitles=filename={_escape_subtitles_path(srt_name)}")
    vf = ",".join(vf_parts) if vf_parts else None

    out_dir = output_path.parent
    if crop_mode == "webcam_chat_stack" and webcam_bbox is not None and chat_bbox is not None:
        wl, wt, wr, wb = webcam_bbox
        cl, ct, cr, cb = chat_bbox
        rw_w = max(0.01, wr - wl)
        rh_w = max(0.01, wb - wt)
        rw_c = max(0.01, cr - cl)
        rh_c = max(0.01, cb - ct)
        # Heights when scaled to width 1080: need source dimensions so aspect is correct
        src_wh = _get_video_dimensions(video_path)
        if src_wh is not None:
            W, H = src_wh
            h_w = max(1, min(1920, round(1080 * (H * rh_w) / (W * rw_w))))
            h_c = max(1, min(1920, round(1080 * (H * rh_c) / (W * rw_c))))
        else:
            h_w = max(1, min(1920, round(1080 * rh_w / rw_w)))
            h_c = max(1, min(1920, round(1080 * rh_c / rw_c)))
        # Force even heights for 4:2:0 and avoid pad "smaller than input" errors
        def even(v: int) -> int:
            return max(2, (v // 2) * 2)
        h_w = even(h_w)
        h_c = even(h_c)
        # Center fill: default center 50% of frame; or use center_bbox
        if center_bbox is not None:
            ml, mt, mr, mb = center_bbox
        else:
            ml, mt, mr, mb = 0.25, 0.25, 0.75, 0.75
        rw_m = max(0.01, mr - ml)
        rh_m = max(0.01, mb - mt)

        if h_w + h_c < 1920:
            h_mid = even(1920 - h_w - h_c)
            # Three-way stack: webcam (top) | center (middle) | chat (bottom)
            # Use scale-to-fill then crop to exact size so pad is never asked to shrink (avoids FFmpeg error)
            fc = (
                f"[0:v]crop=in_w*{rw_w:.4f}:in_h*{rh_w:.4f}:in_w*{wl:.4f}:in_h*{wt:.4f}[wc];"
                f"[wc]scale=1080:{h_w}:force_original_aspect_ratio=increase,crop=1080:{h_w}:0:0[wc2];"
                f"[0:v]crop=in_w*{rw_c:.4f}:in_h*{rh_c:.4f}:in_w*{cl:.4f}:in_h*{ct:.4f}[ch];"
                f"[ch]scale=1080:{h_c}:force_original_aspect_ratio=increase,crop=1080:{h_c}:0:0[ch2];"
                f"[0:v]crop=in_w*{rw_m:.4f}:in_h*{rh_m:.4f}:in_w*{ml:.4f}:in_h*{mt:.4f}[mid];"
                f"[mid]scale=1080:{h_mid}:force_original_aspect_ratio=decrease,pad=1080:{h_mid}:(ow-iw)/2:(oh-ih)/2:black[mid2];"
                "[wc2][mid2][ch2]vstack=inputs=3[out]"
            )
        else:
            # Scale webcam and chat to fit 1920 total height; no middle
            scale = 1920 / (h_w + h_c)
            h_w_new = even(max(1, round(h_w * scale)))
            h_c_new = 1920 - h_w_new  # keep total exactly 1920
            fc = (
                f"[0:v]crop=in_w*{rw_w:.4f}:in_h*{rh_w:.4f}:in_w*{wl:.4f}:in_h*{wt:.4f}[wc];"
                f"[wc]scale=1080:{h_w_new}:force_original_aspect_ratio=increase,crop=1080:{h_w_new}:0:0[wc2];"
                f"[0:v]crop=in_w*{rw_c:.4f}:in_h*{rh_c:.4f}:in_w*{cl:.4f}:in_h*{ct:.4f}[ch];"
                f"[ch]scale=1080:{h_c_new}:force_original_aspect_ratio=increase,crop=1080:{h_c_new}:0:0[ch2];"
                "[wc2][ch2]vstack=inputs=2[out]"
            )
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-i", str(video_path.resolve()),
            "-t", str(duration),
            "-avoid_negative_ts", "make_zero",
            "-filter_complex", fc,
            "-map", "[out]", "-map", "0:a?",
            "-c:a", "aac", "-c:v", "libx264", "-preset", "fast", "-movflags", "+faststart",
            str(output_path.resolve()),
        ]
    elif crop_mode == "webcam_chat_stack":
        scale_crop = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
        vf_fallback = scale_crop
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-i", str(video_path.resolve()),
            "-t", str(duration),
            "-avoid_negative_ts", "make_zero",
            "-vf", vf_fallback,
            "-c:a", "aac", "-c:v", "libx264", "-preset", "fast", "-movflags", "+faststart",
            str(output_path.resolve()),
        ]
    elif crop_mode in ("bottom_split_stack", "bottom_split_stack_swapped"):
        stack_order = "[br][bl]" if crop_mode == "bottom_split_stack_swapped" else "[bl][br]"
        if center_crop:
            fc = (
                "[0:v]" + center_crop + "[vc];"
                "[vc]split=2[blin][brin];"
                "[blin]crop=in_w/2:in_h/2:0:in_h/2[bl];"
                "[brin]crop=in_w/2:in_h/2:in_w/2:in_h/2[br];"
                f"{stack_order}vstack=inputs=2[stk];"
                "[stk]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[out]"
            )
        else:
            fc = (
                "[0:v]split=2[blin][brin];"
                "[blin]crop=in_w/2:in_h/2:0:in_h/2[bl];"
                "[brin]crop=in_w/2:in_h/2:in_w/2:in_h/2[br];"
                f"{stack_order}vstack=inputs=2[stk];"
                "[stk]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[out]"
            )
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-i", str(video_path.resolve()),
            "-t", str(duration),
            "-avoid_negative_ts", "make_zero",
            "-filter_complex", fc,
            "-map", "[out]", "-map", "0:a?",
            "-c:a", "aac", "-c:v", "libx264", "-preset", "fast", "-movflags", "+faststart",
            str(output_path.resolve()),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_sec),
            "-i", str(video_path.resolve()),
            "-t", str(duration),
            "-avoid_negative_ts", "make_zero",
            "-vf", vf,
            "-c:a", "aac", "-c:v", "libx264", "-preset", "fast", "-movflags", "+faststart",
            str(output_path.resolve()),
        ]
    result = subprocess.run(cmd, cwd=str(out_dir), capture_output=True, text=True)

    # FFmpeg built without libass has no "subtitles" filter → retry without burning captions
    if result.returncode != 0:
        err = (result.stderr or "") + (result.stdout or "")
        if vf_parts is not None and (
            ("No such filter" in err and "subtitles" in err) or "Filter not found" in err
        ):
            vf_no_subs = ",".join(vf_parts[:-1] if (srt_path and srt_path.exists()) else vf_parts)
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start_sec),
                "-i", str(video_path.resolve()),
                "-t", str(duration),
                "-avoid_negative_ts", "make_zero",
                "-vf", vf_no_subs,
                "-c:a", "aac", "-c:v", "libx264", "-preset", "fast", "-movflags", "+faststart",
                str(output_path.resolve()),
            ]
            result = subprocess.run(cmd, cwd=str(out_dir), capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed (exit {result.returncode}): {result.stderr or result.stdout}"
        )
    return output_path


def _probe_fps(video_path: Path) -> float | None:
    """Return source FPS via ffprobe (average frame rate). Returns None on failure."""
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=avg_frame_rate",
                "-of", "csv=p=0",
                str(video_path.resolve()),
            ],
            capture_output=True, text=True, timeout=10,
        )
        raw = (out.stdout or "").strip()
        if "/" in raw:
            num, den = raw.split("/", 1)
            num_f = float(num)
            den_f = float(den) if float(den) != 0 else 1.0
            return num_f / den_f if num_f > 0 else None
        if raw:
            return float(raw)
    except Exception:
        pass
    return None


def make_short_dynamic(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    output_path: Path,
    per_frame_track: "list[TrackPoint]",
    srt_path: Path | None = None,
    width: int = 1080,
    height: int = 1920,
    fps: float | None = None,
) -> Path:
    """Render a 9:16 clip whose crop window follows a per-frame track.

    OpenCV seeks to start_sec, crops each source frame to the aspect ratio
    width:height using (cx, cy) from `per_frame_track` at that frame, scales
    to width x height, and pipes BGR bytes to FFmpeg. FFmpeg muxes the
    original audio for [start_sec, end_sec] and optionally burns `srt_path`.
    """
    import cv2
    import numpy as np

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.01, end_sec - start_sec)

    src_fps = fps if fps and fps > 0 else (_probe_fps(video_path) or 30.0)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV could not open {video_path}")
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if src_w <= 0 or src_h <= 0:
        cap.release()
        raise RuntimeError(f"Invalid source dimensions {src_w}x{src_h}")

    target_aspect = width / height
    crop_h = src_h
    crop_w = int(round(crop_h * target_aspect))
    if crop_w > src_w:
        crop_w = src_w
        crop_h = int(round(crop_w / target_aspect))
    crop_w = max(2, crop_w - (crop_w % 2))
    crop_h = max(2, crop_h - (crop_h % 2))

    max_x = max(0, src_w - crop_w)
    max_y = max(0, src_h - crop_h)
    total_frames = max(1, int(round(duration * src_fps)))

    vf_parts = []
    if srt_path and srt_path.exists():
        vf_parts.append(f"subtitles=filename={_escape_subtitles_path(srt_path.name)}")
    vf = ",".join(vf_parts) if vf_parts else None

    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-s", f"{width}x{height}",
        "-r", f"{src_fps:.6f}",
        "-i", "-",
        "-ss", str(start_sec),
        "-t", str(duration),
        "-i", str(video_path.resolve()),
    ]
    if vf:
        cmd += ["-vf", vf]
    cmd += [
        "-map", "0:v", "-map", "1:a?",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-movflags", "+faststart",
        str(output_path.resolve()),
    ]

    cap.set(cv2.CAP_PROP_POS_MSEC, start_sec * 1000.0)
    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE, cwd=str(output_path.parent),
    )
    written = 0
    last_frame_bytes: bytes | None = None
    try:
        for i in range(total_frames):
            ok, frame = cap.read()
            if not ok or frame is None:
                if last_frame_bytes is None:
                    break
                proc.stdin.write(last_frame_bytes)
                written += 1
                continue
            if i < len(per_frame_track):
                tp = per_frame_track[i]
                cx, cy = tp.cx, tp.cy
            elif per_frame_track:
                tp = per_frame_track[-1]
                cx, cy = tp.cx, tp.cy
            else:
                cx, cy = 0.5, 0.5
            px = int(round(cx * src_w - crop_w / 2.0))
            py = int(round(cy * src_h - crop_h / 2.0))
            px = max(0, min(max_x, px))
            py = max(0, min(max_y, py))
            crop = frame[py:py + crop_h, px:px + crop_w]
            if crop.shape[1] != width or crop.shape[0] != height:
                crop = cv2.resize(crop, (width, height), interpolation=cv2.INTER_LANCZOS4)
            if not crop.flags["C_CONTIGUOUS"]:
                crop = np.ascontiguousarray(crop)
            last_frame_bytes = crop.tobytes()
            proc.stdin.write(last_frame_bytes)
            written += 1
    finally:
        cap.release()
        try:
            proc.stdin.close()
        except Exception:
            pass
    stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
    proc.wait()
    if proc.returncode != 0:
        if vf and ("No such filter" in stderr or "Filter not found" in stderr or "subtitles" in stderr.lower()):
            return make_short_dynamic(
                video_path, start_sec, end_sec, output_path,
                per_frame_track, srt_path=None, width=width, height=height, fps=src_fps,
            )
        raise RuntimeError(
            f"FFmpeg dynamic-crop failed (exit {proc.returncode}, wrote {written}/{total_frames} frames):\n{stderr}"
        )
    return output_path


def _escape_subtitles_path(path: str) -> str:
    """Escape path for use inside FFmpeg subtitles filter."""
    # FFmpeg filter parser misparses subtitles='...' (quotes break it). Use no quotes when safe.
    safe = path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    if not any(c in safe for c in " ,;[]"):
        return safe  # no quotes needed
    return f"'{safe}'"


def write_srt(segments: list[dict], path: Path, start_offset: float = 0.0) -> None:
    """Write SRT from segments; segment times are absolute. start_offset shifts display."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for i, s in enumerate(segments, 1):
        t0 = s["start"] - start_offset
        t1 = s["end"] - start_offset
        if t0 < 0:
            t0 = 0.0
        lines.append(f"{i}")
        lines.append(f"{_ts(t0)} --> {_ts(t1)}")
        lines.append(s.get("text", "").replace("\n", " "))
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _ts(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{int(s):02d},{int(s % 1 * 1000):03d}"
