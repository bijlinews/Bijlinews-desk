"""Branded images made by the bot (no third-party photos inside, so no licence issues):
- share card 1200x675: the post's thumbnail and its WhatsApp/Facebook/X preview
- logo 512x512: used by Web Stories
"""
import datetime as dt
import os

from PIL import Image, ImageDraw, ImageFont, features

from . import config

W, H = 1200, 675
RED, RED_D, GOLD, WHITE = (225, 0, 26), (150, 0, 16), (255, 193, 7), (255, 255, 255)
BOLT = [(13, 2), (4, 14), (10, 14), (9, 22), (18, 10), (12, 10), (13, 2)]
# accent colour per section, so thumbnails don't all look the same
ACCENT = {
    "भारत": (225, 0, 26), "दुनिया": (21, 101, 192), "बिजनेस": (0, 121, 107), "शेयर बाजार": (46, 125, 50),
    "टेक्नोलॉजी": (94, 53, 177), "खेल": (230, 81, 0), "मनोरंजन": (194, 24, 91), "हेल्थ": (0, 131, 143),
}
MONTHS = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]


def _font(bold, size):
    path = config.FONT_BOLD if bold else config.FONT_REGULAR
    try:
        return ImageFont.truetype(path, size)
    except OSError:  # local tests without Mukta
        alt = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-%s.ttf" % ("Bold" if bold else "Regular")
        return ImageFont.truetype(alt, size)


def _latin(size):
    """Font for English text (Mukta has Latin letters; the fallback is for machines without Mukta)."""
    for path in (config.FONT_BOLD, "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            f = ImageFont.truetype(path, size)
            if "Devanagari" not in (f.getname()[0] or ""):
                return f
        except OSError:
            continue
    return ImageFont.load_default()


def _wrap(draw, text, font, width):
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _bolt(d, cx, cy, r, fill):
    s = r / 12.0
    d.polygon([(cx + (px - 11) * s, cy + (py - 12) * s) for px, py in BOLT], fill=fill)


def _mark(d, x, y, size):
    d.ellipse((x, y, x + size, y + size), fill=RED)
    _bolt(d, x + size / 2, y + size / 2, size * 0.36, GOLD)


def share_card(title, section, out_path, key_number=None, when=None):
    """Branded 1200x675 card. key_number: optional {"value", "label"} shown in a gold box."""
    if not features.check("raqm"):
        print("  ! Pillow has no raqm: Hindi letters may render incorrectly")
    when = when or dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30)))
    acc = ACCENT.get(section, RED)
    dark = tuple(max(0, int(c * 0.22)) for c in acc)

    # background: dark diagonal gradient tinted with the section colour
    img = Image.new("RGB", (W, H), dark)
    px = img.load()
    for yy in range(0, H, 3):
        for xx in range(0, W, 3):
            t = min(1.0, (xx / W) * 0.55 + (yy / H) * 0.45)
            col = tuple(int(dark[i] * (1 - t) + 10 * t) for i in range(3))
            for a in range(3):
                for b in range(3):
                    if xx + a < W and yy + b < H:
                        px[xx + a, yy + b] = col
    d = ImageDraw.Draw(img)
    d.ellipse((W - 520, -300, W + 260, 420), fill=tuple(min(255, int(c * 0.5)) for c in acc))
    img = Image.blend(img, Image.new("RGB", (W, H), dark), 0.35)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 14, H), fill=acc)                      # left accent bar

    # brand
    _mark(d, 56, 44, 66)
    d.text((138, 44), "बिजली न्यूज़", font=_font(True, 40), fill=WHITE)
    d.text((140, 92), "खबर भी, वजह भी", font=_font(False, 24), fill=(220, 220, 220))
    chip = section or "ट्रेंडिंग"
    cf = _font(True, 26)
    cw = d.textlength(chip, font=cf) + 34
    d.rounded_rectangle((W - 60 - cw, 54, W - 60, 102), radius=8, fill=GOLD)
    d.text((W - 60 - cw + 17, 58), chip, font=cf, fill=(20, 16, 0))

    # headline (shrinks to fit 4 lines)
    box_w = W - 112 - (330 if key_number else 0)
    size = 78
    while True:
        f = _font(True, size)
        lines = _wrap(d, title, f, box_w)
        if (len(lines) <= 4 and (len(lines) <= 3 or size <= 66)) or size <= 40:
            break
        size -= 4
    lines = lines[:4]
    lh = int(size * 1.34)
    y = 170 + max(0, (4 - len(lines)) * lh // 2) - 10
    for ln in lines:
        d.text((58, y), ln, font=f, fill=WHITE)
        y += lh

    # optional key number
    if key_number and key_number.get("value"):
        bx, by = W - 370, 240
        d.rounded_rectangle((bx, by, W - 60, by + 230), radius=18, fill=(255, 255, 255))
        d.rectangle((bx, by, bx + 10, by + 230), fill=acc)
        val = str(key_number["value"])[:14]
        vs = 60
        while d.textlength(val, font=_font(True, vs)) > 270 and vs > 30:
            vs -= 4
        d.text((bx + 34, by + 40), val, font=_font(True, vs), fill=acc)
        lab = _wrap(d, str(key_number.get("label", ""))[:40], _font(False, 26), 260)[:2]
        yy = by + 50 + vs + 10
        for ln in lab:
            d.text((bx + 34, yy), ln, font=_font(False, 26), fill=(40, 40, 40))
            yy += 34

    # footer
    d.rectangle((0, H - 74, W, H), fill=(0, 0, 0))
    d.rectangle((0, H - 74, W, H - 70), fill=acc)
    stamp = f"{when.day} {MONTHS[when.month - 1]} {when.year}"
    d.text((58, H - 58), stamp, font=_font(False, 28), fill=(230, 230, 230))
    site = "bijlinews.com"
    sf = _latin(30)
    d.text((W - 60 - d.textlength(site, font=sf), H - 60), site, font=sf, fill=GOLD)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path, "JPEG", quality=88, optimize=True, progressive=True)
    return out_path


def logo(out_path, size=512):
    img = Image.new("RGB", (size, size), WHITE)
    d = ImageDraw.Draw(img)
    _mark(d, 0, 0, size)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path
