import os
import io
from typing import List, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import imageio.v2 as imageio

try:
    import cairosvg
    HAS_CAIROSVG = True
except Exception:
    HAS_CAIROSVG = False

# -----------------------------
# Config
# -----------------------------
OUTPUT_GIF = "ticker.gif"

# Folder containing icon files (png/svg/webp/jpg)
ICONS_DIR = "icons"

# Final GIF size (good for GitHub readme)
W, H = 850, 110

FPS = 25
DURATION_SEC = 10
FRAMES = FPS * DURATION_SEC

ICON_SIZE = 40
GAP = 18
PADDING_X = 18

# LED Board style
FRAME_COLOR = (70, 70, 70)
BOARD_BG = (12, 12, 12)
LED_ORANGE = (255, 150, 50)
LED_DIM = (55, 25, 10)

SUPPORTED_EXTS = (".png", ".svg", ".webp", ".jpg", ".jpeg")

# Optional mapping from filename -> display label
# Example: "nodedotjs" -> "NodeJS"
LABEL_OVERRIDES = {
    "csharp": "C#",
    "dotnet": ".NET",
    "nodedotjs": "NodeJS",
    "nextdotjs": "NextJS",
    "googlecloud": "GCP",
    "amazonaws": "AWS",
}


# -----------------------------
# Helpers
# -----------------------------
def load_font(size: int):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial.ttf",
        "C:\\Windows\\Fonts\\consola.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size=size)
    return ImageFont.load_default()


def list_icon_files(folder: str) -> List[str]:
    if not os.path.isdir(folder):
        raise FileNotFoundError(f"Icons folder not found: {folder}")

    files = []
    for name in os.listdir(folder):
        if name.lower().endswith(SUPPORTED_EXTS):
            files.append(os.path.join(folder, name))

    if not files:
        raise FileNotFoundError(f"No icon files found in {folder} with extensions: {SUPPORTED_EXTS}")

    # Sort for stable output: by filename (without ext)
    files.sort(key=lambda p: os.path.splitext(os.path.basename(p))[0].lower())
    return files


def filename_to_label(fp: str) -> str:
    base = os.path.splitext(os.path.basename(fp))[0]
    key = base.lower()

    if key in LABEL_OVERRIDES:
        return LABEL_OVERRIDES[key]

    # default: "apachespark" -> "Apachespark" (simple fallback)
    # You can improve this if you want (e.g., split words), but for logos it's usually fine.
    return base[:1].upper() + base[1:]


def open_icon(fp: str, size: int) -> Image.Image:
    ext = os.path.splitext(fp)[1].lower()

    if ext == ".svg":
        if not HAS_CAIROSVG:
            raise RuntimeError("Found SVG icons but cairosvg is not installed. Run: pip install cairosvg")
        png_bytes = cairosvg.svg2png(url=fp, output_width=size, output_height=size)
        return Image.open(io.BytesIO(png_bytes)).convert("RGBA")

    # bitmap
    img = Image.open(fp).convert("RGBA")
    return img.resize((size, size), Image.LANCZOS)


def make_tile(icon: Image.Image, tile_size: int) -> Image.Image:
    tile = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)

    # rounded dark tile
    radius = 10
    d.rounded_rectangle([0, 0, tile_size, tile_size], radius=radius, fill=(25, 25, 25, 255))

    # center icon (slightly smaller)
    icon2 = icon.resize((int(tile_size * 0.72), int(tile_size * 0.72)), Image.LANCZOS)
    ox = (tile_size - icon2.width) // 2
    oy = (tile_size - icon2.height) // 2
    tile.alpha_composite(icon2, (ox, oy))
    return tile


def led_text_img(text: str, font: ImageFont.ImageFont) -> Image.Image:
    tmp = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    bbox = d.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(img)

    # dim underlayer + bright layer
    d2.text((0, 0), text, font=font, fill=LED_DIM)
    d2.text((0, 0), text, font=font, fill=LED_ORANGE)
    return img


def build_strip(icon_files: List[str]) -> Image.Image:
    font = load_font(26)

    parts: List[Tuple[str, Image.Image]] = []
    total_w = PADDING_X

    # header
    header = led_text_img("TECH STACK  ", font)
    parts.append(("img", header))
    total_w += header.width + GAP

    for fp in icon_files:
        label = filename_to_label(fp)

        icon = open_icon(fp, ICON_SIZE)
        tile = make_tile(icon, ICON_SIZE)
        label_img = led_text_img(label, font)

        parts.append(("icon", tile))
        parts.append(("img", label_img))

        total_w += ICON_SIZE + 10 + label_img.width + GAP

    strip_h = max(ICON_SIZE, 32) + 10

    # duplicate once for seamless loop
    strip_w = total_w * 2
    strip = Image.new("RGBA", (strip_w, strip_h), (0, 0, 0, 0))

    def paste_once(x0: int):
        x = x0 + PADDING_X
        y_mid = strip_h // 2
        for kind, img in parts:
            strip.alpha_composite(img, (x, y_mid - img.height // 2))
            x += img.width + (10 if kind == "icon" else GAP)

    paste_once(0)
    paste_once(total_w)

    return strip


def frame_with_board(scrolling_strip: Image.Image, offset_x: int) -> Image.Image:
    base = Image.new("RGB", (W, H), FRAME_COLOR)
    inner = Image.new("RGB", (W - 14, H - 14), BOARD_BG).convert("RGBA")

    y = (inner.height - scrolling_strip.height) // 2
    inner.alpha_composite(scrolling_strip, (offset_x, y))

    # scanlines
    scan = Image.new("RGBA", (inner.width, inner.height), (0, 0, 0, 0))
    sd = ImageDraw.Draw(scan)
    for yy in range(0, inner.height, 4):
        sd.rectangle([0, yy, inner.width, yy + 1], fill=(0, 0, 0, 35))
    inner = Image.alpha_composite(inner, scan)

    inner_rgb = inner.convert("RGB").filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=3))
    base.paste(inner_rgb, (7, 7))
    return base


def main():
    icon_files = list_icon_files(ICONS_DIR)
    print(f"Found {len(icon_files)} icons in {ICONS_DIR}/")

    strip = build_strip(icon_files)

    loop_w = strip.width // 2
    px_per_frame = loop_w / FRAMES

    frames = []
    for i in range(FRAMES):
        shift = -int(i * px_per_frame)  # right -> left
        frames.append(frame_with_board(strip, shift))

    imageio.mimsave(OUTPUT_GIF, frames, format="GIF", duration=1.0 / FPS)
    print(f"✅ Wrote {OUTPUT_GIF} ({FRAMES} frames)")


if __name__ == "__main__":
    main()