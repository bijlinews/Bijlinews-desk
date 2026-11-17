"""The three AI steps: pick trends, write the article, fact-check it."""
import json

from . import config, gemini, llm, search

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
    data, _ = llm.ask(prompt, providers=(config.TRIAGE, _other(config.TRIAGE)), temperature=0.2, max_tokens=3000)
    return data.get("topics", [])


def _other(p):
    return "groq" if p != "groq" else "openrouter"


def _order():
    """Writer first, the other AI as backup."""
    return (config.WRITER, _other(config.WRITER))


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


WRITER_BUDGET = {"groq": 7000, "openrouter": 16000, "mistral": 16000}


def write(topic, section, sources):
    last = None
    for p in _order():
        try:
            article, _ = llm.ask(_write_prompt(topic, sources, WRITER_BUDGET.get(p, 8000)), providers=(p,),
                                 temperature=0.5, max_tokens=4500 if p == "groq" else 6000)
            article["_writer"] = p
            return article
        except llm.AIUnavailable as e:
            last = e
    raise llm.AIUnavailable(f"no writer available: {last}")


def _write_prompt(topic, sources, budget):
    return f"""You write for बिजली न्यूज़, a Hindi news site whose promise is "खबर भी, वजह भी" —
the news AND why it matters. Write an original Hindi news explainer about: "{topic}".

Use ONLY facts found in the sources below. Never invent names, numbers, dates, quotes or causes.
If sources disagree, say so or leave the point out. If a detail is not in the sources, do not write it.
Write in simple, natural Hindi (Devanagari) that a 10th-class student understands. English terms
that Indians commonly use (IPO, RBI, T20) are fine. No clickbait, no exaggeration, no opinions.

SOURCES:
{_sources_block(sources, budget)}

Return JSON with these keys:
- "title_hi": Hindi headline, max 90 characters, factual, no ALL CAPS, no "!!".
- "slug_en": short English URL slug, lowercase words joined by hyphens, max 6 words, no dates.
- "summary": exactly 3 short Hindi bullet strings: (1) क्या हुआ, (2) अभी चर्चा क्यों, (3) आप पर/देश पर असर.
- "body_html": the article, 350–650 Hindi words, as HTML using only <p>, <h2>, <ul>, <li>, <strong>.
   Structure: an opening paragraph (who, what, when, where), then <h2>पूरा मामला क्या है</h2>,
   <h2>यह अभी क्यों चर्चा में है</h2>, <h2>आगे क्या</h2>. Do not repeat the summary bullets word for word.
- "search_description": Hindi, 140–160 characters, unique, describes the article.
- "image_text": a Hindi line of max 60 characters for the cover image (can be the headline shortened).
- "image_alt": Hindi alt text describing the cover image.
- "image_prompt_en": one English sentence describing a symbolic illustration for this story, e.g.
   "gold coins and jewellery on a dark wooden table, warm light, shallow depth of field".
   NEVER describe real or identifiable people, faces, politicians, celebrities, logos, brand names,
   party symbols, flags of parties, text, letters or numbers. Objects, places and anonymous scenes only.
- "claims": list of every checkable factual claim in the article (names, numbers, dates, events), in Hindi.
- "claims_en": the 5 most important of those claims, each rewritten as a short English web-search
   query (max 12 words), e.g. "EPFO employers deposit October PF by November 15 penalty".
- "sources_used": list of source numbers you relied on, e.g. [1, 3]."""


def fact_check(article, sources):
    """Search the web for the article's key claims and let an AI judge them against the results.
    Falls back to two independent AI checks against the news sources if web search is unavailable."""
    if gemini.enabled():
        try:
            return google_check(article)
        except gemini.GeminiUnavailable as e:
            print(f"  ! Gemini/Google check unavailable ({str(e)[:120]}); trying the next checker")
    if search.enabled():
        try:
            return web_check(article)
        except (search.SearchUnavailable, llm.AIUnavailable) as e:
            print(f"  ! web search check unavailable ({str(e)[:120]}); using two-AI check instead")
    return ai_check(article, sources)


def google_check(article):
    """Gemini searches Google itself and judges every claim."""
    prompt = f"""You are a strict fact-checker for a Hindi news website. Use Google Search to verify the
article below BEFORE it is published. Search for each important fact; prefer official sources and
established Indian news outlets. Today's date matters: check the facts are current, not outdated.

HEADLINE: {article['title_hi']}
SUMMARY: {json.dumps(article['summary'], ensure_ascii=False)}
ARTICLE (HTML): {article['body_html']}
KEY CLAIMS: {json.dumps(article.get('claims', [])[:15], ensure_ascii=False)}

Check names and spellings, numbers, dates, places, who said what, and cause and effect.
"supported" = your search results clearly confirm it. "contradicted" = results say something different.
"unsupported" = you could not find confirmation. Also flag a headline that overstates the facts.
{SENSITIVE_RULES}

Reply with ONLY one JSON object, no other text:
{{"verdict": "PASS" | "FIX" | "FAIL",
  "sensitive": true/false,
  "claims": [{{"claim": "...", "status": "supported" | "unsupported" | "contradicted", "evidence": "source name"}}],
  "corrections": [{{"wrong": "exact text from the article", "right": "corrected text", "why": "..."}}],
  "notes": "one or two lines in English for the editor"}}
PASS only if every claim is supported. FIX if small errors are fully solved by the corrections. Otherwise FAIL."""
    result, urls, searches, model = gemini.grounded(prompt)
    result["by_checker"] = {f"Gemini ({model}) + Google Search": result.get("verdict")}
    result["notes"] = f"Google searches: {len(searches)}. " + str(result.get("notes", ""))
    result["evidence_links"] = urls[:12]
    return result


def web_check(article):
    queries = [q for q in (article.get("claims_en") or []) if isinstance(q, str) and q.strip()][:5]
    if not queries:
        queries = [article.get("slug_en", "").replace("-", " ") or article["title_hi"]]
    evidence = []
    for q in queries:
        hits = search.tavily(q, topic="general", max_results=3)
        evidence.append({"query": q, "results": [
            {"source": h["source"], "title": h["title"][:120], "url": h["url"], "text": h["text"][:450]} for h in hits]})
    ev_text = "\n\n".join(
        f"SEARCH {i}: {e['query']}\n" + "\n".join(f"- {r['source']}: {r['title']} — {r['text']}" for r in e["results"])
        for i, e in enumerate(evidence, 1))
    prompt = f"""You are a strict fact-checker for a Hindi news website. Below is an article's headline,
summary and factual claims, and the results of live web searches made just now to verify them.

HEADLINE: {article['title_hi']}
SUMMARY: {json.dumps(article['summary'], ensure_ascii=False)}
CLAIMS (Hindi): {json.dumps(article.get('claims', [])[:12], ensure_ascii=False)}

WEB SEARCH RESULTS:
{ev_text}

Judge every claim ONLY from the search results above, never from your own memory (it may be outdated).
"supported" = a reliable result clearly confirms it. "contradicted" = a result says something different.
"unsupported" = the results don't cover it. Check names, numbers, dates and who-said-what carefully.
Also flag a headline that overstates the facts.
{SENSITIVE_RULES}

Return ONLY JSON:
{{"verdict": "PASS" | "FIX" | "FAIL",
  "sensitive": true/false,
  "claims": [{{"claim": "...", "status": "supported" | "unsupported" | "contradicted", "evidence": "source domain"}}],
  "corrections": [{{"wrong": "exact text from the article", "right": "corrected text", "why": "..."}}],
  "notes": "one or two lines in English for the editor"}}
PASS only if every claim is supported. FIX if small errors are fully solved by the corrections. Otherwise FAIL."""
    result, judge = llm.ask(prompt, providers=("groq", "openrouter"), temperature=0.1, max_tokens=3000)
    result["by_checker"] = {f"web search + {judge}": result.get("verdict")}
    result["notes"] = f"{len(queries)} web searches, judged by {judge}. " + str(result.get("notes", ""))
    result["evidence_links"] = [r["url"] for e in evidence for r in e["results"]][:12]
    return result


def ai_check(article, sources):
    """Both AIs check the article independently. PASS only if both say PASS."""
    results = {}
    for p, budget in (("openrouter", 16000), ("groq", 4500)):
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
{json.dumps({k: article.get(k) for k in ('title_hi','slug_en','summary','body_html','search_description','image_text','image_alt','image_prompt_en','claims','claims_en','sources_used')}, ensure_ascii=False)}"""
    fixed, _ = llm.ask(prompt, providers=_order(), temperature=0.2, max_tokens=6000)
    for k, v in article.items():
        fixed.setdefault(k, v)
    return fixed
