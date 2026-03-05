"""Transcribe video with faster-whisper and return segments with timestamps."""
from __future__ import annotations

from pathlib import Path


def transcribe(
    video_path: Path,
    model_size: str = "base",
    language: str | None = None,
    device: str = "auto",
) -> tuple[str, list[dict]]:
    """
    Return (full_text, segments) where segments are
    [{"start": float, "end": float, "text": str}, ...].
    """
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device=device, compute_type="float32")
    segments_iter, info = model.transcribe(
        str(video_path),
        language=language,
        word_timestamps=False,
        vad_filter=True,
    )
    segments: list[dict] = []
    full_parts: list[str] = []
    for s in segments_iter:
        seg = {"start": s.start, "end": s.end, "text": (s.text or "").strip()}
        segments.append(seg)
        if seg["text"]:
            full_parts.append(seg["text"])
    full_text = " ".join(full_parts)
    return full_text, segments


def _is_sentence_end(text: str) -> bool:
    """True if text looks like the end of a sentence (so we can break chunks here)."""
    if not text:
        return False
    t = text.strip().rstrip()
    return bool(t and (t[-1] in ".?!" or t.endswith("…")))


def segments_to_timestamped_chunks(
    segments: list[dict], chunk_duration_sec: float = 30.0
) -> list[dict]:
    """
    Group consecutive segments into chunks of ~chunk_duration_sec, breaking only at
    sentence boundaries when possible so clips don't start mid-sentence or cut off
    before the end of a thought.
    Each chunk: {"start": float, "end": float, "text": str}.
    """
    if not segments:
        return []
    chunks: list[dict] = []
    min_dur = chunk_duration_sec * 0.7   # at least ~21s before we consider breaking
    max_dur = chunk_duration_sec * 1.4   # force break by ~42s to avoid huge chunks
    cur_start = segments[0]["start"]
    cur_end = cur_start
    cur_text: list[str] = []
    for s in segments:
        cur_end = s["end"]
        cur_text.append(s["text"])
        dur = cur_end - cur_start
        at_sentence_end = _is_sentence_end(s["text"])
        over_min = dur >= min_dur
        over_max = dur >= max_dur
        if over_min and (at_sentence_end or over_max):
            chunks.append({
                "start": cur_start,
                "end": cur_end,
                "text": " ".join(cur_text).strip(),
            })
            cur_start = cur_end
            cur_text = []
    if cur_text or cur_end > cur_start:
        chunks.append({
            "start": cur_start,
            "end": cur_end,
            "text": " ".join(cur_text).strip(),
        })
    return chunks
