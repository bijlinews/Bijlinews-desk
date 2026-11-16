"""Minimal Gemini REST client with JSON output and optional Google Search grounding."""
import json
import re
import time

import requests

from . import config

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _extract_json(text):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=0)
    return json.loads(text[start:])


def ask(prompt, model=None, web_search=False, temperature=0.4, retries=3):
    """Send a prompt, return parsed JSON. With web_search=True the model may run Google searches."""
    model = model or config.WRITER_MODEL
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    if web_search:
        body["tools"] = [{"google_search": {}}]
    else:
        body["generationConfig"]["responseMimeType"] = "application/json"

    last = None
    for attempt in range(retries):
        try:
            r = requests.post(API.format(model=model), params={"key": config.GEMINI_API_KEY},
                              json=body, timeout=180)
            if r.status_code in (429, 500, 503):
                last = f"HTTP {r.status_code}: {r.text[:200]}"
                time.sleep(20 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
            result = _extract_json(text)
            if web_search:
                gm = data["candidates"][0].get("groundingMetadata", {})
                result_sources = [
                    {"title": c.get("web", {}).get("title", ""), "url": c.get("web", {}).get("uri", "")}
                    for c in gm.get("groundingChunks", [])
                ]
                if isinstance(result, dict):
                    result["_search_sources"] = result_sources
            return result
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            last = f"bad response: {e}"
            time.sleep(5)
    raise RuntimeError(f"Gemini request failed: {last}")
