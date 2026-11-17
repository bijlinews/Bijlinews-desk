"""Checks done by plain Python: no AI involved, so they can't be talked into a wrong answer."""
import re

DEV = str.maketrans("०१२३४५६७८९", "0123456789")


def norm(s):
    s = (s or "").translate(DEV).lower()
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[\"'“”‘’`]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def verify_quotes(facts, sources):
    """Keep only facts whose quote really appears in the source it cites."""
    texts = [norm(" ".join([s.get("title", ""), s.get("snippet", ""), s.get("text", "")])) for s in sources]
    alltext = " ".join(texts)
    good, bad = [], []
    for f in facts:
        q = norm(f.get("quote", ""))
        n = f.get("source")
        ok = len(q) >= 15 and (
            (isinstance(n, int) and 0 < n <= len(texts) and q in texts[n - 1]) or q in alltext)
        if not ok and len(q) >= 40:          # tolerate tiny differences: 2 halves of the quote both present
            half = len(q) // 2
            ok = q[:half - 2] in alltext and q[half + 2:] in alltext
        (good if ok else bad).append(f)
    return good, bad


def _numbers(text):
    t = norm(text).replace(",", "")
    nums = set(re.findall(r"\d+(?:\.\d+)?", t))
    return {n for n in nums if not (len(n) == 1)}   # single digits ("3 बातें") are too noisy


def unsupported_numbers(article, sources, facts):
    """Every number (2+ digits) in the headline, summary and body must appear in the sources."""
    art = " ".join([article.get("title_hi", ""), " ".join(article.get("summary", [])), article.get("body_html", "")])
    pool = " ".join([" ".join([s.get("title", ""), s.get("snippet", ""), s.get("text", "")]) for s in sources] +
                    [f.get("quote", "") for f in facts])   # quotes only: they are proven to be in a source
    have = _numbers(pool)
    missing = []
    for n in sorted(_numbers(art)):
        if n in have:
            continue
        if "." in n and n.rstrip("0").rstrip(".") in have:
            continue
        missing.append(n)
    return missing
