"""Web search via Tavily (free plan: 4,000 searches a month). Used for research and fact-checking."""
import time
import urllib.parse

import requests

from . import config


class SearchUnavailable(RuntimeError):
    pass


def enabled():
    return bool(config.TAVILY_API_KEY)


def _domain(url):
    host = urllib.parse.urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def tavily(query, topic="news", days=None, max_results=5, raw=False):
    """Returns a list of {title, url, source, text, published}."""
    if not enabled():
        raise SearchUnavailable("no TAVILY_API_KEY")
    body = {"query": query[:380], "topic": topic, "search_depth": "basic",
            "max_results": max_results, "include_raw_content": bool(raw)}
    if days and topic == "news":
        body["days"] = days
    for attempt in range(3):
        try:
            r = requests.post("https://api.tavily.com/search", json=body, timeout=45,
                              headers={"Authorization": f"Bearer {config.TAVILY_API_KEY}"})
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last = str(e)
            time.sleep(5)
            continue
        if r.status_code in (429, 500, 502, 503):
            last = f"HTTP {r.status_code}"
            time.sleep(10 * (attempt + 1))
            continue
        if r.status_code >= 400:   # 401 bad key, 432/433 monthly limit reached, etc.
            raise SearchUnavailable(f"Tavily HTTP {r.status_code}: {r.text[:200]}")
        out = []
        for x in r.json().get("results", []):
            text = (x.get("raw_content") or "") if raw else ""
            out.append({
                "title": x.get("title", ""),
                "url": x.get("url", ""),
                "source": _domain(x.get("url", "")),
                "text": (text or x.get("content") or "")[:3500],
                "published": x.get("published_date", ""),
            })
        return out
    raise SearchUnavailable(f"Tavily failed: {last}")
