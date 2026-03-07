"""Use local Ollama LLM to pick best N segments for shorts from transcript chunks."""
from __future__ import annotations

import json
import re
from typing import Any

import ollama

# How much of each chunk's text to show the LLM (need enough to see hook + payoff)
CHUNK_TEXT_MAX_CHARS = 700
TITLE_CHUNK_MAX_CHARS = 800
# For segment-based selection: max segments to send (avoid token overflow), chars per segment
SEGMENT_MAX_CHARS = 100
SEGMENT_LIST_MAX = 400


def select_highlights_from_segments(
    segments: list[dict],
    max_clips: int = 5,
    model: str = "mistral",
    min_duration: float = 15.0,
    max_duration: float = 60.0,
) -> list[dict]:
    """
    Ask the LLM to find ALL moments in the transcript that would make a good short.
    Works on raw Whisper segments (fine-grained); returns 1 to max_clips clips based on content.
    Each clip is a range of consecutive segment indices. No fixed time chunks.
    """
    if not segments:
        return []
    # Limit length for context window; show index, start, end, text (truncated)
    use = segments[:SEGMENT_LIST_MAX]
    lines = []
    for i, s in enumerate(use):
        start, end = s["start"], s["end"]
        dur = end - start
        text = (s.get("text") or "").strip()[:SEGMENT_MAX_CHARS]
        if (s.get("text") or "").strip() and len((s.get("text") or "").strip()) > SEGMENT_MAX_CHARS:
            text += "..."
        lines.append(f"[{i}] {start:.1f}s-{end:.1f}s ({dur:.0f}s) {text}")
    transcript_block = "\n".join(lines)

    prompt = f"""You are an expert at finding viral moments in long-form video for short-form clips (YouTube Shorts, TikTok, Reels).

Below is a transcript split into short segments with [index] start-end (duration) and text.

TASK: Find EVERY moment that would make a good short. Each moment = a range of consecutive segments (start_idx through end_idx inclusive).
- Return between 1 and {max_clips} moments. If the video has 5 great moments, return 5. If it only has 2, return 2. Do NOT pad with weak moments to reach {max_clips}.
- Each moment must be between {min_duration:.0f} and {max_duration:.0f} seconds. Compute duration as (segment end_idx end time) minus (segment start_idx start time). Prefer 15–35s when the moment fits; use up to {max_duration:.0f}s when the context needs it (e.g. full story beat, extended bit).
- Each moment must be SELF-CONTAINED: strong hook (question, bold claim, surprise) and clear payoff (punch line, conclusion, reveal). Viewer needs no prior context.
- Prefer the SHORTEST range that contains the full moment. End at the payoff, not after.
- Ranges must NOT overlap. Use 0-based segment indices.

Reply with ONLY a JSON array of objects: [{{"start_idx": 0, "end_idx": 3}}, {{"start_idx": 8, "end_idx": 10}}, ...]
No other text, no markdown.

Transcript (index, time range, duration, text):
{transcript_block}

JSON array of 1 to {max_clips} moments (start_idx, end_idx):"""

    response = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
    content = (response.message.content or "").strip()
    start_pos = content.find("[")
    if start_pos < 0:
        return _fallback_from_segments(segments, max_clips)
    depth = 0
    end_pos = -1
    for i, ch in enumerate(content[start_pos:], start_pos):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end_pos = i
                break
    if end_pos < 0:
        return _fallback_from_segments(segments, max_clips)
    try:
        arr = json.loads(content[start_pos : end_pos + 1])
    except json.JSONDecodeError:
        return _fallback_from_segments(segments, max_clips)
    if not isinstance(arr, list) or not arr:
        return _fallback_from_segments(segments, max_clips)
    out = []
    n = len(use)
    for item in arr:
        if not isinstance(item, dict):
            continue
        si = item.get("start_idx")
        ei = item.get("end_idx")
        if si is None or ei is None:
            continue
        try:
            si, ei = int(si), int(ei)
        except (TypeError, ValueError):
            continue
        if si < 0 or ei >= n or si > ei:
            continue
        s0, s1 = use[si], use[ei]
        start_sec = s0["start"]
        end_sec = s1["end"]
        dur = end_sec - start_sec
        if dur < min_duration or dur > max_duration + 10:
            continue
        texts = [use[j].get("text", "") for j in range(si, ei + 1)]
        out.append({
            "start": start_sec,
            "end": end_sec,
            "text": " ".join(texts).strip(),
        })
    if not out:
        return _fallback_from_segments(segments, max_clips)
    # Sort by start time and remove overlaps (keep earlier)
    out.sort(key=lambda x: x["start"])
    kept = []
    for c in out:
        if any(c["start"] < k["end"] and c["end"] > k["start"] for k in kept):
            continue
        kept.append(c)
    return kept[:max_clips]


def _fallback_from_segments(segments: list[dict], max_clips: int) -> list[dict]:
    """Fallback: take first max_clips non-overlapping windows of ~20s from segments."""
    if not segments or max_clips <= 0:
        return []
    out = []
    video_end = max(s["end"] for s in segments)
    step = max(20.0, (video_end - 5) / max_clips)
    start = 5.0
    for _ in range(max_clips):
        if start >= video_end - 15:
            break
        end = min(start + 25, video_end)
        texts = [s.get("text", "") for s in segments if s["end"] > start and s["start"] < end]
        out.append({
            "start": start,
            "end": end,
            "text": " ".join(texts).strip(),
        })
        start = end + 5
    return out


def select_highlights(
    chunks: list[dict],
    num_clips: int = 3,
    model: str = "mistral",
    min_duration: float = 15.0,
    max_duration: float = 60.0,
) -> list[dict]:
    """
    Ask Ollama to pick the best num_clips moments and their exact boundaries (start/end chunk index).
    Returns list of chunk dicts with "start", "end", "text" — each clip can span 1 to several
    micro-chunks so length matches the moment (15–60s), not always 60s.
    """
    if not chunks:
        return []
    lines = []
    for i, c in enumerate(chunks):
        start, end = c["start"], c["end"]
        dur = end - start
        text_preview = c["text"][:CHUNK_TEXT_MAX_CHARS]
        if len(c["text"]) > CHUNK_TEXT_MAX_CHARS:
            text_preview += "..."
        lines.append(f"[{i}] {start:.1f}s - {end:.1f}s ({dur:.0f}s): {text_preview}")
    transcript_block = "\n".join(lines)

    prompt = f"""You are an expert at choosing the best moments from a long-form video for short-form clips (YouTube Shorts, TikTok, Reels).

Your job: pick exactly {num_clips} highlights. For EACH highlight you must choose a RANGE of consecutive segments (by index). The range is the exact clip: from segment start_idx through end_idx inclusive.

CRITICAL RULES:
- Reply with ONLY a JSON array of objects, each with "start_idx" and "end_idx" (integers). Example: [{{"start_idx": 0, "end_idx": 1}}, {{"start_idx": 5, "end_idx": 7}}]. No other text.
- Each highlight must be between {min_duration:.0f} and {max_duration:.0f} seconds. Use the duration in parentheses to compute length (sum or use end - start of the range). Prefer 15–35s when possible; use up to {max_duration:.0f}s when the moment needs it. End the range at the payoff (punch line, conclusion), not before and not long after.
- Pick moments that:
  • Start with a strong hook (question, bold claim, surprise) and end with a payoff (punch line, conclusion, reveal).
  • Are self-contained (viewer needs no prior context).
- Avoid: mid-sentence starts, segments that are mostly setup with no payoff, filler, or reading long text (e.g. tweets) with no reaction.
- Ranges must not overlap. Use 0-based indices from the list below.

Transcript segments (index, time range, duration, text):
{transcript_block}

Reply with ONLY a JSON array of {num_clips} objects: [{{"start_idx": n, "end_idx": m}}, ...]. Nothing else."""

    response = ollama.chat(model=model, messages=[{"role": "user", "content": prompt}])
    content = (response.message.content or "").strip()
    # Parse array of {start_idx, end_idx}
    start_pos = content.find("[")
    if start_pos < 0:
        return chunks[:num_clips]
    depth = 0
    end_pos = -1
    for i, ch in enumerate(content[start_pos:], start_pos):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end_pos = i
                break
    if end_pos < 0:
        return chunks[:num_clips]
    try:
        arr = json.loads(content[start_pos : end_pos + 1])
    except json.JSONDecodeError:
        return chunks[:num_clips]
    if not isinstance(arr, list):
        return chunks[:num_clips]
    out = []
    # Fallback: if LLM returned plain indices [2, 5, 7]
    if arr and isinstance(arr[0], int):
        for i in arr:
            if isinstance(i, int) and 0 <= i < len(chunks):
                c = chunks[i]
                out.append({"start": c["start"], "end": c["end"], "text": c["text"]})
        return out if out else chunks[:num_clips]
    for item in arr:
        if not isinstance(item, dict):
            continue
        si = item.get("start_idx")
        ei = item.get("end_idx")
        if si is None or ei is None:
            continue
        try:
            si, ei = int(si), int(ei)
        except (TypeError, ValueError):
            continue
        if si < 0 or ei >= len(chunks) or si > ei:
            continue
        c0, c1 = chunks[si], chunks[ei]
        start_sec = c0["start"]
        end_sec = c1["end"]
        texts = [chunks[j]["text"] for j in range(si, ei + 1)]
        out.append({
            "start": start_sec,
            "end": end_sec,
            "text": " ".join(texts).strip(),
        })
    # If LLM returned fewer than num_clips, fill with non-overlapping chunks
    if len(out) < num_clips and len(chunks) > len(out):
        def overlaps(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
            return a_start < b_end and a_end > b_start
        for i in range(len(chunks)):
            if len(out) >= num_clips:
                break
            c = chunks[i]
            if any(overlaps(c["start"], c["end"], s["start"], s["end"]) for s in out):
                continue
            out.append({"start": c["start"], "end": c["end"], "text": c["text"]})
    return out[:num_clips] if out else chunks[:num_clips]


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
