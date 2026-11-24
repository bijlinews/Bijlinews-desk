"""Links the first mention of a glossary term in an article to its explainer page (शब्दकोश).

At most MAX_LINKS links per article, one per page, never inside an existing link or a heading.
Add new explainer pages to explainers.json as they are published."""
import json
import os
import re

MAX_LINKS = 3
SITE = "https://www.bijlinews.com"
_PATH = os.path.join(os.path.dirname(__file__), "explainers.json")
_DEV = "ऀ-ॿ"   # Devanagari block (letters and vowel signs)


def _load():
    try:
        with open(_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


def _pattern(term):
    # whole words only: no letter/vowel sign glued on either side (so "IPO" won't match inside "IPOs")
    return re.compile(rf"(?<![A-Za-z0-9{_DEV}])({re.escape(term)})(?![A-Za-z0-9{_DEV}])")


def link_terms(body_html, pages=None):
    pages = _load() if pages is None else pages
    terms = sorted(((t, url) for url, ts in pages.items() for t in ts), key=lambda x: -len(x[0]))
    parts = re.split(r"(<[^>]+>)", body_html or "")
    used, skip_depth, n = set(), 0, 0
    for i, part in enumerate(parts):
        if part.startswith("<"):
            tag = re.match(r"</?\s*([a-zA-Z0-9]+)", part)
            name = tag.group(1).lower() if tag else ""
            if name in ("a", "h1", "h2", "h3", "h4", "strong"):
                skip_depth += -1 if part.startswith("</") else 1
                skip_depth = max(skip_depth, 0)
            continue
        if skip_depth or n >= MAX_LINKS or not part.strip():
            continue
        for term, url in terms:
            if url in used or n >= MAX_LINKS:
                continue
            m = _pattern(term).search(part)
            if not m:
                continue
            href = url if url.startswith("http") else SITE + url
            part = part[:m.start()] + f'<a href="{href}">{m.group(1)}</a>' + part[m.end():]
            used.add(url)
            n += 1
            break   # one link per text piece keeps the HTML simple; later pieces can take the next term
        parts[i] = part
    return "".join(parts)
