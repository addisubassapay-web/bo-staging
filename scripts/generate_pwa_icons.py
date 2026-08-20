"""Generate PWA icons for Merchari-global (192x192 and 512x512).

The design mirrors the header logo: gradient background (#FF7A18 -> #FF211F) with a rounded
mask, subtle inner highlight, and a bold "M" mark centered.

Run manually if brand assets change:
    python /app/scripts/generate_pwa_icons.py
"""
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pathlib import Path

OUT = Path("/app/frontend/public")
SIZES = [192, 512]

# Brand palette
ORANGE = (255, 122, 24)   # #FF7A18
RED    = (255,  33,  31)  # #FF211F


def _gradient(size: int) -> Image.Image:
    """Diagonal gradient from top-left ORANGE to bottom-right RED."""
    img = Image.new("RGB", (size, size), ORANGE)
    px  = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            r = int(ORANGE[0] + (RED[0] - ORANGE[0]) * t)
            g = int(ORANGE[1] + (RED[1] - ORANGE[1]) * t)
            b = int(ORANGE[2] + (RED[2] - ORANGE[2]) * t)
            px[x, y] = (r, g, b)
    return img


def _rounded_mask(size: int, radius_ratio: float = 0.22) -> Image.Image:
    """Alpha mask for a rounded-square icon (also used as maskable)."""
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    r = int(size * radius_ratio)
    d.rounded_rectangle([0, 0, size, size], radius=r, fill=255)
    return mask


def _highlight(size: int) -> Image.Image:
    """Soft top-left highlight for warm feel."""
    h = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    d = ImageDraw.Draw(h)
    r = int(size * 0.85)
    d.ellipse([-int(size * 0.35), -int(size * 0.35), r, r], fill=(255, 255, 255, 60))
    h = h.filter(ImageFilter.GaussianBlur(radius=size // 12))
    return h


def _find_bold_font(px_size: int) -> ImageFont.FreeTypeFont:
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        p = Path(candidate)
        if p.exists():
            return ImageFont.truetype(str(p), px_size)
    return ImageFont.load_default()


def _draw_M(size: int) -> Image.Image:
    """Draw the 'M' letter mark centered."""
    layer = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    d = ImageDraw.Draw(layer)
    # Font size tuned for maskable safe zone (~80% inner circle)
    font_px = int(size * 0.6)
    font = _find_bold_font(font_px)
    text = "M"
    try:
        bbox = d.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        offset_x, offset_y = bbox[0], bbox[1]
    except AttributeError:  # very old Pillow
        tw, th = d.textsize(text, font=font)
        offset_x, offset_y = 0, 0
    x = (size - tw) // 2 - offset_x
    y = (size - th) // 2 - offset_y - int(size * 0.02)  # optical nudge up
    # Soft drop shadow for warmth
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.text((x + int(size * 0.015), y + int(size * 0.02)), text, font=font, fill=(0, 0, 0, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=max(2, size // 80)))
    layer = Image.alpha_composite(layer, shadow)
    d = ImageDraw.Draw(layer)
    d.text((x, y), text, font=font, fill=(255, 255, 255, 255))
    return layer


def make_icon(size: int) -> Image.Image:
    base = _gradient(size).convert("RGBA")
    base = Image.alpha_composite(base, _highlight(size))
    base = Image.alpha_composite(base, _draw_M(size))

    # Compose onto transparent canvas via rounded mask (maskable-safe: keeps color to edges).
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(base, (0, 0), _rounded_mask(size))
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        img = make_icon(size)
        target = OUT / f"icon-{size}.png"
        img.save(target, "PNG", optimize=True)
        print(f"wrote {target} ({size}x{size})")

    # Also produce a small favicon.
    fav = make_icon(64).resize((32, 32), Image.LANCZOS)
    fav.save(OUT / "favicon.png", "PNG", optimize=True)
    print(f"wrote {OUT / 'favicon.png'} (32x32)")


if __name__ == "__main__":
    main()
