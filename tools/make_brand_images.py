"""Generate the brand images for home-assistant/brands.

The brands repository is where Home Assistant and HACS fetch the picture shown
next to an integration. Without an entry there, both display the "icon not
available" placeholder -- which is cosmetic, but it is also the first thing
anyone sees when browsing HACS.

Requirements from that repository:
  icon.png     256x256, square, transparent background, no padding
  icon@2x.png  512x512
  logo.png     up to 512x512, transparent background
  logo@2x.png  up to 1024x1024

Run:  python3 tools/make_brand_images.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "brands" / "custom_integrations" / "poolsmart"

WATER_TOP = (56, 178, 232)
WATER_BOTTOM = (14, 96, 168)
FOAM = (233, 248, 255)
WARMTH = (255, 176, 60)


def _squircle_mask(size: int, radius_ratio: float = 0.235) -> Image.Image:
    """A rounded square, the shape Home Assistant's integration tiles expect."""
    mask = Image.new("L", (size * 4, size * 4), 0)
    draw = ImageDraw.Draw(mask)
    radius = int(size * 4 * radius_ratio)
    draw.rounded_rectangle([0, 0, size * 4 - 1, size * 4 - 1], radius=radius, fill=255)
    return mask.resize((size, size), Image.LANCZOS)


def _gradient(size: int) -> Image.Image:
    """Vertical gradient from surface water to deep water."""
    grad = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / max(1, size - 1)
        grad.putpixel(
            (0, y),
            tuple(
                int(WATER_TOP[i] + (WATER_BOTTOM[i] - WATER_TOP[i]) * t) for i in range(3)
            ),
        )
    return grad.resize((size, size), Image.BICUBIC)


def _wave(draw: ImageDraw.ImageDraw, size: int, y: float, amplitude: float,
          thickness: float, colour, phase: float = 0.0, alpha: int = 255) -> None:
    """One sine wave drawn as a thick polyline."""
    points = []
    steps = size * 2
    for i in range(steps + 1):
        x = i / steps * size
        yy = y + math.sin(x / size * math.pi * 2 + phase) * amplitude
        points.append((x, yy))
    draw.line(points, fill=colour + (alpha,), width=max(1, int(thickness)), joint="curve")


def build_icon(size: int) -> Image.Image:
    """A pool surface with a warm sun glint: water plus heat, which is the job."""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    water = _gradient(size).convert("RGBA")
    canvas.paste(water, (0, 0))

    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # A warm sun in the upper right: the heating half of the story. A soft glow
    # alone disappears at 24 pixels, so this is a solid disc with a halo.
    cx, cy = size * 0.70, size * 0.28
    halo_r = size * 0.26
    for step in range(int(halo_r), 0, -1):
        alpha = int(90 * (1 - step / halo_r) ** 1.4)
        draw.ellipse([cx - step, cy - step, cx + step, cy + step], fill=WARMTH + (alpha,))
    disc_r = size * 0.125
    draw.ellipse(
        [cx - disc_r, cy - disc_r, cx + disc_r, cy + disc_r], fill=WARMTH + (255,)
    )

    # Two bold waves. Three read as texture at small sizes; two read as water.
    _wave(draw, size, size * 0.63, size * 0.075, size * 0.115, FOAM, 0.0, 255)
    _wave(draw, size, size * 0.85, size * 0.065, size * 0.095, FOAM, 2.4, 225)

    canvas = Image.alpha_composite(canvas, overlay)
    canvas.putalpha(_squircle_mask(size))
    return canvas


def build_logo(width: int, height: int) -> Image.Image:
    """Icon plus wordmark, on transparency."""
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    icon_size = height
    canvas.paste(build_icon(icon_size), (0, 0), build_icon(icon_size))

    draw = ImageDraw.Draw(canvas)
    text = "PoolSmart"
    font = None
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        if Path(candidate).exists():
            font = ImageFont.truetype(candidate, int(height * 0.42))
            break
    if font is None:
        font = ImageFont.load_default()

    box = draw.textbbox((0, 0), text, font=font)
    ty = (height - (box[3] - box[1])) / 2 - box[1]
    draw.text((icon_size + height * 0.18, ty), text, font=font, fill=WATER_BOTTOM + (255,))
    return canvas


def _trim(image: Image.Image) -> Image.Image:
    """Crop transparent padding, which the brands repository does not allow."""
    bbox = image.getchannel("A").getbbox()
    return image.crop(bbox) if bbox else image


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    build_icon(256).save(OUT / "icon.png")
    build_icon(512).save(OUT / "icon@2x.png")
    _trim(build_logo(1024, 256)).save(OUT / "logo.png")
    _trim(build_logo(2048, 512)).save(OUT / "logo@2x.png")
    for path in sorted(OUT.iterdir()):
        with Image.open(path) as img:
            print(f"{path.name}: {img.size[0]}x{img.size[1]} {img.mode}")


if __name__ == "__main__":
    main()
