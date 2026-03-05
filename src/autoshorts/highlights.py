"""Use local Ollama LLM to pick best N segments for shorts from transcript chunks."""
from __future__ import annotations

import json
import re
from typing import Any

import ollama

# How much of each chunk's text to show the LLM (need enough to see hook + payoff)
CHUNK_TEXT_MAX_CHARS = 700
TITLE_CHUNK_MAX_CHARS = 800


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
    # Build a text representation for the LLM (enough text to judge hook and payoff)
    lines = []
    for i, c in enumerate(chunks):
        start, end = c["start"], c["end"]
        dur = end - start
        text_preview = c["text"][:CHUNK_TEXT_MAX_CHARS]
        if len(c["text"]) > CHUNK_TEXT_MAX_CHARS:
            text_preview += "..."
        lines.append(f"[{i}] {start:.1f}s - {end:.1f}s ({dur:.0f}s): {text_preview}")
    transcript_block = "\n".join(lines)

    prompt = f"""You are an expert at choosing the best moments from a long-form video to turn into short-form clips (YouTube Shorts, TikTok, Reels). Your job is to pick segments that work as STANDALONE clips: a viewer who sees only that clip should get a complete idea and a satisfying payoff.

RULES:
- Choose exactly {num_clips} segments. Reply with ONLY a JSON array of their indices, e.g. [2, 5, 9]. No other text, no explanation. Use 0-based indices from the list below.
- Prefer segments that:
  • Start with a strong hook (question, bold claim, surprise, or clear topic in the first 1–2 sentences).
  • Contain a complete thought or story: setup and payoff (punch line, conclusion, reveal) within the same segment.
  • Have an emotional peak, a clear "aha" moment, or a memorable quote.
  • Are between {min_duration:.0f}s and {max_duration:.0f}s when possible.
- Avoid segments that:
  • Start mid-sentence or depend on something said earlier in the video.
  • Are mostly setup with no payoff in that segment.
  • Are filler, repetition, or long pauses.
  • Start with weak intros like "So...", "Anyway...", "Um...", or end abruptly mid-thought.
- Prefer variety: if picking multiple, choose different types of moments (e.g. one hook, one emotional, one surprising) rather than three similar ones.
- Good clip: opens with a clear hook, has a payoff (punch line, reveal, conclusion) before the end. Bad clip: long wind-up, no payoff in the segment, or cuts off right before the key line.
- Segments are built to break at sentence boundaries. Prefer ones where the text clearly starts a complete thought and ends with a conclusion or punch line (not trailing off or cut mid-sentence).

Transcript segments (index, time range, duration, text):
{transcript_block}

Reply with ONLY a JSON array of indices, e.g. [1, 4, 7]. Nothing else."""

    response = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
    content = (response.message.content or "").strip()
    # Extract JSON array
    match = re.search(r"\[[\d,\s]*\]", content)
    if not match:
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


def generate_titles_for_chunks(chunks: list[dict], model: str = "mistral") -> list[str]:
    """
    For each transcript chunk, generate a short catchy title (e.g. for YouTube Shorts).
    Returns a list of strings, one per chunk; falls back to "Short 1", "Short 2" on failure.
    """
    if not chunks:
        return []
    lines = []
    for i, c in enumerate(chunks):
        text = (c.get("text") or "").strip()[:TITLE_CHUNK_MAX_CHARS]
        lines.append(f"[Clip {i + 1}]\n{text}")
    block = "\n\n".join(lines)

    prompt = f"""You are writing titles for short-form video clips (YouTube Shorts, TikTok, Reels). For each clip below, the transcript is given. Write ONE short, catchy title for each clip.

RULES:
- One title per clip, in the same order as the clips ([Clip 1], [Clip 2], ...).
- Each title: 3–8 words, catchy and accurate to the content. No quotes, no colons. Make it something that would get clicks.
- Match the tone: if the clip is serious, the title can be bold; if it's funny, the title can be punchy or playful.
- Reply with ONLY a JSON array of strings, e.g. ["First title here", "Second title here"]. Nothing else.

Clips:
{block}

Reply with ONLY a JSON array of {len(chunks)} title strings, in order. Nothing else."""

    try:
        response = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
        content = (response.message.content or "").strip()
        match = re.search(r'\[[\s\S]*?\]', content)
        if not match:
            return [f"Short {i + 1}" for i in range(len(chunks))]
        arr = json.loads(match.group())
        if not isinstance(arr, list):
            return [f"Short {i + 1}" for i in range(len(chunks))]
        titles = []
        for i in range(len(chunks)):
            if i < len(arr) and isinstance(arr[i], str) and arr[i].strip():
                t = arr[i].strip()[:80]
                titles.append(t)
            else:
                titles.append(f"Short {i + 1}")
        return titles
    except Exception:
        return [f"Short {i + 1}" for i in range(len(chunks))]
