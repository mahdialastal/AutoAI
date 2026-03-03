"""Orchestrate: download → transcribe → highlight selection → export shorts."""
from __future__ import annotations

from pathlib import Path

from .download import get_video_path
from .export import make_short, write_srt
from .highlights import select_highlights
from .transcribe import segments_to_timestamped_chunks, transcribe
from .focus import estimate_focus_x, detect_webcam_chat_regions


def run_pipeline(
    source: str,
    output_dir: str | Path = "./shorts_out",
    download_dir: str | Path | None = None,
    num_clips: int = 3,
    whisper_model: str = "base",
    ollama_model: str = "mistral",
    chunk_duration: float = 30.0,
    min_duration: float = 15.0,
    max_duration: float = 60.0,
    burn_captions: bool = True,
    smart_crop: bool = True,
    crop_mode: str = "bottom_split_stack",
    focus_region: str = "full",
    manual_top: float | None = None,
    manual_bottom: float | None = None,
    manual_left: float | None = None,
    manual_right: float | None = None,
) -> list[Path]:
    """
    Run the full pipeline: get video → transcribe → pick highlights → export shorts.
    output_dir: where to save generated shorts.
    download_dir: where to save downloaded videos (YouTube); if None, uses system temp.
    Returns paths to generated short videos.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dld_dir = Path(download_dir) if download_dir is not None else None

    # 1. Get video
    video_path = get_video_path(source, download_dir=dld_dir)

    # 2. Transcribe
    full_text, segments = transcribe(video_path, model_size=whisper_model)
    if not segments:
        return []

    # 3. Chunk and select highlights
    chunks = segments_to_timestamped_chunks(segments, chunk_duration_sec=chunk_duration)
    selected = select_highlights(
        chunks,
        num_clips=num_clips,
        model=ollama_model,
        min_duration=min_duration,
        max_duration=max_duration,
    )

    # For webcam+chat mode: detect regions from a frame in the first segment
    # (so we use the actual streaming layout, not a fixed 2s that might be different)
    webcam_bbox = None
    chat_bbox = None
    if crop_mode == "webcam_chat_stack" and selected:
        first_start = selected[0]["start"]
        at_sec = max(1.0, first_start)  # avoid 0 in case of loading/black frame
        try:
            webcam_bbox, chat_bbox = detect_webcam_chat_regions(video_path, at_sec=at_sec)
        except Exception:
            pass

    # 4. For each selected chunk: filter segments inside [start,end], build SRT, export
    out_paths: list[Path] = []
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

        focus_x = None
        if smart_crop and crop_mode == "center":
            try:
                focus_x = estimate_focus_x(video_path, start_sec, end_sec)
            except Exception:
                focus_x = None

        out_path = output_dir / f"short_{i + 1}.mp4"
        make_short(
            video_path,
            start_sec,
            end_sec,
            out_path,
            srt_path=srt_path,
            focus_x=focus_x,
            crop_mode=crop_mode,
            focus_region=focus_region,
            manual_top=manual_top,
            manual_bottom=manual_bottom,
            manual_left=manual_left,
            manual_right=manual_right,
            webcam_bbox=webcam_bbox,
            chat_bbox=chat_bbox,
        )
        out_paths.append(out_path)
    return out_paths
