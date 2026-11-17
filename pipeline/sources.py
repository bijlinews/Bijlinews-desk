"""Fetch trends and news from free public feeds."""
import html
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; BijliNewsBot/1.0; +https://www.bijlinews.com/p/editorial-policy.html)"}
HT = "{https://trends.google.com/trending/rss}"


def _get(url, timeout=15):
    r = requests.get(url, headers=UA, timeout=timeout)
    r.raise_for_status()
    return r.text


def _traffic(s):
    m = re.search(r"([\d,]+)", s or "")
    return int(m.group(1).replace(",", "")) if m else 0


def fetch_trends(geo="IN"):
    """Google Trends 'trending now' RSS. Returns newest first."""
    root = ET.fromstring(_get(f"https://trends.google.com/trending/rss?geo={geo}"))
    out = []
    for it in root.iter("item"):
        news = []
        for n in it.findall(f"{HT}news_item"):
            news.append({
                "title": (n.findtext(f"{HT}news_item_title") or "").strip(),
                "url": (n.findtext(f"{HT}news_item_url") or "").strip(),
                "source": (n.findtext(f"{HT}news_item_source") or "").strip(),
            })
        out.append({
            "title": (it.findtext("title") or "").strip(),
            "traffic": _traffic(it.findtext(f"{HT}approx_traffic")),
            "published": it.findtext("pubDate") or "",
            "news": news,
        })
    return out


def google_news(query, lang="hi", limit=10):
    """Google News search RSS. lang='hi' for Hindi edition, 'en' for English (India)."""
    if lang == "hi":
        params = {"q": query, "hl": "hi", "gl": "IN", "ceid": "IN:hi"}
    else:
        params = {"q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"}
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)
    time.sleep(3)   # Google News rate-limits fast repeated requests from GitHub's servers (HTTP 429)
    try:
        root = ET.fromstring(_get(url))
    except Exception as e:  # noqa: BLE001
        print(f"  ! google news failed ({lang}): {e}")
        return []
    items = []
    for it in root.iter("item"):
        src = it.find("source")
        source = (src.text or "").strip() if src is not None else ""
        title = (it.findtext("title") or "").strip()
        if source and title.endswith(" - " + source):
            title = title[: -len(" - " + source)]
        items.append({
            "title": html.unescape(title),
            "source": source,
            "url": (it.findtext("link") or "").strip(),
            "published": it.findtext("pubDate") or "",
        })
        if len(items) >= limit:
            break
    return items


class _PText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self._in_p, self._skip = [], 0, 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "nav", "footer", "aside"):
            self._skip += 1
        if tag == "p":
            self._in_p += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "nav", "footer", "aside") and self._skip:
            self._skip -= 1
        if tag == "p" and self._in_p:
            self._in_p -= 1
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_p and not self._skip:
            self.parts.append(data)


def article_text(url, max_chars=3500):
    """Best-effort plain text of a news article (paragraphs only)."""
    if not url or "news.google.com" in url:
        return ""
    try:
        p = _PText()
        p.feed(_get(url, timeout=12))
        text = re.sub(r"[ \t]+", " ", "".join(p.parts))
        lines = [ln.strip() for ln in text.split("\n") if len(ln.strip()) > 60]
        return "\n".join(lines)[:max_chars]
    except Exception as e:  # noqa: BLE001
        print(f"  ! could not read {url[:80]}: {e}")
        return ""


def outlet_key(name):
    return re.sub(r"[^a-z0-9ऀ-ॿ]", "", (name or "").lower())
