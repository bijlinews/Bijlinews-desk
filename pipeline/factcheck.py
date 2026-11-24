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
    extras = [str(article.get("why_it_matters") or "")]
    for key in ("key_numbers", "timeline", "faq"):
        for item in article.get(key) or []:
            if isinstance(item, dict):
                extras += [str(v) for v in item.values()]
    art = " ".join([article.get("title_hi", ""), " ".join(article.get("summary", [])), article.get("body_html", "")] + extras)
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


def _article_text(article):
    parts = [article.get("title_hi", ""), " ".join(article.get("summary", [])), article.get("body_html", ""),
             str(article.get("why_it_matters") or "")]
    for key in ("key_numbers", "timeline", "faq"):
        for item in article.get(key) or []:
            if isinstance(item, dict):
                parts += [str(v) for v in item.values()]
    return re.sub(r"<[^>]+>", " ", " ".join(parts))


def _source_text(sources, facts):
    return " ".join([" ".join([s.get("title", ""), s.get("snippet", ""), s.get("text", "")]) for s in sources] +
                    [f.get("quote", "") for f in facts])


# Latin words that are not names (units, common English words the writer may use in Hindi text)
_COMMON_LATIN = {"the", "and", "for", "with", "from", "ipo", "gdp", "ceo", "cfo", "pm", "cm", "mp", "mla", "ipl",
                 "odi", "t20", "t20i", "test", "news", "app", "online", "live", "km", "kg", "rs", "inr", "usd",
                 "ist", "gmt", "utc", "am", "pm", "bjp", "aap", "nda", "rbi", "sebi", "bse", "nse", "isro", "bcci", "icc"}
# abbreviations that are never "expanded" (times, units)
_NOT_EXPANSIONS = {"IST", "GMT", "UTC", "AM", "PM", "KM", "KG"}


def unsupported_names(article, sources, facts):
    """Names, abbreviations and other Latin-script words in the article that no source contains.
    Catches invented or wrongly spelled English names (e.g. a team or company the reports never mention)."""
    pool = norm(_source_text(sources, facts))
    missing = []
    for w in sorted(set(re.findall(r"[A-Za-z][A-Za-z0-9&.\-]{1,}", _article_text(article)))):
        key = w.strip(".-").lower()
        if len(key) < 3 or key in _COMMON_LATIN or key.isdigit():
            continue
        if key not in pool:
            missing.append(w.strip(".-"))
    return missing


def expanded_abbreviations(article, sources, facts):
    """Hindi words written just before '(ABC)' when no source spells ABC out.
    Example: '... ट्रांसजेंडर सेंटर (TRC) ग्राउंड' — the reports only said 'TRC', so the writer guessed
    what it stands for. Returns short strings like 'ट्रांसजेंडर सेंटर (TRC)' for the fact-check."""
    text = _article_text(article)
    src = _source_text(sources, facts)
    bad = []
    for m in re.finditer(r"\(\s*([A-Z][A-Z0-9]{1,7})\s*\)", text):
        abbr = m.group(1)
        if abbr in _NOT_EXPANSIONS:
            continue
        before = re.findall(r"[\u0900-\u097F]+", text[max(0, m.start() - 60):m.start()].split("।")[-1])
        if not before or not text[:m.start()].rstrip().endswith(before[-1]):
            continue                      # "(TRC)" not directly after Hindi words: nothing was expanded
        phrase = " ".join(before[-3:])
        spelled = re.search(r"[A-Za-z][A-Za-z .&'-]{3,80}\(\s*" + re.escape(abbr) + r"\s*\)", src) or \
            re.search(re.escape(abbr) + r"\s*\(\s*[A-Za-z][A-Za-z .&'-]{3,80}\)", src) or \
            re.search(r"[\u0900-\u097F][\u0900-\u097F ]{3,60}\(\s*" + re.escape(abbr) + r"\s*\)", src)
        if not spelled:
            bad.append(f"{phrase} ({abbr})")
    return sorted(set(bad))
