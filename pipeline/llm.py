"""AI client for GitHub Models (no key: uses the Action's own token), Groq, and optional OpenRouter/Mistral.
All are OpenAI-compatible.

ask(prompt, providers=["openrouter", "groq"]) tries each provider in order and returns
(json_result, provider_name). If a model name has been retired, it picks the best available
model from the provider's /models list automatically.
"""
import json
import re
import time

import requests

from . import config


class AIUnavailable(RuntimeError):
    """Every provider failed (outage, rate limit, missing key)."""


class TooLarge(AIUnavailable):
    """The prompt is bigger than the free plan allows; retry with fewer sources."""


PROVIDERS = {
    "github": {
        "base": "https://models.github.ai/inference",
        "catalog": "https://models.github.ai/catalog/models",
        "key": lambda: config.GITHUB_TOKEN,
        "model": lambda: config.GITHUB_MODEL,
        "prefer": ["openai/gpt-4.1", "openai/gpt-4o", "openai/gpt-4.1-mini", "openai/gpt-4o-mini"],
    },
    "groq": {
        "base": "https://api.groq.com/openai/v1",
        "key": lambda: config.GROQ_API_KEY,
        "model": lambda: config.GROQ_MODEL,
        # best first; used only if the configured model no longer exists
        "prefer": ["openai/gpt-oss-120b", "qwen/qwen3", "llama-3.3-70b", "llama-4", "gpt-oss-20b"],
    },
    "openrouter": {
        "base": "https://openrouter.ai/api/v1",
        "key": lambda: config.OPENROUTER_API_KEY,
        "model": lambda: config.OPENROUTER_MODEL,
        # free models only (ids ending in ":free"), best first
        "prefer": ["nemotron-3-ultra", "nemotron-3.5-super", "deepseek", "qwen3", "llama-3.3-70b", "gpt-oss-120b", "gemma", ""],
        "free_only": True,
    },
    "mistral": {
        "base": "https://api.mistral.ai/v1",
        "key": lambda: config.MISTRAL_API_KEY,
        "model": lambda: config.MISTRAL_MODEL,
        "prefer": ["mistral-medium-latest", "mistral-large-latest", "mistral-medium", "mistral-large", "mistral-small-latest"],
    },
}
_resolved = {}


def _headers(p):
    h = {"Authorization": f"Bearer {PROVIDERS[p]['key']()}", "Content-Type": "application/json"}
    if p == "github":
        h.update({"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    if p == "openrouter":
        h.update({"HTTP-Referer": "https://www.bijlinews.com", "X-Title": "Bijlinews Desk"})
    return h


def _pick_model(p):
    url = PROVIDERS[p].get("catalog") or f"{PROVIDERS[p]['base']}/models"
    r = requests.get(url, headers=_headers(p), timeout=60)
    r.raise_for_status()
    data = r.json()
    ids = [m.get("id", "") for m in (data if isinstance(data, list) else data.get("data", []))]
    if PROVIDERS[p].get("free_only"):
        ids = [i for i in ids if i.endswith(":free")]
    for want in PROVIDERS[p]["prefer"]:
        hits = sorted([i for i in ids if want in i and not any(b in i for b in ("guard", "whisper", "tts", "embed", "ocr", "moderation"))])
        if hits:
            return hits[-1]
    raise AIUnavailable(f"{p}: no suitable model among {ids[:15]}")


def _extract_json(text):
    text = (text or "").strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()   # some models emit reasoning tags
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1).strip()
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=0)
    end = max(text.rfind("}"), text.rfind("]"))
    return json.loads(text[start:end + 1] if end > start else text[start:])


def _call(p, prompt, temperature, max_tokens):
    model = _resolved.get(p) or PROVIDERS[p]["model"]()
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a careful news-desk assistant. Always answer with valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    if p == "openrouter":
        body.pop("response_format")   # many free OpenRouter models return an empty reply in JSON mode
    last = ""
    for attempt in range(3):
        try:
            r = requests.post(f"{PROVIDERS[p]['base']}/chat/completions", headers=_headers(p), json=body, timeout=180)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last = f"network: {e}"
            time.sleep(10)
            continue
        if r.status_code == 400 and "response_format" in r.text and "response_format" in body:
            body.pop("response_format")          # some free models don't support JSON mode; the prompt still asks for JSON
            continue
        if r.status_code == 404 or (r.status_code == 400 and "model" in r.text.lower() and p not in _resolved):
            _resolved[p] = _pick_model(p)
            body["model"] = _resolved[p]
            print(f"  ! {p}: model '{model}' unavailable, using '{_resolved[p]}'")
            continue
        if r.status_code in (429, 500, 502, 503, 529):
            last = f"HTTP {r.status_code}: {r.text[:160]}"
            wait = float(r.headers.get("retry-after", 0) or 0) or 15 * (attempt + 1)
            if wait > 120:          # daily limit reached: don't wait, let the backup AI take over
                raise AIUnavailable(f"{p}: rate limit, retry after {int(wait)}s")
            time.sleep(min(wait, 60))
            continue
        if r.status_code == 413 or "too large" in r.text.lower() or "tokens_limit_reached" in r.text:
            raise TooLarge(f"{p}: prompt too large for free limits")
        if r.status_code >= 400:
            raise AIUnavailable(f"{p}: HTTP {r.status_code}: {r.text[:300]}")
        try:
            msg = r.json()["choices"][0]["message"]
            # "thinking" models sometimes leave content empty and put the answer in a reasoning field
            text = msg.get("content") or msg.get("reasoning") or msg.get("reasoning_content") or ""
            if not text.strip():
                raise json.JSONDecodeError("empty reply", "", 0)
            return _extract_json(text)
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            last = f"bad JSON: {e}"
            body["temperature"] = 0.1
            continue
    raise AIUnavailable(f"{p}: {last}")


def ask(prompt, providers=("github", "groq"), temperature=0.4, max_tokens=4000):
    """Try providers in order. Returns (result_dict, provider_used)."""
    errors = []
    for p in providers:
        if not PROVIDERS[p]["key"]():
            errors.append(f"{p}: no API key")
            continue
        try:
            return _call(p, prompt, temperature, max_tokens), p
        except AIUnavailable as e:
            print(f"  ! {e}")
            errors.append(str(e))
    raise AIUnavailable(" | ".join(errors))
