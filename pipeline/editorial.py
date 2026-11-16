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
    data = llm.ask(prompt, model=config.WRITER_MODEL, temperature=0.2)
    return data.get("topics", [])


def _sources_block(sources):
    out = []
    for i, s in enumerate(sources, 1):
        body = s.get("text") or ""
        out.append(f"[{i}] {s['source']} — {s['title']}\nURL: {s['url']}\n{body[:2500]}")
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
    return llm.ask(prompt, model=config.WRITER_MODEL, temperature=0.5)


def fact_check(article, sources):
    """Independent check. Sees sources the writer did NOT see, and can search Google itself."""
    search_note = ("You may also run Google searches to verify claims. Prefer official sources and "
                   "well-known Indian news outlets." if config.CHECKER_WEB_SEARCH else "")
    prompt = f"""You are a strict fact-checker for a Hindi news website. A different writer produced the
article below. Your job is to find mistakes BEFORE it is published. Be sceptical.

ARTICLE TITLE: {article['title_hi']}
ARTICLE SUMMARY: {json.dumps(article['summary'], ensure_ascii=False)}
ARTICLE BODY (HTML): {article['body_html']}
CLAIMS LISTED BY WRITER: {json.dumps(article.get('claims', []), ensure_ascii=False)}

INDEPENDENT SOURCES (from other outlets):
{_sources_block(sources)}

{search_note}

Check every factual statement in the title, summary and body (not only the writer's list):
names and spellings, numbers, dates, places, who said what, cause and effect.
A claim is "supported" only if at least one reliable independent source above (or your search) confirms it.
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
    return llm.ask(prompt, model=config.CHECKER_MODEL, web_search=config.CHECKER_WEB_SEARCH, temperature=0.1)


def revise(article, check):
    prompt = f"""Apply these fact-check corrections to the Hindi article. Change ONLY what the corrections
require; remove any sentence marked unsupported or contradicted. Keep the same JSON keys and format.

CORRECTIONS: {json.dumps(check.get('corrections', []), ensure_ascii=False)}
PROBLEM CLAIMS: {json.dumps([c for c in check.get('claims', []) if c.get('status') != 'supported'], ensure_ascii=False)}

ARTICLE JSON:
{json.dumps({k: article[k] for k in ('title_hi','slug_en','summary','body_html','search_description','image_text','image_alt','claims','sources_used')}, ensure_ascii=False)}"""
    fixed = llm.ask(prompt, model=config.WRITER_MODEL, temperature=0.2)
    for k, v in article.items():
        fixed.setdefault(k, v)
    return fixed
