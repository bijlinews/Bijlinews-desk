"""Keyless research: DuckDuckGo news/web search (ddgs) + full article text (trafilatura).
No API keys. Any failure returns an empty list so the pipeline can fall back."""
import re

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def _domain(url):
    m = re.match(r"https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1) if m else ""


def news(query, timelimit="w", max_results=10):
    """Recent news results: [{title, url, source, snippet, published}]."""
    try:
        from ddgs import DDGS
        hits = DDGS().news(query, region="in-en", timelimit=timelimit, max_results=max_results) or []
    except Exception as e:  # noqa: BLE001
        print(f"  ! news search failed ({query[:50]}): {str(e)[:120]}")
        return []
    return [{"title": h.get("title", ""), "url": h.get("url", ""),
             "source": h.get("source") or _domain(h.get("url")), "snippet": h.get("body", ""),
             "published": h.get("date", "")} for h in hits if h.get("url")]


def web(query, max_results=4):
    """General web results for fact-checking: [{title, url, source, snippet}]."""
    try:
        from ddgs import DDGS
        hits = DDGS().text(query, region="in-en", max_results=max_results) or []
    except Exception as e:  # noqa: BLE001
        print(f"  ! web search failed ({query[:50]}): {str(e)[:120]}")
        return []
    return [{"title": h.get("title", ""), "url": h.get("href", ""), "source": _domain(h.get("href")),
             "snippet": h.get("body", "")} for h in hits if h.get("href")]


def article_text(url, max_chars=6000):
    """Main text of a news article, or '' if it can't be read."""
    if not url or "news.google.com" in url:
        return ""
    try:
        import trafilatura
        r = requests.get(url, headers=UA, timeout=15)
        r.raise_for_status()
        text = trafilatura.extract(r.text, include_comments=False, include_tables=False, favor_precision=True) or ""
        return re.sub(r"\n{2,}", "\n", text).strip()[:max_chars]
    except Exception as e:  # noqa: BLE001
        print(f"  ! could not read {url[:80]}: {str(e)[:100]}")
        return ""
