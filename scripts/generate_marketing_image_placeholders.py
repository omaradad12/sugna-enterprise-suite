"""
Generate labeled PNG placeholders for marketing pages under static/assets/images/.
Requires Pillow (see requirements.txt).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "static" / "assets" / "images"

# (filename, width, height, label, bg_rgb, accent_rgb)
SPECS: list[tuple[str, int, int, str, tuple[int, int, int], tuple[int, int, int]]] = [
    ("hero-dashboard.png", 1200, 720, "Hero — dashboard preview", (255, 255, 255), (0, 120, 212)),
    ("finance-module.png", 400, 240, "Module — Finance", (243, 242, 241), (0, 120, 212)),
    ("grants-module.png", 400, 240, "Module — Grants", (243, 242, 241), (0, 120, 212)),
    ("hr-module.png", 400, 240, "Module — HR", (243, 242, 241), (0, 120, 212)),
    ("procurement-module.png", 400, 240, "Module — Procurement", (243, 242, 241), (0, 120, 212)),
    ("hospital-module.png", 400, 240, "Module — Hospital", (243, 242, 241), (0, 120, 212)),
    ("ai-auditor.png", 400, 240, "Module — AI Auditor", (243, 242, 241), (0, 120, 212)),
    ("dashboard-preview.png", 1200, 750, "System dashboard — preview", (250, 249, 248), (0, 120, 212)),
    ("feature-illustration-1.png", 560, 360, "Feature — Multi-tenant", (255, 255, 255), (0, 120, 212)),
    ("feature-illustration-2.png", 560, 360, "Feature — Fund accounting", (255, 255, 255), (0, 120, 212)),
    ("feature-illustration-3.png", 560, 360, "Feature — Grant compliance", (255, 255, 255), (0, 120, 212)),
    ("feature-illustration-4.png", 560, 360, "Feature — Role security", (255, 255, 255), (0, 120, 212)),
    ("about-team.png", 960, 640, "About — team / mission", (243, 242, 241), (0, 120, 212)),
    ("contact-support.png", 720, 520, "Contact — support", (255, 255, 255), (0, 120, 212)),
    ("logo.png", 320, 96, "Sugna Enterprise Suite", (255, 255, 255), (0, 120, 212)),
]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_placeholder(
    path: Path,
    w: int,
    h: int,
    label: str,
    bg: tuple[int, int, int],
    accent: tuple[int, int, int],
) -> None:
    im = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(im)
    font_lg = _font(22 if w > 500 else 16)
    font_sm = _font(14 if w > 500 else 11)
    # Accent bar (Microsoft-style)
    bar_h = max(4, h // 42)
    draw.rectangle([0, 0, w, bar_h], fill=accent)
    # Subtle grid
    step = 48
    grid = (237, 235, 233)
    for x in range(0, w, step):
        draw.line([(x, bar_h), (x, h)], fill=grid, width=1)
    for y in range(bar_h, h, step):
        draw.line([(0, y), (w, y)], fill=grid, width=1)
    # Label
    tw, th = draw.textbbox((0, 0), label, font=font_lg)[2:]
    tx = (w - tw) // 2
    ty = (h - th) // 2 - 8
    draw.text((tx, ty), label, fill=(32, 31, 30), font=font_lg)
    draw.text(
        ((w - draw.textbbox((0, 0), "Placeholder — replace with final asset", font=font_sm)[2]) // 2, ty + th + 12),
        "Placeholder — replace with final asset",
        fill=(96, 94, 92),
        font=font_sm,
    )
    im.save(path, format="PNG", optimize=True)


def draw_favicon(path: Path) -> None:
    size = 32
    im = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle([1, 1, size - 2, size - 2], radius=6, fill=(0, 120, 212, 255))
    font = _font(18)
    draw.text((9, 4), "S", fill=(255, 255, 255, 255), font=font)
    im.save(path, format="PNG")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for fn, w, h, label, bg, accent in SPECS:
        draw_placeholder(OUT / fn, w, h, label, bg, accent)
    draw_favicon(OUT / "favicon.png")
    print(f"Wrote {len(SPECS) + 1} files to {OUT}")


if __name__ == "__main__":
    main()
