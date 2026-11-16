"""Branded 1200x675 cover card with the Hindi headline (no third-party photos = no copyright risk)."""
import datetime as dt
import os

from PIL import Image, ImageDraw, ImageFont, features

from . import config

W, H = 1200, 675
INK, PAPER, VOLT, MUTED = (14, 13, 17), (246, 242, 233), (255, 208, 0), (150, 145, 135)
BOLT = [(13, 2), (4, 14), (10, 14), (9, 22), (18, 10), (12, 10), (13, 2)]


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


def make_card(text, section, out_path, when=None):
    if not features.check("raqm"):
        print("  ! Pillow has no raqm: Hindi letters may render incorrectly")
    when = when or dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30)))
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    # yellow glow circle + accent bar
    glow = Image.new("RGB", (W, H), INK)
    gd = ImageDraw.Draw(glow)
    for r, a in ((420, 18), (300, 30), (180, 45)):
        gd.ellipse((W - r, -r // 2, W + r, r * 1.5), fill=(min(255, 14 + a * 3), min(255, 13 + a * 2), 17))
    img = Image.blend(img, glow, 0.6)
    d = ImageDraw.Draw(img)
    d.rectangle((0, H - 14, W, H), fill=VOLT)

    bold_big = ImageFont.truetype(config.FONT_BOLD, 72)
    bold_mid = ImageFont.truetype(config.FONT_BOLD, 34)
    reg = ImageFont.truetype(config.FONT_REGULAR, 28)

    # logo: bolt in yellow rounded square + name
    d.rounded_rectangle((64, 56, 128, 120), radius=16, fill=VOLT)
    d.polygon([(64 + x * 2.6 + 1, 56 + y * 2.6 + 1) for x, y in BOLT], fill=INK)
    d.text((146, 60), "बिजली न्यूज़", font=bold_mid, fill=PAPER)
    d.text((146, 100), "खबर भी, वजह भी", font=reg, fill=MUTED)

    # section chip
    chip = section or "ट्रेंडिंग"
    cw = d.textlength(chip, font=reg) + 36
    d.rounded_rectangle((64, 190, 64 + cw, 238), radius=10, fill=VOLT)
    d.text((82, 192), chip, font=reg, fill=INK)

    # headline (shrink until it fits in 4 lines)
    size = 72
    while True:
        font = ImageFont.truetype(config.FONT_BOLD, size)
        lines = _wrap(d, text, font, W - 140)
        if len(lines) <= 4 or size <= 44:
            break
        size -= 4
    y = 268
    for ln in lines[:4]:
        d.text((64, y), ln, font=font, fill=PAPER)
        y += int(size * 1.32)

    months = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]
    stamp = f"{when.day} {months[when.month - 1]} {when.year}  ·  bijlinews.com"
    d.text((64, H - 70), stamp, font=reg, fill=MUTED)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path
