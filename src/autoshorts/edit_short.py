"""Edit an existing short with a natural-language prompt (e.g. trim start/end) via Ollama + FFmpeg."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import ollama


def get_video_duration(video_path: Path) -> float:
    """Return duration in seconds via ffprobe. Prefer format (container) duration, then video stream."""
    path_str = str(video_path.resolve())
    # 1. Container duration (most reliable for full file length)
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path_str,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            line = out.stdout.strip().splitlines()[0].strip()
            if line:
                d = float(line)
                if d > 0:
                    return d
    except Exception:
        pass
    # 2. Video stream duration (select first video stream only)
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path_str,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0 and out.stdout.strip():
            line = out.stdout.strip().splitlines()[0].strip()
            if line:
                d = float(line)
                if d > 0:
                    return d
    except Exception:
        pass
    return 0.0


def _parse_trim_instructions(user_prompt: str, duration_sec: float, transcript: str, model: str) -> tuple[float, float]:
    """
    Ask Ollama to interpret the user prompt and return (trim_start_seconds, trim_end_seconds).
    trim_start: seconds to remove from the beginning.
    trim_end: seconds to remove from the end.
    """
    prompt = f"""You are a video editor. The user wants to edit a short video.

Video duration: {duration_sec:.1f} seconds.
Transcript (what is said in the video): {transcript[:1500] if transcript else "(no transcript)"}

User instruction: {user_prompt}

Reply with ONLY a JSON object with two numbers:
- "trim_start_seconds": seconds to REMOVE from the BEGINNING (e.g. 2 = remove first 2 seconds). Use 0 for no trim.
- "trim_end_seconds": seconds to REMOVE from the END (e.g. 3 = remove the last 3 seconds). Use 0 for no trim. This is how much to cut OFF the end, not how much to keep.

Examples:
- "cut the last 3 seconds" → {{"trim_start_seconds": 0, "trim_end_seconds": 3}}  (remove 3s from end)
- "cut the first 2 seconds" → {{"trim_start_seconds": 2, "trim_end_seconds": 0}}
- "remove first 2 and last 3" → {{"trim_start_seconds": 2, "trim_end_seconds": 3}}
- "keep the first 22 seconds" → {{"trim_start_seconds": 0, "trim_end_seconds": duration - 22}} (remove everything after 22s)
- "keep first 30 seconds" → {{"trim_start_seconds": 0, "trim_end_seconds": duration - 30}}

You must output actual numbers for trim_end_seconds (e.g. if duration is 45 and user says keep first 22 seconds, output trim_end_seconds: 23). Ensure trim_start_seconds + trim_end_seconds < duration. Reply with ONLY the JSON, nothing else."""

    response = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
    content = (response.message.content or "").strip()
    # Find first { ... }
    start = content.find("{")
    if start < 0:
        return 0.0, 0.0
    end = content.rfind("}") + 1
    if end <= start:
        return 0.0, 0.0
    try:
        data = json.loads(content[start:end])
        ts = float(data.get("trim_start_seconds", 0) or 0)
        te = float(data.get("trim_end_seconds", 0) or 0)
        ts = max(0, min(ts, duration_sec))
        te = max(0, min(te, duration_sec))
        if ts + te >= duration_sec:
            ts, te = 0.0, 0.0
        return ts, te
    except (json.JSONDecodeError, TypeError, ValueError):
        return 0.0, 0.0


def edit_short_with_prompt(
    video_path: Path,
    output_path: Path,
    user_prompt: str,
    transcript: str = "",
    model: str = "mistral",
) -> tuple[bool, str]:
    """
    Interpret user_prompt (e.g. "cut the last 3 seconds") with Ollama, then trim the video with FFmpeg.
    Saves to output_path. Returns (success, message).
    """
    video_path = Path(video_path)
    output_path = Path(output_path)
    duration = get_video_duration(video_path)
    if duration <= 0:
        return False, "Could not read video duration."

    trim_start, trim_end = _parse_trim_instructions(user_prompt, duration, transcript or "", model)
    if trim_start <= 0 and trim_end <= 0:
        return False, "AI did not suggest any trim (or could not parse). Try being explicit, e.g. 'cut the last 3 seconds'."

    # New duration after trim
    new_duration = duration - trim_start - trim_end
    if new_duration <= 0:
        return False, "Trim would remove the entire video; aborting."

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Use -to (end timestamp) for accurate length; -ss before -i for fast seek
    end_sec = duration - trim_end
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(trim_start),
        "-i", str(video_path.resolve()),
        "-to", str(end_sec),
        "-c", "copy",
        "-avoid_negative_ts", "make_zero",
        str(output_path.resolve()),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        return False, f"FFmpeg failed: {result.stderr or result.stdout or 'unknown error'}"
    return True, f"Saved to {output_path.name} (removed {trim_start:.1f}s from start, {trim_end:.1f}s from end)."
