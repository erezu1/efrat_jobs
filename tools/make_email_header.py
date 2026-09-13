"""Draw the email header image (logo + "BioJobs" wordmark) so it matches the website exactly.

Email clients can't load web fonts or show gradient text, so the header is a PNG embedded in the
mail. Re-run after changing the logo or name:  .venv/bin/python tools/make_email_header.py
Requires Pillow (dev only; not needed by the daily workflow).
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "icons" / "email-header.png"
FONT = ROOT / "tools" / "fonts" / "Sora.ttf"   # SIL Open Font License
SCALE = 3                                        # render at 3x for sharp display on phones
PURPLE, PINK = (0x7B, 0x2D, 0x8E), (0xD6, 0x40, 0x9F)
LOGO, GAP, TEXT_SIZE, NAME = 44, 12, 30, "BioJobs"


def gradient(w: int, h: int) -> Image.Image:
    """135° purple→pink gradient, same as the CSS."""
    g = Image.new("RGB", (w, h))
    px = g.load()
    for y in range(h):
        for x in range(w):
            t = (x / max(w - 1, 1) + y / max(h - 1, 1)) / 2
            px[x, y] = tuple(round(a + (b - a) * t) for a, b in zip(PURPLE, PINK))
    return g


def logo(size: int) -> Image.Image:
    s = size / 64
    tile = gradient(size, size).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=round(14 * s), fill=255)
    tile.putalpha(mask)
    d = ImageDraw.Draw(tile)

    def curve(p0, c1, c2, p3, n=40):
        return [tuple(((1 - t) ** 3) * a + 3 * ((1 - t) ** 2) * t * b + 3 * (1 - t) * t * t * c + t ** 3 * e
                      for a, b, c, e in zip(p0, c1, c2, p3)) for t in (i / n for i in range(n + 1))]

    def strand(x0, x1):
        # M x0 10 C x0 23 x1 23 x1 32 S x0 41 x0 54  (same path as the SVG icon)
        pts = curve((x0, 10), (x0, 23), (x1, 23), (x1, 32)) + curve((x1, 32), (x1, 41), (x0, 41), (x0, 54))
        pts = [(x * s, y * s) for x, y in pts]
        w = round(4.5 * s)
        d.line(pts, fill="white", width=w, joint="curve")
        for x, y in (pts[0], pts[-1]):
            d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill="white")

    strand(21, 43)
    strand(43, 21)
    rung = (255, 255, 255, 204)
    for x0, x1, y in ((25, 39, 15), (25, 39, 49), (29, 35, 22), (29, 35, 42)):
        w = round(3 * s)
        d.line([(x0 * s, y * s), (x1 * s, y * s)], fill=rung, width=w)
    return tile


def main() -> None:
    font = ImageFont.truetype(str(FONT), TEXT_SIZE * SCALE)
    try:
        font.set_variation_by_axes([800])     # ExtraBold, like the site
    except Exception:
        pass
    left, top, right, bottom = font.getbbox(NAME)
    tw, th = right - left, bottom - top
    H = LOGO * SCALE
    W = H + GAP * SCALE + tw + 4 * SCALE
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    img.alpha_composite(logo(H), (0, 0))

    # gradient-filled wordmark
    text_mask = Image.new("L", (tw + 4 * SCALE, H), 0)
    ImageDraw.Draw(text_mask).text((-left, (H - th) // 2 - top), NAME, font=font, fill=255)
    fill = gradient(text_mask.width, H).convert("RGBA")
    fill.putalpha(text_mask)
    img.alpha_composite(fill, (H + GAP * SCALE, 0))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, optimize=True)
    print(f"wrote {OUT.relative_to(ROOT)} ({W}x{H} px, shown at {W // SCALE}x{H // SCALE})")


if __name__ == "__main__":
    main()
