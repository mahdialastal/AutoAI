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


def segments_to_timestamped_chunks(
    segments: list[dict], chunk_duration_sec: float = 30.0
) -> list[dict]:
    """
    Group consecutive segments into chunks of ~chunk_duration_sec.
    Each chunk: {"start": float, "end": float, "text": str}.
    """
    if not segments:
        return []
    chunks: list[dict] = []
    cur_start = segments[0]["start"]
    cur_end = cur_start
    cur_text: list[str] = []
    for s in segments:
        cur_end = s["end"]
        cur_text.append(s["text"])
        if cur_end - cur_start >= chunk_duration_sec:
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
