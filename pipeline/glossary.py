"""Fix known recurring spelling/translation mistakes (pipeline/glossary.json) in an article."""
import json
import os

_PATH = os.path.join(os.path.dirname(__file__), "glossary.json")
TEXT_KEYS = ("title_hi", "body_html", "search_description", "image_alt", "why_it_matters")


def load():
    try:
        with open(_PATH, encoding="utf-8") as f:
            return {k: v for k, v in json.load(f).get("fixes", {}).items() if k and isinstance(v, str)}
    except (OSError, ValueError):
        return {}


def _fix(s, fixes):
    if not isinstance(s, str):
        return s
    for wrong in sorted(fixes, key=len, reverse=True):   # longest first, so "X (TRC)" wins over "X"
        s = s.replace(wrong, fixes[wrong])
    return s


def apply(article, fixes=None):
    fixes = load() if fixes is None else fixes
    if not fixes:
        return article
    for k in TEXT_KEYS:
        if k in article:
            article[k] = _fix(article[k], fixes)
    article["summary"] = [_fix(s, fixes) for s in (article.get("summary") or [])]
    for key, fields in (("key_numbers", ("value", "label")), ("timeline", ("when", "what")), ("faq", ("q", "a"))):
        for item in article.get(key) or []:
            if isinstance(item, dict):
                for f in fields:
                    item[f] = _fix(item.get(f), fixes)
    return article
