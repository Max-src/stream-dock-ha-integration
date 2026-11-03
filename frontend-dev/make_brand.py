"""Draws the integration's brand images (custom_components/stream_dock_ha/brand):
a small pad, 5 x 3 coloured keys and the side band, on a transparent ground.

Run: python frontend-dev/make_brand.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "custom_components" / "stream_dock_ha" / "brand"
KEYS = [
    (37, 99, 235), (124, 58, 237), (220, 38, 38), (14, 165, 233), (16, 185, 129),
    (234, 88, 12), (219, 39, 119), (37, 99, 235), (101, 163, 13), (79, 70, 229),
    (217, 119, 6), (190, 24, 93), (8, 145, 178), (71, 85, 105), (202, 138, 4),
]
BODY = (30, 32, 38)
BAND = (0, 0, 0)
METERS = [(56, 189, 248), (74, 222, 128), (251, 146, 60)]


def pad(width: int) -> Image.Image:
    """The pad, `width` pixels across, drawn 4 times larger then shrunk for smooth edges."""
    big = 4
    w = width * big
    key = w / 7.67  # 5 keys, 4 gaps of a quarter key, the band and the edge
    gap, edge = key * 0.25, key * 0.3
    band_w = key * 0.82
    h = int(edge * 2 + key * 3 + gap * 2)
    image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=key * 0.3, fill=BODY)
    for i, color in enumerate(KEYS):
        x = edge + (i % 5) * (key + gap)
        y = edge + (i // 5) * (key + gap)
        draw.rounded_rectangle((x, y, x + key, y + key), radius=key * 0.16, fill=color)
    band_x = edge + 5 * (key + gap)
    band_h = 2 * (key + gap) + band_w
    band_y = edge + (3 * key + 2 * gap - band_h) / 2
    draw.rounded_rectangle((band_x, band_y, band_x + band_w, band_y + band_h), radius=band_w * 0.18, fill=BAND)
    for i, color in enumerate(METERS):
        y = band_y + i * (key + gap) + band_w * 0.62
        draw.rounded_rectangle((band_x + band_w * 0.15, y, band_x + band_w * 0.85, y + band_w * 0.1), radius=band_w * 0.05, fill=color)
    return image.resize((width, h // big), Image.LANCZOS)


def icon(size: int) -> Image.Image:
    """A square icon: the pad, centred."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    drawn = pad(int(size * 0.94))
    image.alpha_composite(drawn, ((size - drawn.width) // 2, (size - drawn.height) // 2))
    return image


def logo(height: int) -> Image.Image:
    """The pad with the name beside it."""
    drawn = pad(int(height * 1.6))
    drawn = drawn.resize((int(height * 1.6 * height / drawn.height * 0.9), int(height * 0.9)), Image.LANCZOS) if drawn.height > height else drawn
    try:
        font = ImageFont.truetype("segoeuib.ttf", int(height * 0.42))
    except OSError:
        font = ImageFont.load_default()
    text = "Stream Dock HA"
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    box = probe.textbbox((0, 0), text, font=font)
    width = drawn.width + int(height * 0.25) + (box[2] - box[0]) + 4
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    image.alpha_composite(drawn, (0, (height - drawn.height) // 2))
    draw = ImageDraw.Draw(image)
    x = drawn.width + int(height * 0.25)
    draw.text((x, (height - (box[3] - box[1])) // 2 - box[1]), text, font=font, fill=(3, 169, 244))
    return image


OUT.mkdir(parents=True, exist_ok=True)
icon(256).save(OUT / "icon.png")
icon(512).save(OUT / "icon@2x.png")
logo(128).save(OUT / "logo.png")
logo(256).save(OUT / "logo@2x.png")
print("brand images in", OUT)
