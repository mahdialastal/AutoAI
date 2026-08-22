"""FFmpeg color grading presets used by AutoAI final Reel rendering."""

from __future__ import annotations


# Keep the presets intentionally moderate.
# The goal is to improve the look without destroying skin tones
# or clipping highlights/shadows.
COLOR_PRESETS: dict[str, str | None] = {
    # No color changes.
    "none": None,

    # Clean, lightly polished correction.
    "natural": (
        "eq="
        "contrast=1.04:"
        "brightness=0.01:"
        "saturation=1.05:"
        "gamma=1.01"
    ),

    # Slightly warmer / golden look.
    "warm": (
        "eq="
        "contrast=1.05:"
        "brightness=0.01:"
        "saturation=1.07:"
        "gamma=1.01,"
        "colorbalance="
        "rs=.035:"
        "gs=.012:"
        "bs=-.025"
    ),

    # Slightly cooler, cleaner tech look.
    "cool": (
        "eq="
        "contrast=1.05:"
        "brightness=0.00:"
        "saturation=1.02:"
        "gamma=1.00,"
        "colorbalance="
        "rs=-.025:"
        "gs=.005:"
        "bs=.035"
    ),

    # Film-like contrast with subtle cool shadows / warm highlights.
    "cinematic": (
        "eq="
        "contrast=1.10:"
        "brightness=-0.01:"
        "saturation=0.96:"
        "gamma=0.98,"
        "colorbalance="
        "bs=.025:"
        "rm=.012:"
        "rh=.025:"
        "bh=-.010"
    ),

    # Punchier social-media look.
    "vibrant": (
        "eq="
        "contrast=1.10:"
        "brightness=0.01:"
        "saturation=1.20:"
        "gamma=1.01"
    ),

    # Moody low-key look.
    "dark": (
        "eq="
        "contrast=1.12:"
        "brightness=-0.055:"
        "saturation=0.92:"
        "gamma=0.94"
    ),
}


def get_color_filter(
    preset: str | None,
) -> str | None:
    """
    Return the FFmpeg video-filter expression for a preset.

    Unknown/empty values safely fall back to no color filter.
    """
    key = str(preset or "none").strip().lower()
    return COLOR_PRESETS.get(key)


def available_color_presets() -> list[str]:
    """Return all supported preset names."""
    return list(COLOR_PRESETS.keys())
