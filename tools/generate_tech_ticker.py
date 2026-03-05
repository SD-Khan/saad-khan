import os
import io
from typing import List
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import imageio.v2 as imageio

try:
    import cairosvg
    HAS_CAIROSVG = True
except Exception:
    HAS_CAIROSVG = False

# -----------------------------
# CONFIG (tweak these)
# -----------------------------
ICONS_DIR = "icons"
OUTPUT_GIF = "ticker.gif"

# Render at 2x then downscale for crispness
SCALE = 2

W, H = 850, 110                 # final size (GitHub friendly)
FPS = 30                        # smoother motion
SECONDS_PER_LOOP = 6            # how long one full cycle takes

ICON_SIZE = 40
GAP = 18
PADDING_X = 18

FRAME_COLOR = (70, 70, 70)
BOARD_BG = (12, 12, 12)
LED_ORANGE = (255, 150, 50)
LED_DIM = (55, 25, 10)

SUPPORTED_EXTS = (".png", ".svg", ".webp", ".jpg", ".jpeg")

LABEL_OVERRIDES = {
    "csharp": "C#",
    "dotnet": ".NET",
    "nodedotjs": "NodeJS",
    "nextdotjs": "NextJS",
    "googlecloud": "GCP",
    "amazonaws": "AWS",
}

# -----------------------------
# HELPERS
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
        if name.startswith("."):  # ignore .DS_Store etc
            continue
        if name.lower().endswith(SUPPORTED_EXTS):
            files.append(os.path.join(folder, name))

    if not files:
        raise FileNotFoundError(f"No icons found in {folder} (supported: {SUPPORTED_EXTS})")

    files.sort(key=lambda p: os.path.splitext(os.path.basename(p))[0].lower())
    return files

def filename_to_label(fp: str) -> str:
    base = os.path.splitext(os.path.basename(fp))[0]
    key = base.lower()
    if key in LABEL_OVERRIDES:
        return LABEL_OVERRIDES[key]
    return base[:1].upper() + base[1:]

def open_icon(fp: str, size: int) -> Image.Image:
    ext = os.path.splitext(fp)[1].lower()

    if ext == ".svg":
        if not HAS_CAIROSVG:
            raise RuntimeError("SVG found but cairosvg missing. Install: pip install cairosvg")
        with open(fp, "rb") as f:
            svg_bytes = f.read()
        png_bytes = cairosvg.svg2png(bytestring=svg_bytes, output_width=size, output_height=size)
        return Image.open(io.BytesIO(png_bytes)).convert("RGBA")

    img = Image.open(fp).convert("RGBA")
    return img.resize((size, size), Image.LANCZOS)

def make_tile(icon: Image.Image, tile_size: int) -> Image.Image:
    tile = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    d.rounded_rectangle([0, 0, tile_size, tile_size], radius=10, fill=(25, 25, 25, 255))

    # slightly smaller icon on tile
    icon2 = icon.resize((int(tile_size * 0.72), int(tile_size * 0.72)), Image.LANCZOS)
    ox = (tile_size - icon2.width) // 2
    oy = (tile_size - icon2.height) // 2
    tile.alpha_composite(icon2, (ox, oy))
    return tile

def led_text_img(text: str, font: ImageFont.ImageFont) -> Image.Image:
    tmp = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    d = ImageDraw.Draw(tmp)
    bbox = d.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(img)
    d2.text((0, 0), text, font=font, fill=LED_DIM)
    d2.text((0, 0), text, font=font, fill=LED_ORANGE)

    # micro-blur to mimic LED glow (kept subtle for crispness)
    return img.filter(ImageFilter.GaussianBlur(radius=0.25))

def build_strip(icon_files: List[str], scale: int) -> Image.Image:
    font = load_font(26 * scale)
    parts = []
    total_w = PADDING_X * scale

    header = led_text_img("TECH STACK  ", font)
    parts.append(("img", header))
    total_w += header.width + GAP * scale

    for fp in icon_files:
        label = filename_to_label(fp)

        icon = open_icon(fp, ICON_SIZE * scale)
        tile = make_tile(icon, ICON_SIZE * scale)
        label_img = led_text_img(label, font)

        parts.append(("icon", tile))
        parts.append(("img", label_img))

        total_w += (ICON_SIZE * scale) + (10 * scale) + label_img.width + (GAP * scale)

    strip_h = max(ICON_SIZE * scale, 32 * scale) + (10 * scale)

    # ✅ Duplicate content for seamless looping
    strip_w = total_w * 2
    strip = Image.new("RGBA", (strip_w, strip_h), (0, 0, 0, 0))

    def paste_once(x0: int):
        x = x0 + (PADDING_X * scale)
        y_mid = strip_h // 2
        for kind, img in parts:
            strip.alpha_composite(img, (x, y_mid - img.height // 2))
            x += img.width + ((10 * scale) if kind == "icon" else (GAP * scale))

    paste_once(0)
    paste_once(total_w)

    return strip, total_w  # return single-cycle width (total_w)

def frame_with_board(strip: Image.Image, offset_x: int, scale: int) -> Image.Image:
    WW, HH = W * scale, H * scale
    base = Image.new("RGB", (WW, HH), FRAME_COLOR)

    inner = Image.new("RGB", (WW - 14 * scale, HH - 14 * scale), BOARD_BG).convert("RGBA")
    y = (inner.height - strip.height) // 2
    inner.alpha_composite(strip, (offset_x, y))

    # scanlines
    scan = Image.new("RGBA", (inner.width, inner.height), (0, 0, 0, 0))
    sd = ImageDraw.Draw(scan)
    for yy in range(0, inner.height, 4 * scale):
        sd.rectangle([0, yy, inner.width, yy + max(1, scale)], fill=(0, 0, 0, 30))
    inner = Image.alpha_composite(inner, scan)

    inner_rgb = inner.convert("RGB").filter(ImageFilter.UnsharpMask(radius=1.2 * scale, percent=120, threshold=3))
    base.paste(inner_rgb, (7 * scale, 7 * scale))

    # ✅ Downscale to final size for crispness
    return base.resize((W, H), Image.LANCZOS)

def main():
    icon_files = list_icon_files(ICONS_DIR)
    print(f"Found {len(icon_files)} icons in {ICONS_DIR}/")

    strip, cycle_w = build_strip(icon_files, SCALE)

    frames = int(FPS * SECONDS_PER_LOOP)

    # ✅ Seamless: offset is modulo cycle_w (single cycle width)
    frames_out = []
    for i in range(frames):
        t = i / frames
        shift = -int(t * cycle_w)  # right -> left over exactly one cycle
        frames_out.append(frame_with_board(strip, shift, SCALE))

    # ✅ Avoid duplicate last frame == first frame (prevents “pause” feel)
    # (we already render exactly one loop; no need to repeat the first frame)
    imageio.mimsave(
        OUTPUT_GIF,
        frames_out,
        format="GIF",
        duration=1.0 / FPS,
        loop=0,  # infinite
    )

    print(f"✅ Wrote {OUTPUT_GIF} ({len(frames_out)} frames, {FPS} fps, seamless loop)")

if __name__ == "__main__":
    main()