"""FFmpeg color grading presets used by AutoAI final Reel rendering."""

from __future__ import annotations


# Moderate-to-visible presets for social/Reels content.
# Values are intentionally stronger than the previous version,
# but still designed to avoid extreme clipping or unnatural skin tones.
COLOR_PRESETS: dict[str, str | None] = {
    # No color changes.
    "none": None,

    # Clean, lightly polished correction.
    "natural": (
        "eq="
        "contrast=1.08:"
        "brightness=0.02:"
        "saturation=1.08:"
        "gamma=1.01"
    ),

    # Warmer / golden look.
    "warm": (
        "eq="
        "contrast=1.10:"
        "brightness=0.02:"
        "saturation=1.10:"
        "gamma=1.01,"
        "colorbalance="
        "rs=.060:"
        "gs=.015:"
        "bs=-.050"
    ),

    # Cooler, cleaner tech look.
    "cool": (
        "eq="
        "contrast=1.10:"
        "brightness=0.00:"
        "saturation=1.05:"
        "gamma=1.00,"
        "colorbalance="
        "rs=-.040:"
        "gs=.005:"
        "bs=.060"
    ),

    # Film-like contrast with slightly reduced saturation,
    # cooler shadows and warmer highlights.
    "cinematic": (
        "eq="
        "contrast=1.18:"
        "brightness=-0.02:"
        "saturation=0.90:"
        "gamma=0.97,"
        "colorbalance="
        "bs=.060:"
        "rm=.015:"
        "rh=.060:"
        "bh=-.015"
    ),

    # Punchier social-media look.
    "vibrant": (
        "eq="
        "contrast=1.18:"
        "brightness=0.02:"
        "saturation=1.30:"
        "gamma=1.02"
    ),

    # Moody low-key look.
    "dark": (
        "eq="
        "contrast=1.18:"
        "brightness=-0.08:"
        "saturation=0.92:"
        "gamma=0.92"
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
