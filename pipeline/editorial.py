"""The three AI steps: pick trends, write the article, fact-check it."""
import json

from . import config, llm

SECTIONS = ", ".join(config.SECTIONS)

# Topics that must never auto-publish. The pipeline saves these as drafts for a human.
SENSITIVE_RULES = """
Mark "sensitive": true if the story involves ANY of these:
- death, suicide, self-harm, murder, accident or disaster with victims
- a crime, arrest, FIR, court case, or any allegation/accusation against a named person or company
- communal, caste or religious tension; riots; hate speech
- elections, vote counts, or claims made by/against politicians or parties
- health, medicine, diet or disease advice
- investment tips (buy/sell/target price), crypto, betting or gambling
- minors, sexual content, or victims of violence
- anything where getting a fact wrong could harm a real person's reputation
"""


def triage(trends):
    """Decide which trends are worth an article for Hindi-speaking Indian readers."""
    lines = []
    for i, t in enumerate(trends):
        heads = " | ".join(f"{n['title']} ({n['source']})" for n in t["news"][:3])
        lines.append(f"{i}. \"{t['title']}\" — searches: {t['traffic']}+ — news: {heads}")
    prompt = f"""You are the news editor of बिजली न्यूज़ (bijlinews.com), a Hindi news website for readers in India.
Below are topics trending on Google in India right now, with the headlines that explain them.

{chr(10).join(lines)}

For EACH topic decide:
- "relevant": true only if a Hindi-speaking reader in India would care, and there is a real news event
  behind it (not a generic word, not a foreign topic with no Indian angle, not live-score pages,
  not betting, not a plain product/brand name with no news).
- "section": exactly one of [{SECTIONS}] or null.
- "sensitive": see rules.
{SENSITIVE_RULES}
- "priority": 1-10 (10 = most useful and timely for our readers).
- "query": the best short Google News search query (English) to research it.

Return JSON: {{"topics": [{{"index": 0, "relevant": true, "section": "...", "sensitive": false,
"reason": "one line", "priority": 7, "query": "..."}}]}}"""
    data, _ = llm.ask(prompt, providers=_order(), temperature=0.2, max_tokens=3000)
    return data.get("topics", [])


def _order():
    """Writer first, the other AI as backup."""
    return (config.WRITER, "groq" if config.WRITER == "mistral" else "mistral")


def _sources_block(sources, budget=16000):
    """Numbered sources, trimmed to a character budget (Groq's free tier allows smaller prompts)."""
    out, used = [], 0
    per = max(300, budget // max(1, len(sources)))
    for i, s in enumerate(sources, 1):
        body = (s.get("text") or "")[:per]
        block = f"[{i}] {s['source']} — {s['title']}\nURL: {s['url']}\n{body}"
        if used + len(block) > budget:
            block = f"[{i}] {s['source']} — {s['title']}"
        out.append(block)
        used += len(block)
    return "\n\n".join(out)


def write(topic, section, sources):
    prompt = f"""You write for बिजली न्यूज़, a Hindi news site whose promise is "खबर भी, वजह भी" —
the news AND why it matters. Write an original Hindi news explainer about: "{topic}".

Use ONLY facts found in the sources below. Never invent names, numbers, dates, quotes or causes.
If sources disagree, say so or leave the point out. If a detail is not in the sources, do not write it.
Write in simple, natural Hindi (Devanagari) that a 10th-class student understands. English terms
that Indians commonly use (IPO, RBI, T20) are fine. No clickbait, no exaggeration, no opinions.

SOURCES:
{_sources_block(sources)}

Return JSON with these keys:
- "title_hi": Hindi headline, max 90 characters, factual, no ALL CAPS, no "!!".
- "slug_en": short English URL slug, lowercase words joined by hyphens, max 6 words, no dates.
- "summary": exactly 3 short Hindi bullet strings: (1) क्या हुआ, (2) अभी चर्चा क्यों, (3) आप पर/देश पर असर.
- "body_html": the article, 350–700 Hindi words, as HTML using only <p>, <h2>, <ul>, <li>, <strong>.
   Structure: an opening paragraph (who, what, when, where), then <h2>पूरा मामला क्या है</h2>,
   <h2>यह अभी क्यों चर्चा में है</h2>, <h2>आगे क्या</h2>. Do not repeat the summary bullets word for word.
- "search_description": Hindi, 140–160 characters, unique, describes the article.
- "image_text": a Hindi line of max 60 characters for the cover image (can be the headline shortened).
- "image_alt": Hindi alt text describing the cover image (a news card with the headline).
- "claims": list of every checkable factual claim in the article (names, numbers, dates, events), in Hindi.
- "sources_used": list of source numbers you relied on, e.g. [1, 3]."""
    article, by = llm.ask(prompt, providers=_order(), temperature=0.5, max_tokens=6000)
    article["_writer"] = by
    return article


def fact_check(article, sources):
    """Both AIs check the article independently. PASS only if both say PASS."""
    results = {}
    for p, budget in (("mistral", 16000), ("groq", 6000)):
        try:
            results[p], _ = llm.ask(_check_prompt(article, sources, budget), providers=(p,),
                                    temperature=0.1, max_tokens=3500)
        except llm.AIUnavailable as e:
            results[p] = {"verdict": "UNAVAILABLE", "notes": str(e)[:200], "claims": [], "corrections": []}
    return _combine(results)


def _combine(results):
    verdicts = [r.get("verdict", "FAIL") for r in results.values()]
    if all(v == "PASS" for v in verdicts):
        verdict = "PASS"
    elif any(v in ("FAIL", "UNAVAILABLE") for v in verdicts):
        verdict = "FAIL" if "FAIL" in verdicts else "UNAVAILABLE"
    else:
        verdict = "FIX"
    claims, corrections = [], []
    for p, r in results.items():
        for c in r.get("claims", []) or []:
            claims.append({**c, "evidence": f"[{p}] {c.get('evidence', '')}"})
        corrections += r.get("corrections", []) or []
    return {
        "verdict": verdict,
        "sensitive": any(r.get("sensitive") for r in results.values()),
        "claims": claims,
        "corrections": corrections,
        "notes": " | ".join(f"{p}: {r.get('verdict')} — {r.get('notes', '')}" for p, r in results.items()),
        "by_checker": {p: r.get("verdict") for p, r in results.items()},
    }


def _check_prompt(article, sources, budget):
    prompt = f"""You are a strict fact-checker for a Hindi news website. A different writer produced the
article below. Your job is to find mistakes BEFORE it is published. Be sceptical.

ARTICLE TITLE: {article['title_hi']}
ARTICLE SUMMARY: {json.dumps(article['summary'], ensure_ascii=False)}
ARTICLE BODY (HTML): {article['body_html']}
CLAIMS LISTED BY WRITER: {json.dumps(article.get('claims', []), ensure_ascii=False)}

SOURCES (news reports from several outlets):
{_sources_block(sources, budget)}

Check every factual statement in the title, summary and body (not only the writer's list):
names and spellings, numbers, dates, places, who said what, cause and effect.
A claim is "supported" only if a source above clearly confirms it. Do not use your own memory as evidence:
your training data may be outdated, and news changes daily. If no source covers a claim, it is "unsupported".
Also flag: anything that accuses a named person, speculation presented as fact, outdated information,
and a headline that overstates the body.
{SENSITIVE_RULES}

Return ONLY JSON:
{{"verdict": "PASS" | "FIX" | "FAIL",
  "sensitive": true/false,
  "claims": [{{"claim": "...", "status": "supported" | "unsupported" | "contradicted", "evidence": "source name or URL"}}],
  "corrections": [{{"wrong": "exact text from article", "right": "corrected text", "why": "..."}}],
  "notes": "one or two lines in English for the editor"}}
Use PASS only if every claim is supported and nothing is misleading.
Use FIX if there are small errors that the corrections fully solve. Use FAIL for anything else."""
    return prompt


def revise(article, check):
    prompt = f"""Apply these fact-check corrections to the Hindi article. Change ONLY what the corrections
require; remove any sentence marked unsupported or contradicted. Keep the same JSON keys and format.

CORRECTIONS: {json.dumps(check.get('corrections', []), ensure_ascii=False)}
PROBLEM CLAIMS: {json.dumps([c for c in check.get('claims', []) if c.get('status') != 'supported'], ensure_ascii=False)}

ARTICLE JSON:
{json.dumps({k: article[k] for k in ('title_hi','slug_en','summary','body_html','search_description','image_text','image_alt','claims','sources_used')}, ensure_ascii=False)}"""
    fixed, _ = llm.ask(prompt, providers=_order(), temperature=0.2, max_tokens=6000)
    for k, v in article.items():
        fixed.setdefault(k, v)
    return fixed
