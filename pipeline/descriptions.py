"""List of Blogger 'Search description' texts, for a Chrome extension that types them into the Blogger editor.

Blogger's API cannot set a post's Search description, so the bot keeps the ready-made text in
state/descriptions.json (same format as the ICC BizNews list). Until a post gets one, the theme uses the
post's opening line as its description."""
import datetime as dt
import json
import os
import re

PATH = os.path.join("state", "descriptions.json")
KEEP = 400
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def load():
    try:
        with open(PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return []


def save(items):
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(items[:KEEP], f, ensure_ascii=False, indent=1)


def clean(text, limit=150):   # Blogger's Search description box takes at most 150 characters
    text = re.sub(r"<[^>]+>", " ", str(text or ""))
    text = re.sub(r"\s+", " ", text).strip().strip('"').strip()
    if len(text) > limit:   # cut at the last word that fits, never mid-word
        cut = text[:limit - 1]
        text = (cut.rsplit(" ", 1)[0] if " " in cut else cut).rstrip(",;:-–") + "…"
    return text


def add(items, post_id, title, url, edit_url, description):
    """Put one post at the top of the list (replacing an older entry for it). Returns the list."""
    desc = clean(description)
    if not post_id or len(desc) < 40:
        return items
    items = [i for i in items if str(i.get("post_id")) != str(post_id)]
    items.insert(0, {"post_id": str(post_id), "title": title, "url": url, "edit_url": edit_url,
                     "description": desc, "added": dt.datetime.now(IST).strftime("%Y-%m-%dT%H:%M+05:30")})
    return items
