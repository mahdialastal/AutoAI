"""Orchestrate: download → transcribe → highlight selection → export shorts."""
from __future__ import annotations

from pathlib import Path

from .download import get_video_path
from .export import make_short, write_srt
from .highlights import select_highlights_from_segments, generate_titles_for_chunks
from .transcribe import transcribe
from .focus import estimate_focus_x, detect_webcam_chat_regions, suggest_layout
from .event_focus import estimate_event_crop, should_use_event_fallback


def run_pipeline(
    source: str,
    output_dir: str | Path = "./shorts_out",
    download_dir: str | Path | None = None,
    num_clips: int = 3,
    whisper_model: str = "base",
    ollama_model: str = "mistral",
    chunk_duration: float = 15.0,
    min_duration: float = 15.0,
    max_duration: float = 60.0,
    clip_end_padding_sec: float = 3.0,
    burn_captions: bool = True,
    smart_crop: bool = True,
    crop_mode: str = "bottom_split_stack",
    focus_region: str = "full",
    letterbox_full_width: bool = False,
    manual_top: float | None = None,
    manual_bottom: float | None = None,
    manual_left: float | None = None,
    manual_right: float | None = None,
    manual_webcam_bbox: tuple[float, float, float, float] | None = None,
    manual_chat_bbox: tuple[float, float, float, float] | None = None,
    manual_center_bbox: tuple[float, float, float, float] | None = None,
) -> tuple[list[Path], list[str], str, list[str]]:
    """
    Run the full pipeline: get video → transcribe → pick highlights → export shorts.
    Returns (paths, titles, full_transcript, list of per-short transcript text).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dld_dir = Path(download_dir) if download_dir is not None else None

    # 1. Get video
    video_path = get_video_path(source, download_dir=dld_dir)

    # 2. Transcribe
    full_text, segments = transcribe(video_path, model_size=whisper_model)
    if not segments:
        return ([], [], "", [])

    # 3. Select highlights from raw segments (dynamic count, semantic boundaries)
    selected = select_highlights_from_segments(
        segments,
        max_clips=num_clips,
        model=ollama_model,
        min_duration=min_duration,
        max_duration=max_duration,
    )
    titles = generate_titles_for_chunks(selected, model=ollama_model)
    # Ensure we have one title per selected clip
    while len(titles) < len(selected):
        titles.append(f"Short {len(titles) + 1}")
    titles = titles[: len(selected)]
    # Align clip boundaries to full sentences, extend end for punch lines,
    # and enforce a hard max_duration for shorts.
    video_duration_sec = max(s["end"] for s in segments) if segments else 0.0
    max_start_walkback_sec = 12.0  # don't pull start back more than this
    max_start_walkback_segments = 6

    for chunk in selected:
        start_sec = chunk["start"]
        end_sec = chunk["end"]
        # Trim start back to a sentence boundary (don't start mid-sentence).
        # Find first segment overlapping the clip.
        i0 = None
        for i, s in enumerate(segments):
            if s["end"] <= start_sec:
                continue
            if s["start"] >= end_sec:
                break
            i0 = i
            break
        if i0 is not None and i0 > 0:
            original_start = start_sec
            walked = 0
            while i0 > 0 and walked < max_start_walkback_segments:
                prev_text = (segments[i0 - 1].get("text") or "").strip().rstrip()
                # Stop at sentence end (previous segment ends with .?!)
                if prev_text and prev_text[-1] in ".?!…":
                    break
                # Or stop if this segment looks like a sentence start (starts with capital)
                cur_text = (segments[i0].get("text") or "").strip()
                if cur_text and cur_text[0].isupper():
                    break
                # Don't walk back more than max_start_walkback_sec
                candidate_start = segments[i0 - 1]["start"]
                if original_start - candidate_start > max_start_walkback_sec:
                    break
                i0 -= 1
                walked += 1
            start_sec = segments[i0]["start"]
            if original_start - start_sec > max_start_walkback_sec:
                start_sec = original_start - max_start_walkback_sec
            chunk["start"] = start_sec

        # Extend end to include the payoff (punch line often in next phrase).
        # Keep extension small so clips stay natural length; stop at first sentence end.
        end_sec = chunk["end"]
        last_idx = -1
        for i, s in enumerate(segments):
            if s["start"] < end_sec and s["end"] > chunk["start"]:
                last_idx = i
        max_end = chunk["start"] + max_duration
        if last_idx >= 0:
            extra_segments = 2
            extra_sec = 8.0
            for j in range(last_idx + 1, min(last_idx + 1 + extra_segments, len(segments))):
                seg_end = segments[j]["end"]
                if seg_end <= max_end and seg_end - end_sec <= extra_sec:
                    end_sec = seg_end
                    # Stop after a sentence end so we don't cut the punchline
                    txt = (segments[j].get("text") or "").strip().rstrip()
                    if txt and txt[-1] in ".?!…":
                        break
                else:
                    break
        desired_end = min(end_sec + clip_end_padding_sec, video_duration_sec, max_end)
        if desired_end - chunk["start"] > max_duration:
            desired_end = min(chunk["start"] + max_duration, video_duration_sec)
        chunk["end"] = desired_end

    # Resolve "auto" layout from first frame
    if crop_mode == "auto" and selected:
        try:
            at_sec = max(1.0, selected[0]["start"])
            crop_mode = suggest_layout(video_path, at_sec=at_sec)
            # If we suggested center but face detection fails a lot in first chunk, use event mode
            if crop_mode == "center":
                start_sec = selected[0]["start"]
                end_sec = selected[0]["end"]
                if should_use_event_fallback(
                    video_path, start_sec, end_sec, face_fail_ratio_threshold=0.25
                ):
                    crop_mode = "event"
        except Exception:
            crop_mode = "center"

    # For webcam+chat mode: use manual regions, fixed preset, or detect
    webcam_bbox = None
    chat_bbox = None
    center_bbox = manual_center_bbox  # None = use default center 25%,25%,75%,75% in export
    export_crop_mode = crop_mode
    if manual_webcam_bbox is not None and manual_chat_bbox is not None:
        # User chose the crop regions themselves — always use webcam+chat stack
        webcam_bbox = manual_webcam_bbox
        chat_bbox = manual_chat_bbox
        export_crop_mode = "webcam_chat_stack"
    elif crop_mode == "webcam_chat_stack_bottom":
        # Fixed preset: webcam bottom-left, chat bottom-right (like your red boxes)
        webcam_bbox = (0.0, 0.4, 0.5, 1.0)
        chat_bbox = (0.5, 0.4, 1.0, 1.0)
        export_crop_mode = "webcam_chat_stack"
    elif crop_mode == "webcam_chat_stack" and selected:
        first_start = selected[0]["start"]
        at_sec = max(1.0, first_start)  # avoid 0 in case of loading/black frame
        try:
            webcam_bbox, chat_bbox = detect_webcam_chat_regions(
                video_path, at_sec=at_sec, bottom_half_layout=True
            )
        except Exception:
            pass

    # 4. For each selected chunk: filter segments inside [start,end], build SRT, export
    out_paths: list[Path] = []
    short_transcripts: list[str] = []
    for i, chunk in enumerate(selected):
        start_sec = chunk["start"]
        end_sec = chunk["end"]
        clip_segments = [
            s for s in segments
            if s["end"] > start_sec and s["start"] < end_sec
        ]
        # Normalize to clip-local times for SRT
        clip_segments = [
            {
                "start": max(s["start"], start_sec) - start_sec,
                "end": min(s["end"], end_sec) - start_sec,
                "text": s["text"],
            }
            for s in clip_segments
        ]
        srt_path = None
        if burn_captions and clip_segments:
            srt_path = output_dir / f"clip_{i}_subtitles.srt"
            write_srt(clip_segments, srt_path, start_offset=0.0)
        short_transcripts.append(" ".join(s["text"] for s in clip_segments).strip() if clip_segments else "")

        focus_x = None
        event_bbox = None
        if smart_crop and crop_mode == "center":
            try:
                focus_x = estimate_focus_x(video_path, start_sec, end_sec)
            except Exception:
                focus_x = None
            # Fallback: if face detection fails in >25% of frames, use event/group crop
            if focus_x is None and should_use_event_fallback(
                video_path, start_sec, end_sec, face_fail_ratio_threshold=0.25
            ):
                try:
                    event_bbox = estimate_event_crop(
                        video_path, start_sec, end_sec, focus_region=focus_region
                    )
                except Exception:
                    pass
        if crop_mode == "event":
            try:
                event_bbox = estimate_event_crop(
                    video_path, start_sec, end_sec, focus_region=focus_region
                )
            except Exception:
                pass

        out_path = output_dir / f"short_{i + 1}.mp4"
        make_short(
            video_path,
            start_sec,
            end_sec,
            out_path,
            srt_path=srt_path,
            focus_x=focus_x,
            crop_mode=export_crop_mode,
            focus_region=focus_region,
            letterbox_full_width=letterbox_full_width,
            manual_top=manual_top,
            manual_bottom=manual_bottom,
            manual_left=manual_left,
            manual_right=manual_right,
            webcam_bbox=webcam_bbox,
            chat_bbox=chat_bbox,
            event_bbox=event_bbox,
            center_bbox=center_bbox,
        )
        out_paths.append(out_path)
    return (out_paths, titles, full_text, short_transcripts)
