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


class RenderRequest(BaseModel):
    """
    Lightweight render request intended for n8n.

    This skips Whisper, Ollama, and automatic clip selection.
    n8n provides the exact start/end timestamps and the video engine
    only downloads, crops, reframes, and renders the selected segment.
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
