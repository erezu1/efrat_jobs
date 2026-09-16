"""Draw the link-preview image (WhatsApp, iMessage, Telegram, Slack…): logo and wordmark as on the site.

Previews need a real image at an absolute URL (og:image); the page's own icon is an inline SVG that
link previewers can't use. 1200x630 is the size they all show as a large card.
Re-run after changing the logo or name:  .venv/bin/python tools/make_share_image.py  (needs Pillow)
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from make_email_header import FONT, NAME, gradient, logo

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "icons" / "share.png"
W, H = 1200, 630
BG, MUTED = (0xF7, 0xF3, 0xF8), (0x6E, 0x62, 0x74)
LOGO, GAP, TEXT = 190, 44, 150
SUB = "Biology jobs in the Netherlands, updated daily"


def sora(size: int, weight: int) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT), size)
    try:
        f.set_variation_by_axes([weight])
    except Exception:
        pass
    return f


def main() -> None:
    img = Image.new("RGBA", (W, H), BG + (255,))
    word, sub = sora(TEXT, 800), sora(40, 600)
    l, t, r, b = word.getbbox(NAME)
    tw, th = r - l, b - t
    group = LOGO + GAP + tw
    x0, y0 = (W - group) // 2, 170

    # soft shadow under the logo tile, like the site's elevation
    shadow = Image.new("RGBA", (LOGO + 80, LOGO + 80), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([40, 52, 40 + LOGO, 52 + LOGO], radius=44, fill=(90, 30, 110, 60))
    from PIL import ImageFilter
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18)), (x0 - 40, y0 - 40))
    img.alpha_composite(logo(LOGO), (x0, y0))

    mask = Image.new("L", (tw + 8, LOGO), 0)
    ImageDraw.Draw(mask).text((-l, (LOGO - th) // 2 - t), NAME, font=word, fill=255)
    fill = gradient(mask.width, LOGO).convert("RGBA")
    fill.putalpha(mask)
    img.alpha_composite(fill, (x0 + LOGO + GAP, y0))

    sl, st, sr, sb = sub.getbbox(SUB)
    ImageDraw.Draw(img).text(((W - (sr - sl)) // 2 - sl, y0 + LOGO + 70 - st), SUB, font=sub, fill=MUTED)

    img.convert("RGB").save(OUT, optimize=True)
    print(f"wrote {OUT.relative_to(ROOT)} ({W}x{H})")


if __name__ == "__main__":
    main()
