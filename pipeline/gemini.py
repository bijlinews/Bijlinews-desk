"""Gemini with 'Grounding with Google Search': the model runs real Google searches itself.
Used as the first-choice fact-checker. Any failure raises GeminiUnavailable so the pipeline
falls back to Tavily search + Groq."""
import json
import re
import time

import requests

from . import config

BASE = "https://generativelanguage.googleapis.com/v1beta"
_model = {}


class GeminiUnavailable(RuntimeError):
    pass


def enabled():
    return bool(config.GEMINI_API_KEY)


def _headers():
    return {"x-goog-api-key": config.GEMINI_API_KEY}


def _pick_model():
    r = requests.get(f"{BASE}/models", headers=_headers(), params={"pageSize": 1000}, timeout=60)
    r.raise_for_status()
    names = [m["name"].split("/", 1)[1] for m in r.json().get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    for pref in ("gemini-flash-latest", "gemini-pro-latest"):
        if pref in names:
            return pref
    bad = ("lite", "image", "tts", "audio", "live", "embedding", "exp", "preview")
    flash = sorted([n for n in names if "flash" in n and not any(b in n for b in bad)],
                   key=lambda n: [int(x) for x in re.findall(r"\d+", n)], reverse=True)
    if not flash:
        raise GeminiUnavailable("no usable Gemini model for this key")
    return flash[0]


def _json(text):
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise json.JSONDecodeError("no JSON object", text, 0)
    return json.loads(text[start:end + 1])


def grounded(prompt, temperature=0.1):
    """Ask Gemini with Google Search enabled. Returns (json_result, list_of_source_urls)."""
    if not enabled():
        raise GeminiUnavailable("no GEMINI_API_KEY")
    model = _model.get("m") or config.GEMINI_MODEL
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"temperature": temperature}}
    last = ""
    for attempt in range(4):
        try:
            r = requests.post(f"{BASE}/models/{model}:generateContent", headers=_headers(), json=body, timeout=150)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last = f"network: {e}"
            continue
        if r.status_code == 404 and "m" not in _model:
            _model["m"] = model = _pick_model()
            print(f"  ! Gemini model '{config.GEMINI_MODEL}' not found, using '{model}'")
            continue
        if r.status_code in (429, 500, 503):
            last = f"HTTP {r.status_code}: {r.text[:150]}"
            time.sleep(10 * (attempt + 1))
            continue
        if r.status_code >= 400:
            raise GeminiUnavailable(f"HTTP {r.status_code}: {r.text[:300]}")
        try:
            data = r.json()
            cand = data["candidates"][0]
            text = "".join(p.get("text", "") for p in cand["content"]["parts"])
            result = _json(text)
            urls = [c.get("web", {}).get("title") or c.get("web", {}).get("uri", "")
                    for c in cand.get("groundingMetadata", {}).get("groundingChunks", [])]
            searches = cand.get("groundingMetadata", {}).get("webSearchQueries", [])
            return result, urls, searches, model
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            last = f"bad response: {e}"
            continue
    raise GeminiUnavailable(last)
