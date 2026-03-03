"""Cut segments, crop to 9:16, and burn captions using FFmpeg."""
from __future__ import annotations

import subprocess
from pathlib import Path


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
) -> Path:
    """
    Extract [start_sec, end_sec], crop to height x width (9:16), optionally burn SRT.
    crop_mode: "center" = center crop (or follow focus_x);
      "bottom_strip_rotate" = bottom strip rotated 90° CW (left→top, right→bottom);
      "bottom_split_stack" = bottom-left quadrant on top, bottom-right on bottom, stacked (no rotation).
      "bottom_split_stack_swapped" = bottom-right on top, bottom-left on bottom.
      "webcam_chat_stack" = webcam (face) region on top, chat (right strip) on bottom; requires webcam_bbox and chat_bbox.
    """
    duration = end_sec - start_sec
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Optional pre-crop used for screen recordings where a vertical short
    # is centered on the screen (e.g. X / TikTok / YouTube Shorts in a browser).
    # We keep a tall, narrow region around the center to throw away browser chrome
    # and side gutters before applying the main 9:16 crop.
    if focus_region == "center":
        # 50% of width, 90% of height, centered.
        center_crop = "crop=in_w*0.5:in_h*0.9:in_w*0.25:in_h*0.05"
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
    else:
        # Scale to target height while preserving aspect, then crop to 9:16.
        scale = f"scale=-1:{height}:force_original_aspect_ratio=increase"
        if focus_x is None:
            crop = f"crop={width}:{height}:(in_w-{width})/2:(in_h-{height})/2"
        else:
            cx_expr = f"in_w*{focus_x:.3f}"
            x_expr = f"min(max({cx_expr}-{width/2}, 0), in_w-{width})"
            crop = f"crop={width}:{height}:{x_expr}:(in_h-{height})/2"
        vf_parts = []
        if manual_crop:
            vf_parts.append(manual_crop)
        elif center_crop:
            vf_parts.append(center_crop)
        vf_parts.extend([scale, crop])
    if srt_path and srt_path.exists():
        srt_name = srt_path.name
        if vf_parts is not None:
            vf_parts.append(f"subtitles=filename={_escape_subtitles_path(srt_name)}")
    vf = ",".join(vf_parts) if vf_parts else None

    out_dir = output_path.parent
    if crop_mode == "webcam_chat_stack" and webcam_bbox is not None and chat_bbox is not None:
        wl, wt, wr, wb = webcam_bbox
        cl, ct, cr, cb = chat_bbox
        fc = (
            f"[0:v]crop=in_w*{wr-wl:.4f}:in_h*{wb-wt:.4f}:in_w*{wl:.4f}:in_h*{wt:.4f}[wc];"
            "[wc]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[wc2];"
            f"[0:v]crop=in_w*{cr-cl:.4f}:in_h*{cb-ct:.4f}:in_w*{cl:.4f}:in_h*{ct:.4f}[ch];"
            "[ch]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960[ch2];"
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
        # Detection failed: fall back to center crop
        scale = f"scale=-1:{height}:force_original_aspect_ratio=increase"
        crop = f"crop={width}:{height}:(in_w-{width})/2:(in_h-{height})/2"
        vf_fallback = ",".join([scale, crop])
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
