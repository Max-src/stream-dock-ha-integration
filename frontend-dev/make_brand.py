"""Makes the integration's brand images (custom_components/stream_dock_ha/brand)
from the app's own icon, the one Windows shows for it, so Home Assistant shows
the same.

First, in the app: cargo test -- --ignored make_brand_icons (writes
app/target/brand), then: python frontend-dev/make_brand.py [that folder]
"""

from pathlib import Path
import shutil
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "custom_components" / "stream_dock_ha" / "brand"
ICONS = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent.parent / "app" / "target" / "brand"


def logo(icon: Image.Image, height: int) -> Image.Image:
    """The icon with the name beside it."""
    mark = icon.resize((height, height), Image.LANCZOS)
    try:
        font = ImageFont.truetype("segoeuib.ttf", int(height * 0.42))
    except OSError:
        font = ImageFont.load_default()
    text = "Stream Dock HA"
    box = ImageDraw.Draw(Image.new("RGBA", (1, 1))).textbbox((0, 0), text, font=font)
    space = int(height * 0.22)
    image = Image.new("RGBA", (height + space + box[2] - box[0] + 4, height), (0, 0, 0, 0))
    image.alpha_composite(mark, (0, 0))
    ImageDraw.Draw(image).text(
        (height + space, (height - (box[3] - box[1])) // 2 - box[1]), text, font=font, fill=(59, 120, 238)
    )
    return image


OUT.mkdir(parents=True, exist_ok=True)
for name in ("icon.png", "icon@2x.png"):
    shutil.copyfile(ICONS / name, OUT / name)
big = Image.open(ICONS / "icon@2x.png").convert("RGBA")
logo(big, 128).save(OUT / "logo.png")
logo(big, 256).save(OUT / "logo@2x.png")
print("brand images in", OUT)
