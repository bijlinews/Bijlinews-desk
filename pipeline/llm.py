"""Minimal Gemini REST client with JSON output and optional Google Search grounding.
If the configured model name no longer exists (Google retires models), it automatically picks
the newest stable Flash model available to this API key."""
import json
import re
import time

import requests

from . import config

BASE = "https://generativelanguage.googleapis.com/v1beta"
_resolved = {}


def _headers():
    return {"x-goog-api-key": config.GEMINI_API_KEY}


def _version_key(name):
    nums = [int(n) for n in re.findall(r"\d+", name)]
    return nums + [0] * (4 - len(nums))


def _best_flash():
    r = requests.get(f"{BASE}/models", headers=_headers(), params={"pageSize": 1000}, timeout=60)
    r.raise_for_status()
    names = [m["name"].split("/", 1)[1] for m in r.json().get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    bad = ("lite", "image", "tts", "audio", "live", "embedding", "thinking", "exp", "learnlm", "robotics", "computer")
    flash = [n for n in names if "flash" in n and not any(b in n for b in bad)]
    stable = [n for n in flash if "preview" not in n] or flash
    aliases = [n for n in stable if n.endswith("-latest")]
    pool = sorted(stable, key=_version_key, reverse=True)
    choice = pool[0] if pool else (aliases[0] if aliases else None)
    print(f"  (available flash models: {', '.join(sorted(flash))[:300]})")
    if not choice:
        raise RuntimeError("No usable Gemini Flash model found for this API key")
    return choice


def _model(name):
    return _resolved.get(name, name)


def _extract_json(text):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=0)
    return json.loads(text[start:])


def ask(prompt, model=None, web_search=False, temperature=0.4, retries=3):
    """Send a prompt, return parsed JSON. With web_search=True the model may run Google searches."""
    wanted = model or config.WRITER_MODEL
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature},
    }
    if web_search:
        body["tools"] = [{"google_search": {}}]
    else:
        body["generationConfig"]["responseMimeType"] = "application/json"

    last = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(f"{BASE}/models/{_model(wanted)}:generateContent", headers=_headers(),
                              json=body, timeout=180)
            if r.status_code == 404 and wanted not in _resolved:
                _resolved[wanted] = _best_flash()
                print(f"  ! model '{wanted}' not found; using '{_resolved[wanted]}' instead")
                continue
            if r.status_code in (429, 500, 503):
                last = f"HTTP {r.status_code}: {r.text[:200]}"
                time.sleep(20 * (attempt + 1))
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:400]}")
            data = r.json()
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
            result = _extract_json(text)
            if web_search and isinstance(result, dict):
                gm = data["candidates"][0].get("groundingMetadata", {})
                result["_search_sources"] = [
                    {"title": c.get("web", {}).get("title", ""), "url": c.get("web", {}).get("uri", "")}
                    for c in gm.get("groundingChunks", [])
                ]
            return result
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            last = f"bad response: {e}"
            time.sleep(5)
    raise RuntimeError(f"Gemini request failed: {last}")
