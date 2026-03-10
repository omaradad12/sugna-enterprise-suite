from __future__ import annotations

from typing import Tuple

from PIL import Image


def _is_too_light(r: int, g: int, b: int) -> bool:
    # Relative luminance approximation; treat very light colors as background/white.
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return lum > 230


def _lighten_color(r: int, g: int, b: int, factor: float = 0.2) -> Tuple[int, int, int]:
    """Lighten a color towards white."""
    return (
        int(r + (255 - r) * factor),
        int(g + (255 - g) * factor),
        int(b + (255 - b) * factor),
    )


def extract_brand_colors(file_obj) -> Tuple[str | None, str | None]:
    """
    Extract a primary and background color from an uploaded logo file.

    Returns (primary_hex, background_hex). If extraction fails, both are None.
    """
    try:
        img = Image.open(file_obj)
        img = img.convert("RGBA")
        img.thumbnail((64, 64))
        colors = img.getcolors(64 * 64) or []
        # Filter out fully transparent and very light colors (likely background).
        filtered = []
        for count, (r, g, b, a) in colors:
            if a < 10:
                continue
            if _is_too_light(r, g, b):
                continue
            filtered.append((count, (r, g, b)))
        if not filtered:
            return None, None
        # Pick the most frequent remaining color.
        _, (r, g, b) = max(filtered, key=lambda x: x[0])
        primary = f"#{r:02X}{g:02X}{b:02X}"
        lr, lg, lb = _lighten_color(r, g, b, factor=0.6)
        background = f"#{lr:02X}{lg:02X}{lb:02X}"
        return primary, background
    except Exception:
        return None, None

