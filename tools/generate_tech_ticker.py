import os
import io
from typing import List

from PIL import Image, ImageDraw, ImageFilter
import imageio.v2 as imageio

try:
    import cairosvg
    HAS_CAIROSVG = True
except Exception:
    HAS_CAIROSVG = False


# -----------------------------
# CONFIG
# -----------------------------
ICONS_DIR = "icons"
OUTPUT_GIF = "ticker.gif"

W, H = 900, 140          # higher output resolution (GitHub still ok)
SCALE = 4                # render 4x then downscale -> crisp
FPS = 30
SECONDS_PER_LOOP = 7     # slower, smoother

ICON_TILE = 62           # tile size (final size before SCALE)
ICON_PAD = 10            # padding inside tile
GAP = 18                 # gap between tiles

FRAME_COLOR = (70, 70, 70)
BOARD_BG = (10, 10, 10)
TILE_BG = (28, 28, 28)

SUPPORTED_EXTS = (".png", ".svg", ".webp", ".jpg", ".jpeg")


# -----------------------------
# ICON LOADING
# -----------------------------
def list_icon_files(folder: str) -> List[str]:
    if not os.path.isdir(folder):
        raise FileNotFoundError(f"Icons folder not found: {folder}")

    files = []
    for name in os.listdir(folder):
        if name.startswith("."):
            continue
        if name.lower().endswith(SUPPORTED_EXTS):
            files.append(os.path.join(folder, name))

    if not files:
        raise FileNotFoundError(f"No icon files found in {folder}/")

    files.sort(key=lambda p: os.path.splitext(os.path.basename(p))[0].lower())
    return files


def open_icon(fp: str, size: int) -> Image.Image:
    ext = os.path.splitext(fp)[1].lower()

    if ext == ".svg":
        if not HAS_CAIROSVG:
            raise RuntimeError("SVG icons found but cairosvg not installed. Run: pip install cairosvg")
        with open(fp, "rb") as f:
            svg_bytes = f.read()
        png_bytes = cairosvg.svg2png(bytestring=svg_bytes, output_width=size, output_height=size)
        return Image.open(io.BytesIO(png_bytes)).convert("RGBA")

    img = Image.open(fp).convert("RGBA")
    return img.resize((size, size), Image.LANCZOS)


# -----------------------------
# RENDERING
# -----------------------------
def make_icon_tile(icon: Image.Image, tile_size: int, pad: int) -> Image.Image:
    tile = Image.new("RGBA", (tile_size, tile_size), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)

    r = max(10, tile_size // 6)
    d.rounded_rectangle([0, 0, tile_size, tile_size], radius=r, fill=(*TILE_BG, 255))

    target = tile_size - pad * 2

    # Fit icon inside, preserve detail
    icon2 = icon.resize((target, target), Image.LANCZOS)

    ox = (tile_size - icon2.width) // 2
    oy = (tile_size - icon2.height) // 2
    tile.alpha_composite(icon2, (ox, oy))
    return tile


def build_strip(icon_files: List[str], scale: int):
    tile = ICON_TILE * scale
    pad = ICON_PAD * scale
    gap = GAP * scale

    tiles = []
    for fp in icon_files:
        # render each icon at best detail for the tile
        icon = open_icon(fp, size=(tile - pad * 2))
        tiles.append(make_icon_tile(icon, tile_size=tile, pad=pad))

    strip_h = tile
    cycle_w = (len(tiles) * tile) + ((len(tiles) - 1) * gap)

    # duplicate once for seamless scroll
    strip = Image.new("RGBA", (cycle_w * 2, strip_h), (0, 0, 0, 0))

    def paste_once(x0: int):
        x = x0
        for t in tiles:
            strip.alpha_composite(t, (x, 0))
            x += tile + gap

    paste_once(0)
    paste_once(cycle_w)

    return strip, cycle_w


def render_frame(strip: Image.Image, offset_x: int, scale: int) -> Image.Image:
    WW, HH = W * scale, H * scale
    base = Image.new("RGB", (WW, HH), FRAME_COLOR)

    inner = Image.new("RGB", (WW - 14 * scale, HH - 14 * scale), BOARD_BG).convert("RGBA")
    y = (inner.height - strip.height) // 2
    inner.alpha_composite(strip, (offset_x, y))

    # subtle scanlines
    scan = Image.new("RGBA", (inner.width, inner.height), (0, 0, 0, 0))
    sd = ImageDraw.Draw(scan)
    for yy in range(0, inner.height, 6 * scale):
        sd.rectangle([0, yy, inner.width, yy + max(1, scale)], fill=(0, 0, 0, 20))
    inner = Image.alpha_composite(inner, scan)

    inner_rgb = inner.convert("RGB").filter(
        ImageFilter.UnsharpMask(radius=1.2 * scale, percent=160, threshold=2)
    )

    base.paste(inner_rgb, (7 * scale, 7 * scale))

    # downscale to final
    return base.resize((W, H), Image.LANCZOS)


# -----------------------------
# GIF EXPORT (FULL COLOR)
# -----------------------------
def make_global_palette(frames_rgb: List[Image.Image]) -> Image.Image:
    # Build a single palette from a representative frame to preserve color consistency
    # (frame 0 is usually fine; you can also merge a few frames if you want)
    pal = frames_rgb[0].convert("P", palette=Image.Palette.ADAPTIVE, colors=256)
    return pal


def apply_palette(frame_rgb: Image.Image, palette_img: Image.Image) -> Image.Image:
    # Apply the same palette to every frame; avoid dithering to keep logos cleaner
    return frame_rgb.quantize(palette=palette_img, dither=Image.Dither.NONE)


def main():
    icon_files = list_icon_files(ICONS_DIR)
    print(f"Found {len(icon_files)} icons in {ICONS_DIR}/")

    strip, cycle_w = build_strip(icon_files, SCALE)

    frames_count = int(FPS * SECONDS_PER_LOOP)

    # render in RGB first (high quality)
    frames_rgb = []
    for i in range(frames_count):
        t = i / frames_count
        shift = -int(t * cycle_w)  # exactly one cycle => seamless loop
        frames_rgb.append(render_frame(strip, shift, SCALE))

    # global palette to keep color stable
    palette_img = make_global_palette(frames_rgb)
    frames_p = [apply_palette(f, palette_img) for f in frames_rgb]

    # write animated gif (infinite loop)
    imageio.mimsave(
        OUTPUT_GIF,
        frames_p,
        format="GIF",
        duration=1.0 / FPS,
        loop=0
    )

    print(f"✅ Wrote {OUTPUT_GIF} (color, icons-only, seamless loop)")

if __name__ == "__main__":
    main()