"""Pydantic models for API request/response bodies."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class StartRunRequest(BaseModel):
    source: str = Field(
        ...,
        description="URL or absolute local file path to the source video."
    )
    num_clips: int = Field(10, ge=1, le=100)
    ollama_model: str = "mistral"
    whisper_model: str = "base"
    min_duration: float = 15.0
    max_duration: float = 60.0
    burn_captions: bool = True
    smart_crop: bool = True
    crop_mode: str = "auto"
    focus_region: Literal["full", "center"] = "full"
    letterbox_full_width: bool = False
    follow_mode: Literal["auto", "face", "person", "off"] = "auto"
    follow_smoothing: Literal["low", "medium", "high"] = "medium"

    # Manual bbox overrides (optional)
    # Format: (left, top, right, bottom), values from 0.0 to 1.0
    manual_webcam_bbox: tuple[float, float, float, float] | None = None
    manual_chat_bbox: tuple[float, float, float, float] | None = None
    manual_center_bbox: tuple[float, float, float, float] | None = None


class SubtitleSegment(BaseModel):
    """One caption line to burn into the final Reel."""

    start: float = Field(
        ...,
        ge=0,
        description=(
            "Subtitle start in seconds. By default this is an absolute "
            "timestamp in the original source video."
        ),
    )

    end: float = Field(
        ...,
        gt=0,
        description=(
            "Subtitle end in seconds. By default this is an absolute "
            "timestamp in the original source video."
        ),
    )

    text: str = Field(
        ...,
        min_length=1,
        description="Exact spoken caption text.",
    )


class RenderRequest(BaseModel):
    """
    Lightweight final-Reel render request intended for n8n.

    n8n provides:
    - exact clip start/end
    - optional hook
    - subtitle lines + timestamps
    - optional words/phrases to highlight

    AutoAI then performs Smart Crop + speaker tracking + hook + captions
    in the SAME render and outputs one final reel.mp4.
    """

    source: str = Field(
        ...,
        description="YouTube URL or absolute local file path to the source video."
    )

    start: float = Field(
        ...,
        ge=0,
        description="Clip start time in seconds."
    )

    end: float = Field(
        ...,
        gt=0,
        description="Clip end time in seconds."
    )

    smart_crop: bool = True

    crop_mode: Literal[
        "center",
        "event",
        "auto",
        "bottom_strip_rotate",
        "bottom_split_stack",
        "bottom_split_stack_swapped",
        "webcam_chat_stack",
        "webcam_chat_stack_bottom"
    ] = "center"

    focus_region: Literal[
        "full",
        "center"
    ] = "full"

    letterbox_full_width: bool = False

    # Final-Reel text overlay fields.
    hook: str | None = Field(
        default=None,
        description="Short stop-scroll hook displayed at the top of the Reel.",
    )

    hook_duration: float = Field(
        default=4.0,
        ge=0.5,
        le=15.0,
        description="How many seconds the hook remains visible.",
    )

    subtitles: list[SubtitleSegment] = Field(
        default_factory=list,
        description="Caption segments to burn into the final Reel.",
    )

    subtitle_timebase: Literal[
        "source",
        "clip",
    ] = Field(
        default="source",
        description=(
            "'source' means subtitle timestamps refer to the original video; "
            "'clip' means they are already relative to the Reel start."
        ),
    )

    highlight_words: list[str] = Field(
        default_factory=list,
        description=(
            "Words or short phrases to emphasize inside captions. "
            "Matching words are rendered bold with a highlight color."
        ),
    )


class JobSummary(BaseModel):
    id: str
    run_folder: str
    source: str
    status: str
    created_at: float
    started_at: float | None
    finished_at: float | None
    error: str | None = None
    last_stage: str | None = None
    last_message: str | None = None
    progress: float = 0.0


class ShortInfo(BaseModel):
    file: str
    title: str
    transcript: str = ""
    url: str


class RunDetail(BaseModel):
    run_folder: str
    source: str
    source_label: str = ""
    full_transcript: str = ""
    shorts: list[ShortInfo]


class PublishRequest(BaseModel):
    run_folder: str
    file: str
    title: str
    description: str = ""

    platform: Literal[
        "youtube",
        "tiktok",
        "facebook",
        "instagram"
    ]

    mode: Literal[
        "api",
        "browser"
    ] = "api"

    # YouTube: public / unlisted / private
    privacy_status: str | None = None

    tiktok_direct_post: bool = False


class PublishResponse(BaseModel):
    platform: str
    mode: str
    ok: bool
    url: str | None = None
    remote_id: str | None = None
    message: str = ""


class PresetSummary(BaseModel):
    names: list[str]


class SavePresetRequest(BaseModel):
    name: str
    webcam: tuple[float, float, float, float]
    chat: tuple[float, float, float, float]
    center: tuple[float, float, float, float]
