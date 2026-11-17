"""Cover image.
1) Unsplash photo (free; Unsplash's rules: show it from Unsplash's own URL, ping the download link,
   credit the photographer). Generic photos only (objects, places), shown as a symbolic image.
2) If Unsplash has no key or no match: a branded headline card made here and committed to the repo."""
import datetime as dt
import os

import requests
from PIL import Image, ImageDraw, ImageFont, features

from . import config

W, H = 1200, 675
INK, PAPER, VOLT, MUTED = (14, 13, 17), (246, 242, 233), (255, 208, 0), (150, 145, 135)
BOLT = [(13, 2), (4, 14), (10, 14), (9, 22), (18, 10), (12, 10), (13, 2)]
UTM = "utm_source=bijlinews&utm_medium=referral"


def unsplash_photo(query, used=()):
    """Returns {url, credit_name, credit_url, unsplash_url, id} or None."""
    if not (query and config.UNSPLASH_ACCESS_KEY):
        return None
    h = {"Authorization": f"Client-ID {config.UNSPLASH_ACCESS_KEY}", "Accept-Version": "v1"}
    try:
        r = requests.get("https://api.unsplash.com/search/photos", headers=h, timeout=20,
                         params={"query": query, "orientation": "landscape", "per_page": 10, "content_filter": "high"})
        if r.status_code >= 400:
            print(f"  ! Unsplash search failed: HTTP {r.status_code} {r.text[:120]}")
            return None
        photos = [p for p in r.json().get("results", []) if p.get("id") not in used]
        if not photos:
            print(f"  ! Unsplash: no photo for '{query}'")
            return None
        p = photos[0]
        # Unsplash requires this "download" ping whenever a photo is used
        requests.get(p["links"]["download_location"], headers=h, timeout=20)
        return {"id": p["id"],
                "url": p["urls"]["raw"] + "&w=1200&h=675&fit=crop&crop=entropy&q=80&fm=jpg",
                "credit_name": p["user"]["name"],
                "credit_url": f"{p['user']['links']['html']}?{UTM}",
                "unsplash_url": f"https://unsplash.com/?{UTM}"}
    except Exception as e:  # noqa: BLE001  — an image problem must never stop an article
        print(f"  ! Unsplash failed: {e}")
        return None


def _cover(img):
    """Scale and centre-crop to exactly 1200x675."""
    scale = max(W / img.width, H / img.height)
    img = img.resize((int(img.width * scale + 0.5), int(img.height * scale + 0.5)), Image.LANCZOS)
    left, top = (img.width - W) // 2, (img.height - H) // 2
    return img.crop((left, top, left + W, top + H))


def _wrap(draw, text, font, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _logo(d, x, y, bold_mid, reg, on_photo):
    d.rounded_rectangle((x, y, x + 64, y + 64), radius=16, fill=VOLT)
    d.polygon([(x + px * 2.6 + 1, y + py * 2.6 + 1) for px, py in BOLT], fill=INK)
    d.text((x + 82, y + 4), "बिजली न्यूज़", font=bold_mid, fill=PAPER)
    if not on_photo:
        d.text((x + 82, y + 44), "खबर भी, वजह भी", font=reg, fill=MUTED)


def make_card(text, section, out_path, when=None, bg=None):  # bg kept for compatibility (unused)
    bg = None
    if not features.check("raqm"):
        print("  ! Pillow has no raqm: Hindi letters may render incorrectly")
    when = when or dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30)))
    bold_mid = ImageFont.truetype(config.FONT_BOLD, 34)
    reg = ImageFont.truetype(config.FONT_REGULAR, 28)
    chip = section or "ट्रेंडिंग"

    if bg is not None:
        img = _cover(bg)
        # dark fade: light at top, strong at the bottom where the headline sits
        shade = Image.new("L", (1, H))
        for y in range(H):
            shade.putpixel((0, y), int(40 + 190 * max(0, (y - H * 0.25) / (H * 0.75)) ** 1.3))
        shade = shade.resize((W, H))
        img = Image.composite(Image.new("RGB", (W, H), (8, 7, 10)), img, shade)
        d = ImageDraw.Draw(img)
        _logo(d, 48, 40, bold_mid, reg, on_photo=True)
        size, max_lines, bottom = 64, 3, H - 70
    else:
        img = Image.new("RGB", (W, H), INK)
        glow = Image.new("RGB", (W, H), INK)
        gd = ImageDraw.Draw(glow)
        for r, a in ((420, 18), (300, 30), (180, 45)):
            gd.ellipse((W - r, -r // 2, W + r, r * 1.5), fill=(min(255, 14 + a * 3), min(255, 13 + a * 2), 17))
        img = Image.blend(img, glow, 0.6)
        d = ImageDraw.Draw(img)
        _logo(d, 64, 56, bold_mid, reg, on_photo=False)
        size, max_lines, bottom = 72, 4, None

    # headline: shrink until it fits
    while True:
        font = ImageFont.truetype(config.FONT_BOLD, size)
        lines = _wrap(d, text, font, W - 130)
        if len(lines) <= max_lines or size <= 42:
            break
        size -= 4
    lines = lines[:max_lines]
    line_h = int(size * 1.32)
    y = (bottom - line_h * len(lines) - 70) if bottom else 268
    cw = d.textlength(chip, font=reg) + 36
    d.rounded_rectangle((64, y, 64 + cw, y + 48), radius=10, fill=VOLT)
    d.text((82, y + 2), chip, font=reg, fill=INK)
    y += 66
    for ln in lines:
        d.text((64, y), ln, font=font, fill=PAPER)
        y += line_h

    months = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]
    stamp = f"{when.day} {months[when.month - 1]} {when.year}  ·  bijlinews.com"
    if bg is not None:
        stamp += "  ·  AI चित्र"
    d.text((64, H - 56), stamp, font=reg, fill=(200, 196, 188) if bg is not None else MUTED)
    d.rectangle((0, H - 10, W, H), fill=VOLT)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, "JPEG", quality=86, optimize=True, progressive=True)
    return out_path
