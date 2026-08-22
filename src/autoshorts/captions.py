"""ASS overlay generation for hooks, captions, and highlighted words."""
from __future__ import annotations

import re
import textwrap
from pathlib import Path


def _ass_time(seconds: float) -> str:
    """Convert seconds to ASS timestamp H:MM:SS.cc."""
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    centis = int(round((secs - int(secs)) * 100))

    if centis >= 100:
        secs = int(secs) + 1
        centis = 0
    else:
        secs = int(secs)

    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _escape_ass_text(value: str) -> str:
    """Escape text so user/AI content cannot inject ASS override tags."""
    value = str(value or "")
    value = value.replace("\\", r"\\")
    value = value.replace("{", r"\{").replace("}", r"\}")
    value = value.replace("\r", " ").replace("\n", r"\N")
    return re.sub(r"\s+", " ", value).strip()


def _wrap_caption(value: str, width: int = 34) -> str:
    """
    Wrap caption text to a maximum approximate line width.

    ASS/libass handles RTL direction; this only inserts line breaks so long
    sentences do not span the full phone screen.
    """
    clean = re.sub(r"\s+", " ", str(value or "")).strip()
    if not clean:
        return ""

    lines = textwrap.wrap(
        clean,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )

    if len(lines) <= 2:
        return r"\N".join(lines)

    # Keep captions compact: merge overflow into line 2.
    return lines[0] + r"\N" + " ".join(lines[1:])


def _highlight_ass_text(
    value: str,
    highlight_words: list[str] | None,
) -> str:
    """Escape caption text and add ASS yellow/bold tags to selected words."""
    raw = re.sub(r"\s+", " ", str(value or "")).strip()
    if not raw:
        return ""

    words = [
        str(word).strip()
        for word in (highlight_words or [])
        if str(word).strip()
    ]

    if not words:
        return _escape_ass_text(_wrap_caption(raw))

    # Longest first prevents a short highlight from swallowing a longer phrase.
    words = sorted(set(words), key=len, reverse=True)
    pattern = re.compile(
        "(" + "|".join(re.escape(word) for word in words) + ")",
        flags=re.IGNORECASE,
    )

    wrapped = _wrap_caption(raw)
    parts = pattern.split(wrapped)

    rendered: list[str] = []
    for part in parts:
        if not part:
            continue

        if pattern.fullmatch(part):
            rendered.append(
                r"{\c&H0000FFFF&\b1}"
                + _escape_ass_text(part)
                + r"{\rCaption}"
            )
        else:
            # Preserve the explicit ASS line break inserted by _wrap_caption.
            escaped = _escape_ass_text(part)
            escaped = escaped.replace(r"\\N", r"\N")
            rendered.append(escaped)

    return "".join(rendered)


def _normalize_segments(
    subtitles: list[dict],
    clip_start: float,
    clip_end: float,
    timebase: str,
) -> list[dict]:
    """
    Convert subtitle timestamps to clip-relative time and prevent overlap.

    `source` timebase: subtitle timestamps refer to the original YouTube video.
    `clip` timebase: subtitle timestamps already start from 0 at the Reel.
    """
    duration = max(0.01, float(clip_end) - float(clip_start))
    normalized: list[dict] = []

    for item in subtitles or []:
        try:
            start = float(item.get("start", 0.0))
            end = float(item.get("end", start))
        except (TypeError, ValueError):
            continue

        text = str(item.get("text", "") or "").strip()
        if not text:
            continue

        if timebase == "source":
            start -= clip_start
            end -= clip_start

        if end <= 0 or start >= duration:
            continue

        start = max(0.0, start)
        end = min(duration, end)

        if end <= start:
            continue

        normalized.append(
            {
                "start": start,
                "end": end,
                "text": text,
            }
        )

    normalized.sort(key=lambda x: (x["start"], x["end"]))

    # YouTube automatic captions commonly overlap. End each line when the next
    # line starts so libass never displays multiple rolling captions at once.
    for i in range(len(normalized) - 1):
        next_start = normalized[i + 1]["start"]
        if next_start > normalized[i]["start"]:
            normalized[i]["end"] = min(
                normalized[i]["end"],
                next_start,
            )

    return [
        item
        for item in normalized
        if item["end"] - item["start"] >= 0.08
    ]


def build_ass_overlay(
    subtitles: list[dict],
    output_path: Path,
    clip_start: float,
    clip_end: float,
    hook: str | None = None,
    highlight_words: list[str] | None = None,
    timebase: str = "source",
    hook_duration: float = 4.0,
    width: int = 1080,
    height: int = 1920,
) -> Path | None:
    """
    Create one ASS file containing:
    - Hook at the top
    - Spoken captions at the bottom
    - Highlighted words inside captions

    Returns None when there is nothing to burn.
    """
    hook = str(hook or "").strip()
    normalized = _normalize_segments(
        subtitles=subtitles,
        clip_start=float(clip_start),
        clip_end=float(clip_end),
        timebase=timebase,
    )

    if not hook and not normalized:
        return None

    duration = max(0.01, float(clip_end) - float(clip_start))
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {int(width)}
PlayResY: {int(height)}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Hook,DejaVu Sans,60,&H00FFFFFF,&H00FFFFFF,&H80000000,&H80000000,-1,0,0,0,100,100,0,0,3,3,0,8,70,70,110,1
Style: Caption,DejaVu Sans,54,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,70,70,165,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""

    events: list[str] = []

    if hook:
        hook_end = min(
            duration,
            max(0.5, float(hook_duration)),
        )
        hook_text = _escape_ass_text(_wrap_caption(hook, width=30))
        hook_text = hook_text.replace(r"\\N", r"\N")

        events.append(
            "Dialogue: 1,"
            f"{_ass_time(0.0)},"
            f"{_ass_time(hook_end)},"
            "Hook,,0,0,0,,"
            f"{hook_text}"
        )

    for item in normalized:
        text = _highlight_ass_text(
            item["text"],
            highlight_words=highlight_words,
        )

        events.append(
            "Dialogue: 0,"
            f"{_ass_time(item['start'])},"
            f"{_ass_time(item['end'])},"
            "Caption,,0,0,0,,"
            f"{text}"
        )

    output_path.write_text(
        header + "\n".join(events) + "\n",
        encoding="utf-8",
    )

    return output_path
