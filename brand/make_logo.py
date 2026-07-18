"""Generate Bugne brand assets for home-assistant/brands.

icon: white bold "B" on a #2196F3 rounded square, full bleed.
logo: "Bugne" wordmark in DejaVuSans-Bold, #2196F3, transparent bg, trimmed.
Everything drawn 4x supersampled then downscaled for clean edges.
"""
from PIL import Image, ImageDraw, ImageFont
import os

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
BLUE = (0x21, 0x96, 0xF3, 255)
OUT = os.path.join(os.path.dirname(__file__), "brand")
os.makedirs(OUT, exist_ok=True)
SS = 4  # supersampling factor


def make_icon(size, name):
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    radius = int(s * 0.22)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=BLUE)
    font = ImageFont.truetype(FONT, int(s * 0.72))
    bbox = d.textbbox((0, 0), "B", font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((s - w) / 2 - bbox[0], (s - h) / 2 - bbox[1]), "B",
           font=font, fill=(255, 255, 255, 255))
    img = img.resize((size, size), Image.LANCZOS)
    img.save(os.path.join(OUT, name), optimize=True)


def make_logo(height, name):
    # Render big, trim to the ink bbox, then scale to the target height.
    font = ImageFont.truetype(FONT, 400)
    tmp = Image.new("RGBA", (2000, 800), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    d.text((50, 50), "Bugne", font=font, fill=BLUE)
    tmp = tmp.crop(tmp.getbbox())
    w = round(tmp.width * height / tmp.height)
    tmp.resize((w, height), Image.LANCZOS).save(os.path.join(OUT, name),
                                                optimize=True)


make_icon(256, "icon.png")
make_icon(512, "icon@2x.png")
make_logo(128, "logo.png")
make_logo(256, "logo@2x.png")
for f in sorted(os.listdir(OUT)):
    im = Image.open(os.path.join(OUT, f))
    print(f, im.size, im.mode)
