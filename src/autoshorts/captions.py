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


def _text_direction(value: str) -> str:
    """
    Detect paragraph direction from the first strong Unicode character.
    """
    import unicodedata

    for char in str(value or ""):
        bidi = unicodedata.bidirectional(char)

        if bidi in {"R", "AL"}:
            return "rtl"

        if bidi == "L":
            return "ltr"

    return "ltr"


def _prepare_bidi_text(value: str) -> str:
    """
    Prepare mixed RTL/LTR text for libass/FriBidi.

    Important:
    - Do NOT wrap the whole Arabic line in an isolate. That can reorder
      multi-line captions unexpectedly after ASS override tags are inserted.
    - Instead, set paragraph direction with RLM/LRM and isolate only embedded
      opposite-direction runs such as English words inside Arabic.
    """
    value = str(value or "")

    # Unicode controls:
    # RLM = U+200F, LRM = U+200E
    # RLI = U+2067, LRI = U+2066, PDI = U+2069
    RLM = "\u200f"
    LRM = "\u200e"
    RLI = "\u2067"
    LRI = "\u2066"
    PDI = "\u2069"

    direction = _text_direction(value)

    if direction == "rtl":
        # Keep English / numbers / Latin brand names as local LTR runs.
        latin_run = re.compile(
            r"([A-Za-zÀ-ÖØ-öø-ÿ0-9][A-Za-zÀ-ÖØ-öø-ÿ0-9._%+\-/:@#&']*)"
        )
        value = latin_run.sub(
            lambda m: LRI + m.group(1) + PDI,
            value,
        )
        return RLM + value

    # LTR paragraph: isolate embedded Arabic/Hebrew runs.
    rtl_run = re.compile(
        r"([\u0590-\u08FF\uFB1D-\uFDFF\uFE70-\uFEFF]+(?:\s+[\u0590-\u08FF\uFB1D-\uFDFF\uFE70-\uFEFF]+)*)"
    )
    value = rtl_run.sub(
        lambda m: RLI + m.group(1) + PDI,
        value,
    )
    return LRM + value


def _escape_ass_text(value: str) -> str:
    """Escape text so user/AI content cannot inject ASS override tags."""
    value = str(value or "")
    value = value.replace("\\", r"\\")
    value = value.replace("{", r"\{").replace("}", r"\}")
    value = value.replace("\r", " ").replace("\n", r"\N")
    return re.sub(r"\s+", " ", value).strip()


def _wrap_caption(value: str, width: int = 26, max_lines: int = 2) -> str:
    """
    Wrap text for a 1080x1920 Reel without letting it leave the safe area.

    Unlike the old version, overflow is NOT merged into one huge second line.
    Each visible caption is capped to a small number of short lines.
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

    return r"\N".join(lines[:max_lines])


def _split_text_chunks(
    value: str,
    max_chars: int = 48,
) -> list[str]:
    """
    Split a long subtitle into compact readable chunks.

    This is intentionally word-based. Timing for the chunks is assigned
    proportionally inside the source caption interval.
    """
    clean = re.sub(r"\s+", " ", str(value or "")).strip()
    if not clean:
        return []

    words = clean.split()
    chunks: list[str] = []
    current: list[str] = []

    for word in words:
        candidate = " ".join(current + [word])

        if current and len(candidate) > max_chars:
            chunks.append(" ".join(current))
            current = [word]
        else:
            current.append(word)

    if current:
        chunks.append(" ".join(current))

    return chunks


def _expand_long_segments(
    segments: list[dict],
    max_chars: int = 48,
) -> list[dict]:
    """
    Break long caption text into several short on-screen captions.

    The original source timing is preserved as a whole, then divided between
    text chunks by word count. This keeps captions much closer to speech than
    displaying one long sentence for the entire interval.
    """
    expanded: list[dict] = []

    for item in segments:
        text = str(item.get("text", "") or "").strip()
        chunks = _split_text_chunks(text, max_chars=max_chars)

        if len(chunks) <= 1:
            expanded.append(item)
            continue

        start = float(item["start"])
        end = float(item["end"])
        duration = max(0.08, end - start)

        weights = [max(1, len(chunk.split())) for chunk in chunks]
        total_weight = sum(weights)

        cursor = start
        for i, (chunk, weight) in enumerate(zip(chunks, weights)):
            if i == len(chunks) - 1:
                chunk_end = end
            else:
                chunk_end = cursor + duration * (weight / total_weight)

            expanded.append(
                {
                    "start": cursor,
                    "end": chunk_end,
                    "text": chunk,
                }
            )
            cursor = chunk_end

    return expanded


def _highlight_ass_text(
    value: str,
    highlight_words: list[str] | None,
) -> str:
    """
    Render caption text with optional highlighted words.

    Highlight matching happens before Unicode BiDi controls are injected.
    This keeps words like "Fake" matchable while preserving Arabic order.
    """
    raw = re.sub(r"\s+", " ", str(value or "")).strip()
    if not raw:
        return ""

    wrapped = _wrap_caption(
        raw,
        width=26,
        max_lines=2,
    )

    words = [
        str(word).strip()
        for word in (highlight_words or [])
        if str(word).strip()
    ]

    if not words:
        prepared = _prepare_bidi_text(wrapped)
        escaped = _escape_ass_text(prepared)
        return escaped.replace(r"\\N", r"\N")

    words = sorted(set(words), key=len, reverse=True)
    pattern = re.compile(
        "(" + "|".join(re.escape(word) for word in words) + ")",
        flags=re.IGNORECASE,
    )

    parts = pattern.split(wrapped)

    rendered: list[str] = []
    for part in parts:
        if not part:
            continue

        is_highlight = bool(pattern.fullmatch(part))
        prepared = _prepare_bidi_text(part)
        escaped = _escape_ass_text(prepared)
        escaped = escaped.replace(r"\\N", r"\N")

        if is_highlight:
            rendered.append(
                r"{\c&H0000FFFF&\b1}"
                + escaped
                + r"{\rCaption}"
            )
        else:
            rendered.append(escaped)

    return "".join(rendered)


def _normalize_segments(
    subtitles: list[dict],
    clip_start: float,
    clip_end: float,
    timebase: str,
    subtitle_offset: float = 0.0,
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

        # Global timing correction. Negative values display captions earlier.
        start += float(subtitle_offset)
        end += float(subtitle_offset)

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

    normalized = [
        item
        for item in normalized
        if item["end"] - item["start"] >= 0.08
    ]

    return _expand_long_segments(
        normalized,
        max_chars=48,
    )


def build_ass_overlay(
    subtitles: list[dict],
    output_path: Path,
    clip_start: float,
    clip_end: float,
    hook: str | None = None,
    highlight_words: list[str] | None = None,
    timebase: str = "source",
    subtitle_offset: float = 0.0,
    hook_duration: float = 4.0,
    width: int = 1080,
    height: int = 1920,
) -> Path | None:
    """
    Create one ASS file containing:
    - Hook at the top
    - Spoken captions at the bottom
    - Highlighted words inside captions
    - Automatic RTL/LTR direction for multilingual text

    Returns None when there is nothing to burn.
    """
    hook = str(hook or "").strip()
    normalized = _normalize_segments(
        subtitles=subtitles,
        clip_start=float(clip_start),
        clip_end=float(clip_end),
        timebase=timebase,
        subtitle_offset=float(subtitle_offset),
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
Style: Hook,DejaVu Sans,56,&H00FFFFFF,&H00FFFFFF,&H80000000,&H80000000,-1,0,0,0,100,100,0,0,3,3,0,8,95,95,120,1
Style: Caption,DejaVu Sans,48,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,115,115,190,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""

    events: list[str] = []

    if hook:
        hook_end = min(
            duration,
            max(0.5, float(hook_duration)),
        )
        hook_text = _escape_ass_text(_prepare_bidi_text(_wrap_caption(hook, width=24, max_lines=2)))
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
