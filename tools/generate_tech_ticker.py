import os
import math
import time
import json
import urllib.request
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
import cairosvg

def force_svg_fill_white(svg_bytes: bytes) -> bytes:
    """
    Simple Icons SVGs often use `fill="currentColor"`.
    We replace it with white for consistent dark-mode rendering.
    """
    s = svg_bytes.decode("utf-8", errors="ignore")
    s = s.replace('fill="currentColor"', 'fill="#ffffff"')
    return s.encode("utf-8")

# ----------------------------
# Config
# ----------------------------
OUTPUT_GIF = "assets/tech-ticker.gif"

# Canvas config
W = 1200          # width of ticker
H = 140           # height of ticker
FPS = 24          # frames per second
DURATION_SEC = 10 # duration for one full loop
PX_PER_FRAME = 4  # scroll speed

# Style
BG = (10, 12, 18)           # near-black (GitHub dark friendly)
FG = (226, 232, 240)        # near-white
PILL_BG = (24, 27, 36)      # pill background
PILL_BORDER = (45, 55, 72)  # subtle border
LABEL_COLOR = (226, 232, 240)

ICON_SIZE = 28
PILL_H = 44
PILL_PAD_X = 14
PILL_GAP = 14

# List of (label, simpleicons slug)
# Use Simple Icons slugs: https://simpleicons.org/
TECH = [
    # Languages / Runtime
    ("Java", "java"),
    ("Python", "python"),
    ("C Sharp", "csharp"),
    ("DotNet", "dotnet"),
    ("NodeJS", "nodedotjs"),
    ("NextJS", "nextdotjs"),

    # Cloud / AWS
    ("AWS", "amazonaws"),
    ("ECS", "amazonecs"),
    ("S3", "amazons3"),
    ("Lambda", "awslambda"),
    ("ALB", "awselasticloadbalancing"),
    ("EMR", "awselasticmapreduce"),
    ("Step Functions", "awsstepfunctions"),
    ("DynamoDB", "awsdynamodb"),
    ("RDS", "awsrds"),
    ("EKS", "awsecs"),
    {"ApiGateway", "apigateway"}

    # GCP
    ("GCP", "googlecloud"),

    # Data
    ("Spark", "apachespark"),
    ("Snowflake", "snowflake"),
    ("DBT", "dbt"),
    ("Fivetran", "fivetran"),
    ("Shopify", "shopify"),

    # Databases
    {"PostgreSQL", "postgresql"},
    {"Athena", "athena"},
    {"Redshift", "redshift"},
    {"Qdrant", "qdrant"},
    {"Supabase", "supabase"},

    # AI
    ("Llama", "meta"),
    ("Ollama", "ollama"),
    ("Qwen", "alibabacloud"),
]

# Simple Icons CDN SVG (stable)
ICON_URL = "https://cdn.jsdelivr.net/npm/simple-icons@v11/icons/{slug}.svg"

# ----------------------------
# Helpers
# ----------------------------
def ensure_dirs():
    os.makedirs("assets", exist_ok=True)
    os.makedirs("tools/.cache/icons", exist_ok=True)

def download_svg(slug: str) -> bytes:
    cache_path = f"tools/.cache/icons/{slug}.svg"
    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            return f.read()

    url = ICON_URL.format(slug=slug)
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = resp.read()

    with open(cache_path, "wb") as f:
        f.write(data)
    return data

def svg_to_png(svg_bytes: bytes, size: int) -> Image.Image:
    png_bytes = cairosvg.svg2png(bytestring=svg_bytes, output_width=size, output_height=size)
    img = Image.open(BytesIO(png_bytes)).convert("RGBA")
    return img

def load_font(size: int) -> ImageFont.ImageFont:
    # GitHub Actions ubuntu has DejaVu fonts
    # Fallback to default if missing
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

def measure_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]

def draw_pill(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, r: int):
    # Rounded rectangle
    draw.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=PILL_BG, outline=PILL_BORDER, width=1)

def build_strip() -> Image.Image:
    font = load_font(18)
    # temporary canvas for measurement
    tmp = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    dtmp = ImageDraw.Draw(tmp)

    pills = []
    for label, slug in TECH:
        svg = force_svg_fill_white(download_svg(slug))
        icon = svg_to_png(svg, ICON_SIZE)

        text_w, text_h = measure_text(dtmp, label, font)
        pill_w = PILL_PAD_X * 2 + ICON_SIZE + 10 + text_w
        pill = Image.new("RGBA", (pill_w, PILL_H), (0, 0, 0, 0))
        dp = ImageDraw.Draw(pill)
        draw_pill(dp, 0, 0, pill_w, PILL_H, r=14)

        # icon
        pill.paste(icon, (PILL_PAD_X, (PILL_H - ICON_SIZE) // 2), icon)

        # label
        tx = PILL_PAD_X + ICON_SIZE + 10
        ty = (PILL_H - text_h) // 2 - 1
        dp.text((tx, ty), label, font=font, fill=LABEL_COLOR)
        pills.append(pill)

    # Concatenate pills into one long strip
    strip_w = sum(p.size[0] for p in pills) + PILL_GAP * (len(pills) - 1)
    strip_h = H
    strip = Image.new("RGBA", (strip_w, strip_h), (0, 0, 0, 0))

    x = 0
    y = (strip_h - PILL_H) // 2
    for i, p in enumerate(pills):
        strip.paste(p, (x, y), p)
        x += p.size[0] + PILL_GAP

    return strip

def make_frames(strip: Image.Image):
    frames = []
    total_frames = int(FPS * DURATION_SEC)
    # To loop seamlessly, duplicate strip and scroll across one full strip width
    strip_w = strip.size[0]
    combined = Image.new("RGBA", (strip_w * 2, H), (0, 0, 0, 0))
    combined.paste(strip, (0, 0), strip)
    combined.paste(strip, (strip_w, 0), strip)

    for i in range(total_frames):
        offset = (i * PX_PER_FRAME) % strip_w
        frame = Image.new("RGB", (W, H), BG)
        # Crop a window from combined strip
        window = combined.crop((offset, 0, offset + W, H))
        frame.paste(window, (0, 0), window)
        frames.append(frame)

    return frames, total_frames

def save_gif(frames, total_frames):
    os.makedirs(os.path.dirname(OUTPUT_GIF), exist_ok=True)
    duration_ms = int(1000 / FPS)

    # Convert to palette mode for smaller gif
    pal_frames = []
    for f in frames:
        pal_frames.append(f.convert("P", palette=Image.Palette.ADAPTIVE, colors=256))

    pal_frames[0].save(
        OUTPUT_GIF,
        save_all=True,
        append_images=pal_frames[1:],
        optimize=False,
        duration=duration_ms,
        loop=0
    )

def main():
    ensure_dirs()
    strip = build_strip()
    frames, total_frames = make_frames(strip)
    save_gif(frames, total_frames)
    print(f"Generated {OUTPUT_GIF} with {total_frames} frames")

if __name__ == "__main__":
    main()