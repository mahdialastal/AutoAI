"""Simple Gradio UI for MarkSoft AutoShorts — upload or paste URL, get shorts."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import cv2
import gradio as gr
import numpy as np

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
from src.autoshorts.download import get_video_path, get_video_title
from src.autoshorts.youtube_upload import upload_video_to_youtube

PRESETS_FILE = APP_ROOT / "crop_presets.json"


def _presets_data():
    PRESETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not PRESETS_FILE.exists():
        PRESETS_FILE.write_text("{}", encoding="utf-8")
    return json.loads(PRESETS_FILE.read_text(encoding="utf-8"))


def list_crop_presets():
    return sorted(_presets_data().keys())


def get_crop_preset(name):
    return _presets_data().get(name)


def save_crop_preset(name, webcam, chat):
    name = (name or "").strip()
    if not name:
        return "Preset name is required."
    try:
        data = _presets_data()
        data[name] = {"webcam": [float(x) for x in webcam], "chat": [float(x) for x in chat]}
        PRESETS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return None
    except Exception as e:
        return str(e)


def rename_crop_preset(old_name, new_name):
    new_name = (new_name or "").strip()
    if not new_name:
        return "New name is required."
    try:
        data = _presets_data()
        if old_name not in data:
            return f"Preset not found: {old_name}"
        if new_name != old_name and new_name in data:
            return f"A preset named '{new_name}' already exists."
        data[new_name] = data.pop(old_name)
        PRESETS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return None
    except Exception as e:
        return str(e)


def delete_crop_preset(name):
    try:
        data = _presets_data()
        if name in data:
            del data[name]
            PRESETS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return None
    except Exception as e:
        return str(e)


GENERATED_DIR = APP_ROOT / "generated"


def _source_label(source: str) -> str:
    """Short display label for a source (URL or path)."""
    if not source:
        return "Unknown"
    s = source.strip()
    if s.startswith(("http://", "https://")):
        # YouTube: show video id or domain
        if "youtube.com" in s or "youtu.be" in s:
            for sep in ("v=", "youtu.be/"):
                if sep in s:
                    rest = s.split(sep, 1)[-1].split("&")[0].split("?")[0].strip("/")
                    if rest:
                        return f"YouTube: {rest[:20]}" + ("…" if len(rest) > 20 else "")
        return "URL: " + s[:30] + ("…" if len(s) > 30 else "")
    # Local file
    return os.path.basename(s) or s[:30]


def list_generated_runs():
    """Return list of (folder_name, display_label) for History dropdown, newest first."""
    if not GENERATED_DIR.exists():
        return []
    runs = []
    for d in GENERATED_DIR.iterdir():
        if d.is_dir() and not d.name.startswith("."):
            label = d.name.replace("_", " ", 1)
            runs.append((d.name, label))
    runs.sort(key=lambda x: x[0], reverse=True)
    return runs


def get_runs_by_source():
    """
    Group runs by source video. Returns list of (source_key, source_label, runs)
    where runs = [(folder_name, run_timestamp_label), ...] newest first per source.
    """
    if not GENERATED_DIR.exists():
        return []
    # folder_name -> (run_timestamp_label, source_key, source_label)
    run_info = {}
    for d in GENERATED_DIR.iterdir():
        if not d.is_dir() or d.name.startswith("."):
            continue
        folder_name = d.name
        ts_label = folder_name.replace("_", " ", 1)
        meta_path = d / "run_metadata.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                src = meta.get("source", "")
                src_label = meta.get("source_label") or _source_label(src)
                # Use normalized source as key (same video = same key)
                source_key = src.strip() or f"__unknown_{folder_name}"
                run_info[folder_name] = (ts_label, source_key, src_label)
            except Exception:
                run_info[folder_name] = (ts_label, f"__unknown_{folder_name}", "Unknown")
        else:
            run_info[folder_name] = (ts_label, f"__unknown_{folder_name}", "Unknown")
    # Group by source_key
    by_source = {}
    for folder_name, (ts_label, source_key, source_label) in run_info.items():
        if source_key not in by_source:
            by_source[source_key] = (source_label, [])
        by_source[source_key][1].append((folder_name, ts_label))
    for lst in by_source.values():
        lst[1].sort(key=lambda x: x[0], reverse=True)
    # Sort sources by most recent run
    order = sorted(by_source.items(), key=lambda x: x[1][1][0][0] if x[1][1] else "", reverse=True)
    # Prefer actual video title for URLs (helps when metadata only had video ID)
    out = []
    for sk, (sl, runs) in order:
        display_label = (get_video_title(sk) or sl) if (sk and sk.startswith(("http://", "https://"))) else sl
        out.append((sk, display_label, runs))
    return out


def get_run_shorts(folder_name):
    """
    Return (list of (title, path_str, transcript), list of path_str, full_transcript) for a run folder.
    transcript and full_transcript are "" when not in metadata (e.g. older runs).
    """
    if not folder_name:
        return [], [], ""
    run_dir = GENERATED_DIR / folder_name
    if not run_dir.exists() or not run_dir.is_dir():
        return [], [], ""
    meta_path = run_dir / "run_metadata.json"
    titles = {}
    transcripts_by_file = {}
    run_timestamp = folder_name.replace("_", " ", 1)
    full_transcript = ""
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            run_timestamp = meta.get("run_timestamp", run_timestamp)
            full_transcript = meta.get("full_transcript", "")
            for s in meta.get("shorts", []):
                titles[s["file"]] = s.get("title", s["file"])
                transcripts_by_file[s["file"]] = s.get("transcript", "")
        except Exception:
            pass
    shorts = []
    for f in sorted(run_dir.glob("short_*.mp4")):
        title = titles.get(f.name, f"Short {f.stem.split('_')[-1]}")
        path_str = str(f.resolve())
        transcript = transcripts_by_file.get(f.name, "")
        shorts.append((title, run_timestamp, path_str, transcript))
    paths_only = [p for _, _, p, _ in shorts]
    return shorts, paths_only, full_transcript


def _get_transcript_for_selection(folder_name: str | None, choice_index: int) -> str:
    """Return transcript text for the given run and selection: 0 = full video, 1+ = short index."""
    if not folder_name:
        return ""
    shorts, _, full_transcript = get_run_shorts(folder_name)
    if choice_index == 0:
        return (full_transcript or "").strip() or "*No full transcript saved for this run.*"
    i = choice_index - 1
    if 0 <= i < len(shorts):
        _, _, _, transcript = shorts[i]
        return (transcript or "").strip() or "*No transcript saved for this short.*"
    return ""


def preview_manual_regions(
    source: str,
    input_mode: str,
    url: str,
    video_path: str | None,
    w_left: float,
    w_top: float,
    w_right: float,
    w_bottom: float,
    c_left: float,
    c_top: float,
    c_right: float,
    c_bottom: float,
    m_left: float,
    m_top: float,
    m_right: float,
    m_bottom: float,
):
    """Draw webcam, chat, and middle (gap fill) regions on a frame. Returns RGB image or None."""
    if input_mode == "YouTube URL":
        src = (url or "").strip()
    else:
        if video_path is None:
            return None
        src = (video_path.get("path") if isinstance(video_path, dict) else video_path) or ""
        src = str(src).strip() if src else ""
    if not src or not src.strip():
        return None
    src = src.strip()
    try:
        path = get_video_path(src, download_dir=APP_ROOT / "downloads")
    except Exception:
        return None
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_POS_MSEC, 5000.0)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return None
    h, w = frame.shape[:2]
    if w <= 0 or h <= 0:
        return None
    def pct(x):
        return max(0, min(100, float(x or 0))) / 100.0
    wl, wt, wr, wb = pct(w_left), pct(w_top), pct(w_right), pct(w_bottom)
    cl, ct, cr, cb = pct(c_left), pct(c_top), pct(c_right), pct(c_bottom)
    ml, mt, mr, mb = pct(m_left), pct(m_top), pct(m_right), pct(m_bottom)
    img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    # Webcam = green
    x1, y1 = int(wl * w), int(wt * h)
    x2, y2 = int(wr * w), int(wb * h)
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 3)
    cv2.putText(img, "Webcam", (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    # Chat = orange
    x1, y1 = int(cl * w), int(ct * h)
    x2, y2 = int(cr * w), int(cb * h)
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 165, 255), 3)
    cv2.putText(img, "Chat", (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
    # Middle (gap fill) = blue
    x1, y1 = int(ml * w), int(mt * h)
    x2, y2 = int(mr * w), int(mb * h)
    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 180, 255), 3)  # RGB blue
    cv2.putText(img, "Middle (gap)", (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 180, 255), 2)
    return img


def _pct(x):
    return max(0, min(100, float(x or 0))) / 100.0


def _crop_scale_pad(frame_bgr, l, t, r, b, out_w, out_h):
    """Crop region (l,t,r,b) from frame (0-1), scale to fit out_w x out_h, pad to exact size. Returns BGR."""
    h, w = frame_bgr.shape[:2]
    x1, y1 = int(l * w), int(t * h)
    x2, y2 = int(r * w), int(b * h)
    if x2 <= x1 or y2 <= y1:
        return np.zeros((out_h, out_w, 3), dtype=np.uint8)
    crop = frame_bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return np.zeros((out_h, out_w, 3), dtype=np.uint8)
    crop_h, crop_w = crop.shape[:2]
    scale = min(out_w / crop_w, out_h / crop_h)
    new_w = max(1, int(crop_w * scale))
    new_h = max(1, int(crop_h * scale))
    scaled = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_AREA)
    out = np.zeros((out_h, out_w, 3), dtype=np.uint8)
    out[:] = 0
    y0 = (out_h - new_h) // 2
    x0 = (out_w - new_w) // 2
    out[y0 : y0 + new_h, x0 : x0 + new_w] = scaled
    return out


def preview_final_layout(
    input_mode: str,
    url: str,
    video_path,
    w_left: float,
    w_top: float,
    w_right: float,
    w_bottom: float,
    c_left: float,
    c_top: float,
    c_right: float,
    c_bottom: float,
    m_left: float,
    m_top: float,
    m_right: float,
    m_bottom: float,
):
    """Build the exact 9:16 layout: webcam top, center fill (gap), chat bottom. Returns RGB 1080x1920 or None."""
    if input_mode == "YouTube URL":
        src = (url or "").strip()
    else:
        if video_path is None:
            return None
        src = (video_path.get("path") if isinstance(video_path, dict) else video_path) or ""
        src = str(src).strip() if src else ""
    if not src:
        return None
    try:
        path = get_video_path(src, download_dir=APP_ROOT / "downloads")
    except Exception:
        return None
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_POS_MSEC, 5000.0)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return None
    wl, wt, wr, wb = _pct(w_left), _pct(w_top), _pct(w_right), _pct(w_bottom)
    cl, ct, cr, cb = _pct(c_left), _pct(c_top), _pct(c_right), _pct(c_bottom)
    ml, mt, mr, mb = _pct(m_left), _pct(m_top), _pct(m_right), _pct(m_bottom)
    rw_w, rh_w = max(0.01, wr - wl), max(0.01, wb - wt)
    rw_c, rh_c = max(0.01, cr - cl), max(0.01, cb - ct)
    rw_m, rh_m = max(0.01, mr - ml), max(0.01, mb - mt)
    h_w = max(1, min(1920, round(1080 * rh_w / rw_w)))
    h_c = max(1, min(1920, round(1080 * rh_c / rw_c)))
    if h_w + h_c < 1920:
        h_mid = 1920 - h_w - h_c
        top = _crop_scale_pad(frame, wl, wt, wr, wb, 1080, h_w)
        mid = _crop_scale_pad(frame, ml, mt, mr, mb, 1080, h_mid)
        bot = _crop_scale_pad(frame, cl, ct, cr, cb, 1080, h_c)
        stacked = np.vstack([top, mid, bot])
    else:
        scale = 1920 / (h_w + h_c)
        h_w_new = max(1, round(h_w * scale))
        h_c_new = 1920 - h_w_new
        top = _crop_scale_pad(frame, wl, wt, wr, wb, 1080, h_w_new)
        bot = _crop_scale_pad(frame, cl, ct, cr, cb, 1080, h_c_new)
        stacked = np.vstack([top, bot])
    if stacked.shape[0] != 1920 or stacked.shape[1] != 1080:
        stacked = cv2.resize(stacked, (1080, 1920), interpolation=cv2.INTER_LINEAR)
    return cv2.cvtColor(stacked, cv2.COLOR_BGR2RGB)


def generate(
    source: str,
    num_clips: int,
    ollama_model: str,
    crop_mode: str,
    focus_region: str,
    letterbox_full_width: bool = False,
    use_manual_regions: bool = False,
    manual_webcam_bbox: tuple[float, float, float, float] | None = None,
    manual_chat_bbox: tuple[float, float, float, float] | None = None,
    manual_center_bbox: tuple[float, float, float, float] | None = None,
) -> tuple[str, list[str]]:
    """Returns (status_message, list of video paths for gallery)."""
    if not source or not source.strip():
        return "Enter a YouTube URL or provide a video file path.", [], None
    source = source.strip()
    if not source.startswith(("http://", "https://")) and not os.path.isfile(source):
        return "Not a valid URL or existing file path.", [], None
    try:
        download_dir = APP_ROOT / "downloads"
        download_dir.mkdir(parents=True, exist_ok=True)
        run_folder = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_dir = APP_ROOT / "generated" / run_folder
        output_dir.mkdir(parents=True, exist_ok=True)

        paths, titles, full_transcript, short_transcripts = run_pipeline(
            source=source,
            output_dir=output_dir,
            download_dir=download_dir,
            num_clips=num_clips,
            ollama_model=ollama_model,
            burn_captions=True,
            crop_mode=crop_mode,
            focus_region=focus_region,
            letterbox_full_width=letterbox_full_width,
            manual_top=None,
            manual_bottom=None,
            manual_left=None,
            manual_right=None,
            manual_webcam_bbox=manual_webcam_bbox,
            manual_chat_bbox=manual_chat_bbox,
            manual_center_bbox=manual_center_bbox,
        )
        if not paths:
            return "No segments found (empty or very short transcript).", [], None
        path_strs = [str(p.resolve()) for p in paths]
        title_list = [titles[i] if i < len(titles) else f"Short {i+1}" for i in range(len(paths))]
        run_ts = run_folder.replace("_", " ", 1)
        short_transcripts_safe = short_transcripts if len(short_transcripts) >= len(paths) else short_transcripts + [""] * (len(paths) - len(short_transcripts))
        meta = {
            "run_timestamp": run_ts,
            "source": source,
            "source_label": (get_video_title(source) or _source_label(source)),
            "full_transcript": full_transcript or "",
            "shorts": [
                {"file": p.name, "title": title_list[i], "transcript": short_transcripts_safe[i]}
                for i, p in enumerate(paths)
            ],
        }
        (output_dir / "run_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        gallery_value = [(path_strs[i], title_list[i]) for i in range(len(path_strs))]
        return (
            f"Generated {len(paths)} short(s) in generated/{run_folder}/.",
            gallery_value,
            run_folder,
        )
    except Exception as e:
        return f"Error: {e}", [], None


def run_ui(
    url: str,
    video_path: str | None,
    num_clips: int,
    ollama_model: str,
    input_mode: str,
    crop_mode: str,
    focus_region: str,
    letterbox_full_width: bool,
    use_manual_regions: bool,
    w_left: float,
    w_top: float,
    w_right: float,
    w_bottom: float,
    c_left: float,
    c_top: float,
    c_right: float,
    c_bottom: float,
    m_left: float,
    m_top: float,
    m_right: float,
    m_bottom: float,
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
        return "Paste a URL or upload a video, then click Generate.", [], None
    manual_webcam = None
    manual_chat = None
    manual_center = None
    if use_manual_regions and crop_mode in ("webcam_chat_stack", "webcam_chat_stack_bottom"):
        try:
            wl = max(0, min(100, float(w_left))) / 100.0
            wt = max(0, min(100, float(w_top))) / 100.0
            wr = max(0, min(100, float(w_right))) / 100.0
            wb = max(0, min(100, float(w_bottom))) / 100.0
            cl = max(0, min(100, float(c_left))) / 100.0
            ct = max(0, min(100, float(c_top))) / 100.0
            cr = max(0, min(100, float(c_right))) / 100.0
            cb = max(0, min(100, float(c_bottom))) / 100.0
            if wl < wr and wt < wb and cl < cr and ct < cb:
                manual_webcam = (wl, wt, wr, wb)
                manual_chat = (cl, ct, cr, cb)
                ml = max(0, min(100, float(m_left or 25))) / 100.0
                mt = max(0, min(100, float(m_top or 25))) / 100.0
                mr = max(0, min(100, float(m_right or 75))) / 100.0
                mb = max(0, min(100, float(m_bottom or 75))) / 100.0
                if ml < mr and mt < mb:
                    manual_center = (ml, mt, mr, mb)
                else:
                    manual_center = (0.25, 0.25, 0.75, 0.75)
            else:
                return "Manual regions: left must be < right, top < bottom for both boxes.", [], None
        except (TypeError, ValueError):
            return "Manual regions: enter numbers 0–100 for all 8 fields.", [], None
    else:
        manual_center = None
    return generate(
        source, num_clips, ollama_model, crop_mode, focus_region, letterbox_full_width,
        use_manual_regions=use_manual_regions,
        manual_webcam_bbox=manual_webcam,
        manual_chat_bbox=manual_chat,
        manual_center_bbox=manual_center,
    )


def build_ui() -> gr.Blocks:
    with gr.Blocks(title="MarkSoft AutoShorts") as app:
        gr.Markdown("# MarkSoft AutoShorts — Turn videos into shorts locally")
        gr.Markdown(
            "Paste a link or upload a video, choose a layout, generate. "
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
        ollama_model = gr.Dropdown(
            choices=["mistral", "llama3.1", "llama3.2", "llama3.3", "gemma2", "phi3"],
            value="mistral",
            label="AI model (Ollama)",
            allow_custom_value=True,
            info="Model used to pick moments and generate titles. Stronger models may give better clips.",
        )
        gr.Markdown("### 2. Layout")
        gr.Markdown(
            "**Screen recording of a feed or event/news clip?** → Choose **Event / news**. "
            "**Actual stream with webcam + chat on screen?** → **Streaming**. "
            "If the webcam and chat are in the **bottom** of the screen (webcam left, chat right), pick **Streaming (webcam bottom-left, chat bottom-right)** so we use those two areas only. "
            "**Single speaker (talking head)?** → **Speaker only** or **Auto**."
        )
        with gr.Row():
            crop_mode = gr.Dropdown(
                [
                    ("Auto (detect layout)", "auto"),
                    ("Event / news (group & action)", "event"),
                    ("Streaming (webcam top, chat bottom)", "webcam_chat_stack"),
                    ("Streaming (webcam bottom-left, chat bottom-right)", "webcam_chat_stack_bottom"),
                    ("Speaker only (face in center)", "center"),
                    ("Split screen (left & right stacked)", "bottom_split_stack"),
                ],
                value="event",
                label="Layout",
            )
            focus_region = gr.Radio(
                choices=[("Full frame", "full"), ("Screen recording (crop to center)", "center")],
                value="full",
                label="Source",
                info="Use 'Screen recording' when your file is a capture of a browser or app with a video playing in the middle. For screen recordings, use Layout = Event / news and Source = Screen recording together.",
            )
        output_style = gr.Radio(
            choices=[
                ("Fill frame (crop to 9:16)", False),
                ("Full width (letterbox — no horizontal crop)", True),
            ],
            value=False,
            label="Output",
            info="Full width keeps the entire horizontal frame visible with black bars top/bottom. Use this if the result looks like 'only the center' and you want to see the whole scene.",
        )

        gr.Markdown("### 2b. Set crop regions yourself (Streaming only)")
        manual_accord = gr.Accordion(
            "I'll select the webcam and chat areas myself (no AI)",
            open=False,
            visible=False,
        )
        with manual_accord:
            use_manual_regions = gr.Checkbox(
                value=False,
                label="Use my crop regions (ignore auto-detect / presets)",
            )
            gr.Markdown("**Saved presets** — Load a preset to fill the boxes below, or save/rename/delete.")
            with gr.Row():
                preset_dropdown = gr.Dropdown(
                    choices=[""] + list_crop_presets(),
                    value="",
                    label="Saved presets",
                    allow_custom_value=False,
                )
                preset_name_in = gr.Textbox(
                    value="",
                    label="Preset name (save or rename to this)",
                    placeholder="e.g. My stream layout",
                    scale=2,
                )
            with gr.Row():
                load_preset_btn = gr.Button("Load selected")
                save_preset_btn = gr.Button("Save current as")
                rename_preset_btn = gr.Button("Rename selected")
                delete_preset_btn = gr.Button("Delete selected")
            preset_status = gr.Textbox(label="Preset status", interactive=False, visible=True)

            gr.Markdown(
                "Same idea for all three: **Left / Top / Right / Bottom %** define a rectangle on the full video (0–100). "
                "**Webcam** = top of the short, **Chat** = bottom, **Middle** = the strip in between (gap fill)."
            )
            with gr.Row():
                with gr.Column():
                    gr.Markdown("**Webcam** (top of short)")
                    w_left = gr.Number(value=0, label="Left %", minimum=0, maximum=100)
                    w_top = gr.Number(value=40, label="Top %", minimum=0, maximum=100)
                    w_right = gr.Number(value=50, label="Right %", minimum=0, maximum=100)
                    w_bottom = gr.Number(value=100, label="Bottom %", minimum=0, maximum=100)
                with gr.Column():
                    gr.Markdown("**Chat** (bottom of short)")
                    c_left = gr.Number(value=50, label="Left %", minimum=0, maximum=100)
                    c_top = gr.Number(value=40, label="Top %", minimum=0, maximum=100)
                    c_right = gr.Number(value=100, label="Right %", minimum=0, maximum=100)
                    c_bottom = gr.Number(value=100, label="Bottom %", minimum=0, maximum=100)
                with gr.Column():
                    gr.Markdown("**Middle** (gap between webcam & chat)")
                    m_left = gr.Number(value=25, label="Left %", minimum=0, maximum=100)
                    m_top = gr.Number(value=25, label="Top %", minimum=0, maximum=100)
                    m_right = gr.Number(value=75, label="Right %", minimum=0, maximum=100)
                    m_bottom = gr.Number(value=75, label="Bottom %", minimum=0, maximum=100)
            gr.Markdown(
                "**Tip:** Middle uses the same 4 numbers as webcam/chat. Default 25–75 is the center of the frame. "
                "If the middle looks wrong (e.g. head cropped), try **lower Top %** to capture higher, or **higher Bottom %** to capture lower."
            )
            with gr.Row():
                preview_btn = gr.Button("Preview regions on a frame")
                preview_final_btn = gr.Button("Preview final layout (9:16)")
            preview_out = gr.Image(label="Preview", height=300)

        def show_manual_section(mode):
            return gr.update(visible=mode in ("webcam_chat_stack", "webcam_chat_stack_bottom"))

        crop_mode.change(show_manual_section, crop_mode, manual_accord)

        def do_preview(inp_mode, url, vid, wl, wt, wr, wb, cl, ct, cr, cb, ml, mt, mr, mb):
            img = preview_manual_regions(
                "", inp_mode, url, vid,
                wl or 0, wt or 40, wr or 50, wb or 100,
                cl or 50, ct or 40, cr or 100, cb or 100,
                ml or 25, mt or 25, mr or 75, mb or 75,
            )
            return img if img is not None else None

        preview_btn.click(
            fn=do_preview,
            inputs=[
                input_mode, url_in, file_in,
                w_left, w_top, w_right, w_bottom,
                c_left, c_top, c_right, c_bottom,
                m_left, m_top, m_right, m_bottom,
            ],
            outputs=preview_out,
        )

        def do_preview_final(inp_mode, url, vid, wl, wt, wr, wb, cl, ct, cr, cb, ml, mt, mr, mb):
            img = preview_final_layout(
                inp_mode, url, vid,
                wl or 0, wt or 40, wr or 50, wb or 100,
                cl or 50, ct or 40, cr or 100, cb or 100,
                ml or 25, mt or 25, mr or 75, mb or 75,
            )
            return img if img is not None else None

        preview_final_btn.click(
            fn=do_preview_final,
            inputs=[
                input_mode, url_in, file_in,
                w_left, w_top, w_right, w_bottom,
                c_left, c_top, c_right, c_bottom,
                m_left, m_top, m_right, m_bottom,
            ],
            outputs=preview_out,
        )

        def load_preset_into_fields(name):
            if not name:
                return 0, 40, 50, 100, 50, 40, 100, 100
            p = get_crop_preset(name)
            if not p:
                return 0, 40, 50, 100, 50, 40, 100, 100
            w = p.get("webcam", [0, 40, 50, 100])
            c = p.get("chat", [50, 40, 100, 100])
            return (w[0], w[1], w[2], w[3], c[0], c[1], c[2], c[3])

        preset_dropdown.change(
            load_preset_into_fields,
            inputs=[preset_dropdown],
            outputs=[w_left, w_top, w_right, w_bottom, c_left, c_top, c_right, c_bottom],
        )
        load_preset_btn.click(
            load_preset_into_fields,
            inputs=[preset_dropdown],
            outputs=[w_left, w_top, w_right, w_bottom, c_left, c_top, c_right, c_bottom],
        )

        def save_preset_fn(name, wl, wt, wr, wb, cl, ct, cr, cb):
            err = save_crop_preset(name, [wl or 0, wt or 40, wr or 50, wb or 100], [cl or 50, ct or 40, cr or 100, cb or 100])
            if err:
                return gr.update(choices=[""] + list_crop_presets()), err
            return gr.update(choices=[""] + list_crop_presets()), f"Saved as \"{name.strip()}\"."

        save_preset_btn.click(
            save_preset_fn,
            inputs=[preset_name_in, w_left, w_top, w_right, w_bottom, c_left, c_top, c_right, c_bottom],
            outputs=[preset_dropdown, preset_status],
        )

        def rename_preset_fn(old_name, new_name):
            if not old_name:
                return gr.update(choices=[""] + list_crop_presets()), "Select a preset to rename."
            err = rename_crop_preset(old_name, new_name)
            if err:
                return gr.update(choices=[""] + list_crop_presets()), err
            return gr.update(choices=[""] + list_crop_presets(), value=new_name.strip()), f"Renamed to \"{new_name.strip()}\"."

        rename_preset_btn.click(
            rename_preset_fn,
            inputs=[preset_dropdown, preset_name_in],
            outputs=[preset_dropdown, preset_status],
        )

        def delete_preset_fn(name):
            if not name:
                return gr.update(choices=[""] + list_crop_presets()), "Select a preset to delete."
            err = delete_crop_preset(name)
            if err:
                return gr.update(choices=[""] + list_crop_presets()), err
            return gr.update(choices=[""] + list_crop_presets(), value=""), f"Deleted \"{name}\"."

        delete_preset_btn.click(
            delete_preset_fn,
            inputs=[preset_dropdown],
            outputs=[preset_dropdown, preset_status],
        )

        gr.Markdown("### 3. Generate")
        run_btn = gr.Button("Generate shorts", variant="primary", size="lg")
        msg_out = gr.Textbox(label="Status", interactive=False)

        gr.Markdown("---")
        gr.Markdown("### Generated shorts")
        with gr.Tabs():
            with gr.TabItem("This run"):
                gallery = gr.Gallery(
                    label="Generated shorts",
                    columns=1,
                    object_fit="contain",
                    height="auto",
                )
            with gr.TabItem("History"):
                gr.Markdown("Browse by **source video**, then pick a run to see and play the shorts.")
                by_source = get_runs_by_source()
                # Dropdown 1: From video (source)
                video_choices = [
                    (f"{sl} ({len(runs)} run{'s' if len(runs) != 1 else ''})", sk)
                    for sk, sl, runs in by_source
                ]
                first_source_key = video_choices[0][1] if video_choices else None
                first_run_folder = None
                if by_source:
                    first_run_folder = by_source[0][2][0][0]  # first folder_name of first source
                history_video_dropdown = gr.Dropdown(
                    choices=video_choices,
                    value=first_source_key,
                    label="From video",
                    allow_custom_value=False,
                )
                # Dropdown 2: Run (timestamp) for selected video
                run_choices_for_first = [(ts, fn) for fn, ts in (by_source[0][2] if by_source else [])]
                history_run_dropdown = gr.Dropdown(
                    choices=run_choices_for_first,
                    value=first_run_folder,
                    label="Run",
                    allow_custom_value=False,
                )
                if first_run_folder:
                    shorts, _initial_paths, _full_transcript = get_run_shorts(first_run_folder)
                    if shorts:
                        _lines = ["| Title | Generated | Transcript |", "|-------|-----------|------------|"]
                        for _t, _ts, _p, _ in shorts:
                            _lines.append(f"| **{_t}** | {_ts} | *view below* |")
                        _initial_md = "\n".join(_lines)
                        _initial_paths = [(path_str, title) for title, _ts, path_str, _ in shorts]
                        _transcript_choices = [("Full video", 0)] + [(f"Short {i+1}: {t}", i + 1) for i, (t, _, _, _) in enumerate(shorts)]
                        _transcript_value = 0
                        _initial_transcript = _get_transcript_for_selection(first_run_folder, 0)
                    else:
                        _initial_md, _initial_paths = "No shorts in this run.", []
                        _transcript_choices = [("Full video", 0)]
                        _transcript_value = 0
                        _initial_transcript = ""
                else:
                    _initial_md, _initial_paths = "Select a video and run above.", []
                    _transcript_choices = [("Full video", 0)]
                    _transcript_value = 0
                    _initial_transcript = ""
                history_list_md = gr.Markdown(
                    value=_initial_md,
                    label="Shorts in this run",
                )
                with gr.Accordion("Transcript", open=False):
                    transcript_dropdown = gr.Dropdown(
                        choices=_transcript_choices,
                        value=_transcript_value,
                        label="Show transcript",
                        allow_custom_value=False,
                    )
                    history_transcript_md = gr.Markdown(
                        value=_initial_transcript,
                        label="",
                        elem_id="history-transcript-content",
                    )
                history_gallery = gr.Gallery(
                    label="Play shorts",
                    columns=1,
                    object_fit="contain",
                    height="auto",
                    value=_initial_paths,
                )
                with gr.Accordion("Transcripts", open=True):
                    history_transcript_md = gr.Markdown(
                        value=_initial_transcript,
                        label="Full video & short transcripts",
                    )

                # YouTube upload:
                _upload_choices = [(s[0], i) for i, s in enumerate(shorts)] if first_run_folder and shorts else []
                upload_short_dropdown = gr.Radio(
                    label="Short to upload",
                    choices=_upload_choices,
                    value=0 if first_run_folder and shorts else None,
                )
                upload_title_box = gr.Textbox(
                    label="YouTube title",
                    value=shorts[0][0] if first_run_folder and shorts else "",
                )
                upload_desc_box = gr.Textbox(
                    label="YouTube description (optional)",
                    value="",
                    lines=3,
                )
                upload_privacy = gr.Dropdown(
                    label="YouTube privacy",
                    choices=["public", "unlisted", "private"],
                    value="unlisted",
                    allow_custom_value=False,
                )
                upload_status = gr.Markdown(value="")
                upload_btn = gr.Button("Upload selected short to YouTube")

        def on_history_video_select(source_key):
            if not source_key:
                return (
                    gr.update(choices=[], value=None),
                    "Select a video above.",
                    [],
                    gr.update(choices=[], value=None),
                    "",
                    "",
                    "unlisted",
                    "",
                    gr.update(choices=[("Full video", 0)], value=0),
                    "",
                )
            by_source = get_runs_by_source()
            runs = []
            for sk, _, run_list in by_source:
                if sk == source_key:
                    runs = [(ts, fn) for fn, ts in run_list]
                    break
            if not runs:
                return (
                    gr.update(choices=[], value=None),
                    "No runs for this video.",
                    [],
                    gr.update(choices=[], value=None),
                    "",
                    "",
                    "unlisted",
                    "",
                    gr.update(choices=[("Full video", 0)], value=0),
                    "",
                )
            first_folder = runs[0][1]
            md, paths, upload_radio_update, upload_title, transcript_dd_update, transcript_content = on_history_select(first_folder)
            return (
                gr.update(choices=runs, value=first_folder),
                md,
                paths,
                upload_radio_update,
                upload_title,
                "",
                "unlisted",
                "",
                transcript_dd_update,
                transcript_content,
            )

        def on_history_select(folder_name):
            if not folder_name:
                return "Select a run above.", [], gr.update(choices=[], value=None), "", gr.update(choices=[("Full video", 0)], value=0), ""
            shorts, paths, full_transcript = get_run_shorts(folder_name)
            if not shorts:
                return "No shorts in this run.", [], gr.update(choices=[], value=None), "", gr.update(choices=[("Full video", 0)], value=0), ""
            lines = ["| Title | Generated | Transcript |", "|-------|-----------|------------|"]
            for title, ts, _path, _ in shorts:
                lines.append(f"| **{title}** | {ts} | *view below* |")
            gallery_value = [(path_str, title) for title, ts, path_str, _ in shorts]
            upload_choices = [(s[0], i) for i, s in enumerate(shorts)]
            upload_value = 0
            upload_title = shorts[0][0]
            transcript_choices = [("Full video", 0)] + [(f"Short {i+1}: {t}", i + 1) for i, (t, _, _, _) in enumerate(shorts)]
            transcript_content = _get_transcript_for_selection(folder_name, 0)
            return "\n".join(lines), gallery_value, gr.update(choices=upload_choices, value=upload_value), upload_title, gr.update(choices=transcript_choices, value=0), transcript_content

        def on_upload_short_change(folder_name, short_title):
            if folder_name is None or short_title is None:
                return "", ""
            # Gradio may send (label, value) as list or just the index (int)
            if isinstance(short_title, (list, tuple)):
                if len(short_title) >= 2 and isinstance(short_title[-1], int):
                    short_title = short_title[-1]  # use index
                elif len(short_title) >= 1:
                    short_title = short_title[0]  # use title string
            shorts, _, _ = get_run_shorts(folder_name)
            if not shorts:
                return "", ""
            idx = None
            if isinstance(short_title, int) and 0 <= short_title < len(shorts):
                idx = short_title
            else:
                idx = next((i for i, s in enumerate(shorts) if s[0] == short_title), None)
            if idx is None:
                return "", ""
            title, ts, _, _ = shorts[idx]
            desc = f"Clip from longer video, generated at {ts}."
            return title, desc

        def on_transcript_select(folder_name, choice_value):
            if folder_name is None:
                return ""
            idx = 0
            if choice_value is not None:
                try:
                    idx = int(choice_value)
                except (TypeError, ValueError):
                    idx = 0
            return _get_transcript_for_selection(folder_name, idx)

        def on_upload_click(folder_name, short_title, title, description, privacy):
            if folder_name is None:
                return "Select a run and short first."
            if short_title is None:
                return "Select a short to upload."
            # Gradio may send (label, value) as list or just the index (int)
            if isinstance(short_title, (list, tuple)):
                if len(short_title) >= 2 and isinstance(short_title[-1], int):
                    short_title = short_title[-1]  # use index
                elif len(short_title) >= 1:
                    short_title = short_title[0]  # use title string
            shorts, _, _ = get_run_shorts(folder_name)
            if not shorts:
                return "No shorts in this run."
            idx = None
            if isinstance(short_title, int) and 0 <= short_title < len(shorts):
                idx = short_title
            else:
                idx = next((i for i, s in enumerate(shorts) if s[0] == short_title), None)
            if idx is None:
                return "Select a valid short to upload."
            _, _, path_str, _ = shorts[idx]
            video_path = Path(path_str)
            try:
                url = upload_video_to_youtube(
                    video_path,
                    title=title or video_path.stem,
                    description=description or "",
                    privacy_status=privacy or "unlisted",
                    client_secrets_file=APP_ROOT / "youtube_client_secret.json",
                    token_file=APP_ROOT / "youtube_token.json",
                )
                return f"**Uploaded!** [Open on YouTube]({url})"
            except Exception as e:
                return f"Upload failed: `{e}`"

        history_video_dropdown.change(
            on_history_video_select,
            inputs=[history_video_dropdown],
            outputs=[
                history_run_dropdown,
                history_list_md,
                history_gallery,
                upload_short_dropdown,
                upload_title_box,
                upload_desc_box,
                upload_privacy,
                upload_status,
                transcript_dropdown,
                history_transcript_md,
            ],
        )
        history_run_dropdown.change(
            on_history_select,
            inputs=[history_run_dropdown],
            outputs=[
                history_list_md,
                history_gallery,
                upload_short_dropdown,
                upload_title_box,
                transcript_dropdown,
                history_transcript_md,
            ],
        )
        transcript_dropdown.change(
            on_transcript_select,
            inputs=[history_run_dropdown, transcript_dropdown],
            outputs=[history_transcript_md],
        )

        upload_short_dropdown.change(
            on_upload_short_change,
            inputs=[history_run_dropdown, upload_short_dropdown],
            outputs=[upload_title_box, upload_desc_box],
        )
        upload_btn.click(
            on_upload_click,
            inputs=[
                history_run_dropdown,
                upload_short_dropdown,
                upload_title_box,
                upload_desc_box,
                upload_privacy,
            ],
            outputs=[upload_status],
        )

        def on_generate(url, vid, n, ollama, mode, crop, focus, letterbox, use_man, wl, wt, wr, wb, cl, ct, cr, cb, ml, mt, mr, mb):
            msg, paths, run_folder = run_ui(url, vid, n, ollama, mode, crop, focus, letterbox, use_man, wl or 0, wt or 40, wr or 50, wb or 100, cl or 50, ct or 40, cr or 100, cb or 100, ml or 25, mt or 25, mr or 75, mb or 75)
            if run_folder is not None:
                by_source = get_runs_by_source()
                video_choices = [
                    (f"{sl} ({len(runs)} run{'s' if len(runs) != 1 else ''})", sk)
                    for sk, sl, runs in by_source
                ]
                # Find source_key for this run (from metadata we just wrote)
                run_meta_path = GENERATED_DIR / run_folder / "run_metadata.json"
                source_key = f"__unknown_{run_folder}"
                if run_meta_path.exists():
                    try:
                        meta = json.loads(run_meta_path.read_text(encoding="utf-8"))
                        source_key = (meta.get("source") or "").strip() or source_key
                    except Exception:
                        pass
                run_choices = []
                for sk, _, run_list in by_source:
                    if sk == source_key:
                        run_choices = [(ts, fn) for fn, ts in run_list]
                        break
                md, history_paths, _r, _t, transcript_dd_update, transcript_content = on_history_select(run_folder)
                return (
                    msg,
                    paths,
                    gr.update(choices=video_choices, value=source_key),
                    gr.update(choices=run_choices, value=run_folder),
                    md,
                    history_paths,
                    transcript_dd_update,
                    transcript_content,
                )
            return msg, paths, gr.update(), gr.update(), "Select a video and run above.", [], gr.update(choices=[("Full video", 0)], value=0), ""

        run_btn.click(
            fn=on_generate,
            inputs=[
                url_in,
                file_in,
                num_clips,
                ollama_model,
                input_mode,
                crop_mode,
                focus_region,
                output_style,
                use_manual_regions,
                w_left,
                w_top,
                w_right,
                w_bottom,
                c_left,
                c_top,
                c_right,
                c_bottom,
                m_left,
                m_top,
                m_right,
                m_bottom,
            ],
            outputs=[msg_out, gallery, history_video_dropdown, history_run_dropdown, history_list_md, history_gallery, transcript_dropdown, history_transcript_md],
        )
    return app


if __name__ == "__main__":
    app = build_ui()
    app.launch(
        theme=gr.themes.Soft(),
        css=".video-container { max-width: 100%; margin: 0 auto; } .gr-video { border-radius: 12px; overflow: hidden; } #history-transcript-content { max-height: 320px; overflow-y: auto; }",
    )
