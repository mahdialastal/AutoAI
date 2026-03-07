#!/usr/bin/env python3
"""CLI for MarkSoft AutoShorts: turn long videos into shorts locally."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Run from project root so src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.autoshorts.pipeline import run_pipeline


def main() -> None:
    p = argparse.ArgumentParser(
        description="Turn long videos or YouTube URLs into short clips (Shorts/Reels/TikTok) using local AI."
    )
    p.add_argument(
        "source",
        help="YouTube URL or path to a local video file",
    )
    p.add_argument(
        "-o", "--output-dir",
        default="./shorts_out",
        help="Output directory for generated shorts (default: ./shorts_out)",
    )
    p.add_argument(
        "-n", "--num-clips",
        type=int,
        default=3,
        help="Number of short clips to generate (default: 3)",
    )
    p.add_argument(
        "--whisper-model",
        default="base",
        choices=["tiny", "base", "small", "medium", "large-v2", "large-v3"],
        help="Whisper model size (default: base)",
    )
    p.add_argument(
        "--ollama-model",
        default="mistral",
        help="Ollama model for highlight selection (default: mistral)",
    )
    p.add_argument(
        "--chunk-duration",
        type=float,
        default=30.0,
        help="Target chunk duration in seconds for LLM analysis (default: 30)",
    )
    p.add_argument(
        "--min-duration",
        type=float,
        default=15.0,
        help="Minimum clip length in seconds (default: 15)",
    )
    p.add_argument(
        "--max-duration",
        type=float,
        default=60.0,
        help="Maximum clip length in seconds; can go longer when context needs it (default: 60)",
    )
    p.add_argument(
        "--no-captions",
        action="store_true",
        help="Do not burn captions into the video",
    )
    p.add_argument("--crop-mode", default="bottom_split_stack", choices=["center", "bottom_strip_rotate", "bottom_split_stack", "bottom_split_stack_swapped"], help="Crop layout")
    p.add_argument("--focus-region", default="full", choices=["full", "center"], help="Use 'center' for screen recordings to crop to center area first")
    args = p.parse_args()

    app_root = Path(__file__).resolve().parent
    is_url = str(args.source).strip().startswith(("http://", "https://"))
    download_dir = (app_root / "downloads") if is_url else None

    try:
        paths, titles, *_ = run_pipeline(
            source=args.source,
            output_dir=args.output_dir,
            download_dir=download_dir,
            num_clips=args.num_clips,
            whisper_model=args.whisper_model,
            ollama_model=args.ollama_model,
            chunk_duration=args.chunk_duration,
            min_duration=args.min_duration,
            max_duration=args.max_duration,
            burn_captions=not args.no_captions,
            crop_mode=args.crop_mode,
            focus_region=args.focus_region,
        )
        print(f"Generated {len(paths)} short(s):")
        for i, path in enumerate(paths):
            title = titles[i] if i < len(titles) else f"Short {i+1}"
            print(f"  {path}  — {title}")
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
