"""Use local Ollama LLM to pick best N segments for shorts from transcript chunks."""
from __future__ import annotations

import json
import re
from typing import Any

import ollama


def select_highlights(
    chunks: list[dict],
    num_clips: int = 3,
    model: str = "mistral",
    min_duration: float = 15.0,
    max_duration: float = 60.0,
) -> list[dict]:
    """
    Ask Ollama to pick the best num_clips chunks that would make viral shorts.
    Returns list of chunk dicts with "start", "end", "text" (subset of chunks).
    """
    if not chunks:
        return []
    # Build a simple text representation for the LLM
    lines = []
    for i, c in enumerate(chunks):
        start, end = c["start"], c["end"]
        dur = end - start
        lines.append(f"[{i}] {start:.1f}s - {end:.1f}s ({dur:.0f}s): {c['text'][:200]}")
    transcript_block = "\n".join(lines)

    prompt = f"""You are an expert at picking the most engaging moments from a video transcript for short-form clips (YouTube Shorts, TikTok, Reels).

Given this transcript with segment indices and timestamps, choose exactly {num_clips} segments that would make the best viral shorts. Prefer:
- Strong hooks or surprising statements
- Clear, self-contained ideas
- Emotional or punchy moments
- Segments between {min_duration:.0f} and {max_duration:.0f} seconds when possible

Transcript:
{transcript_block}

Reply with ONLY a JSON array of segment indices, e.g. [2, 5, 7]. No other text."""

    response = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
    content = (response.message.content or "").strip()
    # Extract JSON array
    match = re.search(r"\[[\d,\s]*\]", content)
    if not match:
        # Fallback: take first N chunks
        return chunks[:num_clips]
    try:
        indices = json.loads(match.group())
    except json.JSONDecodeError:
        return chunks[:num_clips]
    out = []
    for i in indices:
        if isinstance(i, int) and 0 <= i < len(chunks):
            out.append(chunks[i])
    return out if out else chunks[:num_clips]
