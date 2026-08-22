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
    """
    Escape text for ASS while preserving intentional \\N line breaks.

    We temporarily replace ASS line breaks with a private placeholder,
    escape user text, then restore the real ASS \\N control sequence.
    """
    value = str(value or "")

    placeholder = "\uFFF0ASS_LINE_BREAK\uFFF1"

    # Preserve intentional ASS hard line breaks inserted by _wrap_caption.
    value = value.replace(r"\N", placeholder)

    # Normalize actual newlines from input text.
    value = value.replace("\r", " ").replace("\n", " ")

    # Escape ASS-sensitive characters.
    value = value.replace("\\", r"\\")
    value = value.replace("{", r"\{").replace("}", r"\}")

    # Collapse ordinary whitespace without touching the placeholder.
    value = re.sub(r"[ \t]+", " ", value).strip()

    # Restore exactly one ASS hard line-break sequence.
    value = value.replace(placeholder, r"\N")

    return value


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


def _caption_profile(
    text: str,
    duration: float,
) -> dict:
    """
    Caption Timing Normalizer v2.

    Estimate speaking speed from the timed transcript segment itself and
    choose a suitable amount of text per on-screen caption.

    No AI rewriting happens here. The original transcript words and the
    original segment time window are preserved.
    """
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    words = clean.split()
    word_count = len(words)
    duration = max(0.10, float(duration))

    words_per_second = word_count / duration if word_count else 0.0

    # Faster speech -> slightly more frequent caption changes.
    if words_per_second >= 3.3:
        target_duration = 1.15
        max_words = 5
        max_chars = 30
    elif words_per_second >= 2.5:
        target_duration = 1.35
        max_words = 6
        max_chars = 34
    elif words_per_second >= 1.7:
        target_duration = 1.60
        max_words = 7
        max_chars = 38
    else:
        target_duration = 1.90
        max_words = 7
        max_chars = 40

    return {
        "words_per_second": words_per_second,
        "target_duration": target_duration,
        "max_words": max_words,
        "max_chars": max_chars,
    }


def _split_text_chunks(
    value: str,
    max_words: int = 6,
    max_chars: int = 34,
) -> list[str]:
    """
    Split transcript text into readable chunks without changing its wording.

    Preference order:
    1) punctuation boundary
    2) word-count limit
    3) character-width limit
    """
    clean = re.sub(r"\s+", " ", str(value or "")).strip()
    if not clean:
        return []

    words = clean.split()
    chunks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        if current:
            chunks.append(" ".join(current).strip())
            current = []

    for word in words:
        candidate = " ".join(current + [word])

        if current and (
            len(current) >= max_words
            or len(candidate) > max_chars
        ):
            flush()

        current.append(word)

        # A natural punctuation boundary is a good place to change captions,
        # but avoid flashing captions containing only one word.
        if (
            len(current) >= 3
            and re.search(r"[.!?؟,:;]$", word)
        ):
            flush()

    flush()
    return chunks


def _chunk_weight(text: str) -> float:
    """
    Approximate how much of the parent segment's speaking time belongs to
    this chunk. Word count is primary; character count provides a small
    correction for long words.
    """
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    words = clean.split()
    chars = len(clean.replace(" ", ""))

    return max(
        1.0,
        len(words) + (chars * 0.025),
    )


def _expand_long_segments(
    segments: list[dict],
) -> list[dict]:
    """
    Adaptive Caption Timing Normalizer v2.

    For each real timed transcript segment:
    - measure its speech rate,
    - choose caption density automatically,
    - split only its original words,
    - distribute the original timing proportionally,
    - preserve the parent's exact start/end boundaries.

    This does NOT invent or paraphrase subtitle text.
    """
    expanded: list[dict] = []

    for item in segments:
        text = re.sub(
            r"\s+",
            " ",
            str(item.get("text", "") or ""),
        ).strip()

        if not text:
            continue

        start = float(item["start"])
        end = float(item["end"])
        duration = max(0.08, end - start)

        profile = _caption_profile(
            text=text,
            duration=duration,
        )

        chunks = _split_text_chunks(
            text,
            max_words=profile["max_words"],
            max_chars=profile["max_chars"],
        )

        if len(chunks) <= 1:
            expanded.append(
                {
                    "start": start,
                    "end": end,
                    "text": text,
                }
            )
            continue

        weights = [_chunk_weight(chunk) for chunk in chunks]
        total_weight = sum(weights) or 1.0

        cursor = start

        for index, (chunk, weight) in enumerate(
            zip(chunks, weights)
        ):
            if index == len(chunks) - 1:
                chunk_end = end
            else:
                share = duration * (weight / total_weight)
                chunk_end = min(end, cursor + share)

            # Prevent extremely short flashes. If there is not enough room,
            # the final chunk still closes exactly at the parent end.
            if (
                index < len(chunks) - 1
                and chunk_end - cursor < 0.45
            ):
                chunk_end = min(end, cursor + 0.45)

            if chunk_end > cursor + 0.08:
                expanded.append(
                    {
                        "start": cursor,
                        "end": chunk_end,
                        "text": chunk,
                    }
                )

            cursor = chunk_end

            if cursor >= end:
                break

    return expanded


def _render_bidi_line(
    line: str,
    highlight_words: list[str] | None = None,
) -> str:
    """
    Render ONE visual line.

    We never pass the ASS hard line-break token (\\N) through the BiDi
    processor. This prevents it from being interpreted as literal text.
    """
    line = str(line or "").strip()
    if not line:
        return ""

    words = [
        str(word).strip()
        for word in (highlight_words or [])
        if str(word).strip()
    ]

    if not words:
        return _escape_ass_text(
            _prepare_bidi_text(line)
        )

    words = sorted(set(words), key=len, reverse=True)

    pattern = re.compile(
        "(" + "|".join(re.escape(word) for word in words) + ")",
        flags=re.IGNORECASE,
    )

    parts = pattern.split(line)
    rendered: list[str] = []

    for part in parts:
        if not part:
            continue

        prepared = _prepare_bidi_text(part)
        escaped = _escape_ass_text(prepared)

        if pattern.fullmatch(part):
            rendered.append(
                r"{\c&H0000FFFF&\b1}"
                + escaped
                + r"{\rCaption}"
            )
        else:
            rendered.append(escaped)

    return "".join(rendered)


def _render_multiline_text(
    value: str,
    highlight_words: list[str] | None = None,
) -> str:
    """
    Render wrapped text line-by-line, then join using a real ASS \\N token.
    """
    lines = str(value or "").split(r"\N")

    rendered_lines = [
        _render_bidi_line(
            line,
            highlight_words=highlight_words,
        )
        for line in lines
        if str(line).strip()
    ]

    return r"\N".join(rendered_lines)


def _highlight_ass_text(
    value: str,
    highlight_words: list[str] | None,
) -> str:
    """
    Wrap captions safely, preserve RTL/LTR, and highlight selected words.
    """
    raw = re.sub(r"\s+", " ", str(value or "")).strip()
    if not raw:
        return ""

    wrapped = _wrap_caption(
        raw,
        width=22,
        max_lines=2,
    )

    return _render_multiline_text(
        wrapped,
        highlight_words=highlight_words,
    )


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
Style: Caption,DejaVu Sans,46,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,145,145,235,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""

    events: list[str] = []

    if hook:
        hook_end = min(
            duration,
            max(0.5, float(hook_duration)),
        )
        hook_text = _render_multiline_text(
            _wrap_caption(
                hook,
                width=22,
                max_lines=2,
            ),
            highlight_words=None,
        )

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
