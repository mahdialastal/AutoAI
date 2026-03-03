"""Simple Gradio UI for AutoShorts - upload or paste URL, get shorts."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import gradio as gr

# App folder = directory containing this file (AutoAI project root)
APP_ROOT = Path(__file__).resolve().parent
try:
    gr.set_static_paths(paths=[str(APP_ROOT)])
except AttributeError:
    # Older Gradio: playback may still work without this helper
    pass

# Ensure project root is on path
import sys
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from src.autoshorts.pipeline import run_pipeline


def generate(
    source: str,
    num_clips: int,
    crop_mode: str,
    focus_region: str,
) -> tuple[str, list[str]]:
    """Returns (status_message, list of video paths for gallery)."""
    if not source or not source.strip():
        return "Enter a YouTube URL or provide a video file path.", []
    source = source.strip()
    if not source.startswith(("http://", "https://")) and not os.path.isfile(source):
        return "Not a valid URL or existing file path.", []
    try:
        download_dir = APP_ROOT / "downloads"
        download_dir.mkdir(parents=True, exist_ok=True)
        run_folder = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_dir = APP_ROOT / "generated" / run_folder
        output_dir.mkdir(parents=True, exist_ok=True)

        paths = run_pipeline(
            source=source,
            output_dir=output_dir,
            download_dir=download_dir,
            num_clips=num_clips,
            burn_captions=True,
            crop_mode=crop_mode,
            focus_region=focus_region,
            manual_top=None,
            manual_bottom=None,
            manual_left=None,
            manual_right=None,
        )
        if not paths:
            return "No segments found (empty or very short transcript).", []
        path_strs = [str(p.resolve()) for p in paths]
        return (
            f"Generated {len(paths)} short(s) in generated/{run_folder}/.",
            path_strs,
        )
    except Exception as e:
        return f"Error: {e}", []


def run_ui(
    url: str,
    video_path: str | None,
    num_clips: int,
    input_mode: str,
    crop_mode: str,
    focus_region: str,
) -> tuple[str, list[str]]:
    """Use URL if input_mode is 'url', else use uploaded video path."""
    if input_mode == "YouTube URL":
        source = url or ""
    else:
        if video_path is None:
            source = ""
        elif isinstance(video_path, dict) and "path" in video_path:
            source = video_path["path"] or ""
        else:
            source = str(video_path)
    if not source:
        return "Paste a URL or upload a video, then click Generate.", []
    return generate(source, num_clips, crop_mode, focus_region)


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="AutoShorts (local)", theme=gr.themes.Soft(), css="""
        .video-container { max-width: 100%; margin: 0 auto; }
        .gr-video { border-radius: 12px; overflow: hidden; }
    """) as app:
        gr.Markdown("# AutoShorts — Turn videos into shorts locally")
        gr.Markdown(
            "Like **Klap** and **Opus Clip**: paste a link, choose a layout, generate. "
            "We auto-detect the best moments, add captions, and reframe for vertical (9:16). "
            "All processing runs on your machine."
        )

        with gr.Row():
            input_mode = gr.Radio(
                choices=["YouTube URL", "Upload video"],
                value="YouTube URL",
                label="Input",
            )
        url_in = gr.Textbox(
            label="YouTube URL",
            placeholder="https://youtube.com/watch?v=...",
        )
        file_in = gr.Video(label="Upload video", visible=False)

        def toggle_input(choice: str):
            if choice == "YouTube URL":
                return gr.update(visible=True), gr.update(visible=False)
            return gr.update(visible=False), gr.update(visible=True)

        input_mode.change(toggle_input, input_mode, [url_in, file_in])

        gr.Markdown("### 1. How many shorts?")
        num_clips = gr.Slider(1, 10, value=3, step=1, label="Number of shorts")

        gr.Markdown("### 2. Layout (like Opus Clip)")
        gr.Markdown(
            "Pick how the short is framed. **Streaming** = we detect your face and the chat/side panel and stack them (webcam on top, chat on bottom)."
        )
        with gr.Row():
            crop_mode = gr.Dropdown(
                [
                    ("Streaming (webcam top, chat bottom)", "webcam_chat_stack"),
                    ("Split screen (left & right stacked)", "bottom_split_stack"),
                    ("Speaker only (face in center)", "center"),
                ],
                value="webcam_chat_stack",
                label="Layout",
            )
            focus_region = gr.Radio(
                choices=[("Full frame", "full"), ("Screen recording (center)", "center")],
                value="full",
                label="Source",
            )

        gr.Markdown("### 3. Generate")
        run_btn = gr.Button("Generate shorts", variant="primary", size="lg")
        msg_out = gr.Textbox(label="Status", interactive=False)

        gr.Markdown("---")
        gr.Markdown("### Generated shorts")
        gallery = gr.Gallery(
            label="Generated shorts",
            columns=1,
            object_fit="contain",
            height="auto",
        )

        def on_generate(url, vid, n, mode, crop, focus):
            msg, paths = run_ui(url, vid, n, mode, crop, focus)
            return msg, paths

        run_btn.click(
            fn=on_generate,
            inputs=[
                url_in,
                file_in,
                num_clips,
                input_mode,
                crop_mode,
                focus_region,
            ],
            outputs=[msg_out, gallery],
        )
    return app


if __name__ == "__main__":
    build_ui().launch()
