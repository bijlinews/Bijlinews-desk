"""AI steps: pick trends -> build a verified fact sheet -> write ONLY from it -> fact-check.

Why a fact sheet: when the writer was given whole articles (or only headlines) it filled gaps from
its own memory, which is often outdated or wrong. Now the AI first copies facts with an exact quote
from a source; Python throws away any fact whose quote isn't really in that source; the writer sees
only the verified facts; and the final check is done by a different AI plus plain-Python number checks.
"""
import datetime as dt
import json

from . import config, factcheck, llm, search

SECTIONS = ", ".join(config.ALLOWED_SECTIONS)
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def today():
    return dt.datetime.now(IST).strftime("%d %B %Y")


# Topics that must never auto-publish. The pipeline saves these as drafts for a human.
SENSITIVE_RULES = """
Mark "sensitive": true ONLY if the story involves any of these:
- death, suicide, murder, or an accident/disaster with victims
- a crime, arrest, FIR or court case, or an allegation/accusation against a named person or company
- communal, caste or religious tension; riots; hate speech
- elections, vote counts, or claims made by/against politicians or parties
- health, medicine, diet or disease advice
- an explicit buy/sell/hold recommendation or target price, crypto tips, betting or gambling
NOT sensitive: ordinary business news - company results, revenue/profit numbers, share price moves,
market updates, product launches, executive appointments or exits, deals and funding.

Mark "blocked": true (cannot be published in India) ONLY if the story would name or identify a victim of
rape or any sexual offence, or identify a child/minor who is accused of a crime, a victim of abuse, or in
sexual content. Otherwise "blocked": false.
"""


def _backup(p):
    return "groq_alt" if p != "groq_alt" else "groq"


# ---------------------------------------------------------------- 1. triage
def triage(trends):
    """Decide which trends are worth an article for Hindi-speaking Indian readers."""
    lines = []
    for i, t in enumerate(trends):
        heads = " | ".join(f"{n['title']} ({n['source']})" for n in t["news"][:3])
        lines.append(f"{i}. \"{t['title']}\" — searches: {t['traffic']}+ — news: {heads}")
    prompt = f"""You are the news editor of बिजली न्यूज़ (bijlinews.com), a Hindi news website for readers in India.
Today is {today()}. Below are topics trending on Google in India right now, with the headlines that explain them.

{chr(10).join(lines)}

For EACH topic decide:
- "relevant": true only if a Hindi-speaking reader in India would care, there is a real news event
  behind it, AND it fits our beats. We are a small site that wants to be the best Hindi source on a few beats:
  money and markets (शेयर बाजार, बिजनेस, personal finance, taxes, banks, RBI, prices that affect households),
  Indian cricket (खेल: ONLY cricket involving Indian national, IPL, women's or domestic teams/players),
  and national India news (भारत: government decisions, schemes, exam/job announcements, weather warnings,
  major events that affect readers).
  Mark relevant=false for: other sports (football, tennis, F1, MotoGP...), foreign news with no direct
  India impact, celebrity gossip, films/OTT/box office, video games, live scores, match schedules or
  previews, lottery or result pages, daily price/rate lookups, a generic word, or a brand name with no news.
- "section": exactly one of [{SECTIONS}] or null.
- "sensitive": see rules.
{SENSITIVE_RULES}
- "priority": 1-10 (10 = most useful for our readers: changes their money, plans or safety, or a big Indian
  cricket result). Lower it for stories every big site has already covered in the same way.
- "query": a short English news-search query that finds THIS specific event (include the full name of the
  person/team/company and the event, e.g. "Sunny Deol Suryaa release postponed"), not just the trend word.

Return JSON: {{"topics": [{{"index": 0, "relevant": true, "section": "...", "sensitive": false, "blocked": false,
"reason": "one line", "priority": 7, "query": "..."}}]}}"""
    data, _ = llm.ask(prompt, providers=(config.TRIAGE, _backup(config.TRIAGE)), temperature=0.2, max_tokens=3000)
    return data.get("topics", [])


# ---------------------------------------------------------------- 2. fact sheet
def _sources_block(sources, budget):
    out, used = [], 0
    per = max(600, budget // max(1, len(sources)))
    for i, s in enumerate(sources, 1):
        body = (s.get("text") or s.get("snippet") or "")[:per]
        block = f"[{i}] {s['source']} ({s.get('published', '')[:16]}) — {s['title']}\n{body}"
        if used + len(block) > budget:
            break
        out.append(block)
        used += len(block)
    return "\n\n".join(out)


def extract_facts(topic, sources):
    """Returns (verified_facts, rejected_facts, provider)."""
    last = None
    for p in (config.WRITER, _backup(config.WRITER)):
        for budget in (7000, 5000, 3500):
            prompt = f"""Today is {today()}. Read the news reports below about "{topic}" and list the facts they state.

RULES
- Copy each fact's evidence as an EXACT quote: a continuous piece of text copied character-for-character from
  ONE report (20–200 characters). Do not translate, shorten or fix the quote.
- Only facts about this specific news event. Skip ads, related-story links, opinions and rumours.
- Never add anything from your own knowledge.
- If reports disagree on a fact, include both versions with their own quotes and say so in "fact_hi".
- Note when it happened if the report says so.
- In "fact_hi", keep names of people, places, teams, companies and all abbreviations exactly as the report
  writes them (Latin letters are fine, e.g. "TRC", "SEBI", "Nvidia"). NEVER expand or translate an
  abbreviation unless the report itself spells it out; do not guess what it stands for.

REPORTS:
{_sources_block(sources, budget)}

Return JSON: {{"event_en": "one English sentence: what happened, who, when",
 "facts": [{{"fact_hi": "the fact in simple Hindi", "quote": "exact text from the report", "source": 1}}]}}
List 8 to 25 facts, most important first."""
            try:
                data, used = llm.ask(prompt, providers=(p,), temperature=0.0, max_tokens=4000)
            except llm.TooLarge as e:
                last = e
                continue
            except llm.AIUnavailable as e:
                last = e
                break
            good, bad = factcheck.verify_quotes(data.get("facts", []), sources)
            print(f"  facts: {len(good)} verified, {len(bad)} rejected (quote not found) — by {used}")
            return good, bad, data.get("event_en", ""), used
    raise llm.AIUnavailable(f"fact sheet failed: {last}")


# ---------------------------------------------------------------- 3. write
def _facts_block(facts, with_quotes=False, budget=9000):
    out, used = [], 0
    for i, f in enumerate(facts, 1):
        line = f"F{i}. {f.get('fact_hi', '')} [स्रोत {f.get('source')}]"
        if with_quotes:
            line += f"\n    quote: \"{f.get('quote', '')}\""
        if used + len(line) > budget:
            break
        out.append(line)
        used += len(line)
    return "\n".join(out)


def write(topic, section, facts, event_en, sources=None):
    last = None
    for p in (config.WRITER, _backup(config.WRITER)):
        try:
            article, _ = llm.ask(_write_prompt(topic, facts, event_en, sources), providers=(p,),
                                 temperature=0.3, max_tokens=4000)
            article["_writer"] = p
            return article
        except llm.AIUnavailable as e:
            last = e
    raise llm.AIUnavailable(f"no writer available: {last}")


def _outlets_block(sources):
    if not sources:
        return "(not given)"
    return "\n".join(f"स्रोत {i} = {s.get('source') or 'report'}" for i, s in enumerate(sources, 1))


FAQ_RULE = """- "faq": exactly 3 {"q": "a question readers ask, in Hindi", "a": "1-2 sentence Hindi answer"}; every answer
   must come only from the facts. If the facts can't answer 3 questions, give fewer."""


def _write_prompt(topic, facts, event_en, sources=None):
    faq_rule = FAQ_RULE if config.SHOW_FAQ else '- "faq": [] (always an empty list).'
    return f"""You write for बिजली न्यूज़, a Hindi news site ("खबर भी, वजह भी"). Today is {today()}.
Write a Hindi news article about: "{topic}" — {event_en}

STRICT RULES (the article is checked automatically; any extra fact gets it rejected)
- Use ONLY the verified facts F1, F2... below. Every sentence must come from one or more of these facts.
- Do NOT add background, history, numbers, dates, ages, quotes, reasons or names from your own memory,
  even if you are sure. If the facts don't explain "why", do not guess; just leave it out.
- Copy every number, date and name exactly as in the facts.
- Attribute claims to the outlet that reported them, by name: e.g. "PTI के मुताबिक", "Reuters की रिपोर्ट के अनुसार"
  (outlet names are listed below; each fact shows its स्रोत number). Use "रिपोर्ट्स के मुताबिक" only when several
  outlets report the same thing. For official statements, name who said it.
- Keep names of people, places, teams, companies and abbreviations exactly as in the facts. NEVER expand an
  abbreviation into words (write "TRC ग्राउंड", not a guess of what TRC stands for).
- Simple, natural Hindi (Devanagari) for a 10th-class student. No clickbait, no opinions.
- It is fine if the article is short. Short and correct is better than long and wrong.

OUTLETS:
{_outlets_block(sources)}

VERIFIED FACTS:
{_facts_block(facts)}

Return JSON:
- "title_hi": Hindi headline, max 75 characters, factual, says only what the facts say. Lead with the most
   important new fact: what changed, by how much, for whom (e.g. "Nasdaq 6.5% उछला, Nvidia में 31% की तेजी"),
   with the key number if there is one. No filler headlines like "X खुला", "मैच आज होगा", "जानें पूरी खबर".
- "slug_en": short English URL slug, lowercase words joined by hyphens, max 6 words, no dates.
- "summary": exactly 3 short Hindi bullet strings: (1) क्या हुआ, (2) अभी चर्चा क्यों, (3) आगे क्या/असर.
   Only from the facts; if a point isn't in the facts, write a different true point from them.
- "body_html": 250–500 Hindi words, HTML using only <p>, <h2>, <ul>, <li>, <strong>. An opening paragraph
   (who, what, when, where), then 2–3 sections with <h2> headings that fit the facts.
- "search_description": Hindi, 140–160 characters.
- "image_alt": Hindi alt text for a generic photo about the topic.
- "image_query_en": 2–4 English words for a GENERIC stock photo search: objects or places only, e.g.
   "gold jewellery", "cricket stadium night", "indian court building", "film camera set".
   Never a person's name, brand, party or team name.
- "claims_en": the 5 most important facts as short English web-search queries (max 12 words each),
   including names, e.g. "Sunny Deol Suryaa release postponed November 2026".
- "key_numbers": 0 to 3 of the most important numbers in the facts, each {{"value": "the number exactly as in
   the facts, e.g. '₹1,429' or '145 किमी/घंटा'", "label": "2-5 Hindi words saying what it is"}}. [] if none.
- "timeline": [] unless the facts give 3 or more dated events; then up to 5 {{"when": "date as in the facts",
   "what": "one short Hindi line"}} in time order.
- "why_it_matters": 1-2 Hindi sentences on what this means for readers (their money, exams, travel, safety,
   the team's chances) — ONLY if the facts state such an effect or consequence. Otherwise "" (empty). No guessing.
{faq_rule}
- "facts_used": list of fact numbers used, e.g. [1, 2, 5]."""


def extras_text(article):
    """Number tiles, timeline and FAQ as plain text, so they are fact-checked like the body."""
    parts = []
    if article.get("why_it_matters"):
        parts.append(f"इसका मतलब: {article['why_it_matters']}")
    for n in article.get("key_numbers") or []:
        if isinstance(n, dict):
            parts.append(f"{n.get('value', '')} — {n.get('label', '')}")
    for t in article.get("timeline") or []:
        if isinstance(t, dict):
            parts.append(f"{t.get('when', '')}: {t.get('what', '')}")
    for f in article.get("faq") or []:
        if isinstance(f, dict):
            parts.append(f"प्रश्न: {f.get('q', '')} उत्तर: {f.get('a', '')}")
    return "\n".join(parts)


# ---------------------------------------------------------------- 4. check
def fact_check(article, facts, sources):
    """A different AI than the writer compares the article with the verified facts and fresh web
    search results. Python separately checks that every number in the article is in the sources."""
    missing = factcheck.unsupported_numbers(article, sources, facts)
    names_missing = factcheck.unsupported_names(article, sources, facts)
    guessed = factcheck.expanded_abbreviations(article, sources, facts)
    web = []
    for q in [q for q in (article.get("claims_en") or []) if isinstance(q, str)][:5]:
        web.append((q, search.web(q, max_results=3)))
    web_text = "\n".join(f"SEARCH: {q}\n" + "\n".join(f"- {h['source']}: {h['title'][:90]} — {h['snippet'][:220]}"
                                                    for h in hits) for q, hits in web)
    writer = article.get("_writer") or config.WRITER
    order = (_backup(writer), writer)      # a different model checks first
    result, judge = None, None
    for fbudget, wbudget in ((4500, 2400), (3000, 1400)):
        prompt = f"""You are a strict fact-checker for a Hindi news website. Today is {today()}.
Another AI wrote the article below. Find every mistake BEFORE it is published.

HEADLINE: {article['title_hi']}
SUMMARY: {json.dumps(article.get('summary', []), ensure_ascii=False)}
ARTICLE: {article['body_html']}
NUMBER TILES / TIMELINE / FAQ (also part of the article):
{extras_text(article) or "(none)"}

VERIFIED FACTS (each with an exact quote from a news report):
{_facts_block(facts, with_quotes=True, budget=fbudget)}

WEB SEARCH RESULTS (searched just now):
{web_text[:wbudget] or "(none)"}

Check EVERY sentence of the headline, summary, article, number tiles, timeline and FAQ — names and spellings, numbers, dates, places,
who said what, cause and effect. Compare the Hindi spelling of every name, place and abbreviation with the
quotes: a wrong name, or an abbreviation turned into words the quotes don't contain, is "contradicted".
A statement is "supported" only if the facts or search results above
clearly confirm it. Do NOT use your own memory as evidence (it may be outdated); if nothing above covers
a statement it is "unsupported". Flag a headline that says more than the facts.
{SENSITIVE_RULES}

Return ONLY JSON:
{{"verdict": "PASS" | "FIX" | "FAIL",
  "sensitive": true/false,
  "blocked": true/false,
  "claims": [{{"claim": "short Hindi statement from the article", "status": "supported" | "unsupported" | "contradicted", "evidence": "F3 or source domain"}}],
  "corrections": [{{"wrong": "exact text from the article", "right": "corrected text, or empty to delete", "why": "..."}}],
  "notes": "one or two lines in English for the editor"}}
PASS only if every statement is supported. FIX if the corrections fully solve the problems. Otherwise FAIL."""
        try:
            result, judge = llm.ask(prompt, providers=order, temperature=0.0, max_tokens=3000)
            break
        except llm.TooLarge:
            continue
        except llm.AIUnavailable as e:
            result = {"verdict": "UNAVAILABLE", "claims": [], "corrections": [], "notes": str(e)[:200]}
            break
    if result is None:
        result = {"verdict": "UNAVAILABLE", "claims": [], "corrections": [], "notes": "prompt too large"}
    result["numbers_not_in_sources"] = missing
    result["names_not_in_sources"] = names_missing
    result["guessed_expansions"] = guessed
    for g in guessed:
        result["claims"] = list(result.get("claims") or []) + [
            {"claim": g, "status": "contradicted", "evidence": "स्रोत में इसका विस्तार नहीं है (Python जाँच)"}]
        result["corrections"] = list(result.get("corrections") or []) + [
            {"wrong": g, "right": g.split("(")[-1].rstrip(")"),
             "why": "abbreviation expanded by guessing; keep only the abbreviation"}]
    for n in names_missing:
        result["claims"] = list(result.get("claims") or []) + [
            {"claim": n, "status": "unsupported", "evidence": "यह नाम किसी स्रोत में नहीं मिला (Python जाँच)"}]
    if (guessed or names_missing) and result.get("verdict") == "PASS":
        result["verdict"] = "FIX"
    if missing:
        result["claims"] = list(result.get("claims") or []) + [
            {"claim": f"संख्या {n}", "status": "unsupported", "evidence": "किसी स्रोत में नहीं मिली (Python जाँच)"}
            for n in missing]
        if result.get("verdict") == "PASS":
            result["verdict"] = "FIX"
    result["by_checker"] = {f"{judge or '—'} + web search + number check": result.get("verdict")}
    result["notes"] = (f"Checked by {judge}; {sum(len(h) for _, h in web)} web results; "
                       f"numbers not in sources: {missing or 'none'}; names not in sources: {names_missing or 'none'}; "
                       f"guessed abbreviations: {guessed or 'none'}. " + str(result.get("notes", "")))
    result["evidence_links"] = [h["url"] for _, hits in web for h in hits][:12]
    return result


def revise(article, check, facts):
    bad = [c for c in check.get("claims", []) if c.get("status") != "supported"]
    prompt = f"""Fix this Hindi news article. Apply the corrections, and DELETE every sentence, number tile, timeline
entry or FAQ answer that contains a problem statement or one of these numbers: {check.get('numbers_not_in_sources') or []},
or one of these names that no source contains: {check.get('names_not_in_sources') or []}.
Where an abbreviation was expanded by guessing ({check.get('guessed_expansions') or []}), keep only the
abbreviation and keep the sentence grammatical.
Do not add anything new. Use only the verified facts below. Keep the same JSON keys.

CORRECTIONS: {json.dumps(check.get('corrections', []), ensure_ascii=False)}
PROBLEM STATEMENTS: {json.dumps(bad, ensure_ascii=False)}

VERIFIED FACTS:
{_facts_block(facts, budget=5000)}

ARTICLE JSON:
{json.dumps({k: article.get(k) for k in ('title_hi', 'slug_en', 'summary', 'body_html', 'search_description', 'image_alt', 'image_query_en', 'claims_en', 'key_numbers', 'timeline', 'faq', 'why_it_matters', 'facts_used')}, ensure_ascii=False)}"""
    fixed, _ = llm.ask(prompt, providers=(article.get("_writer") or config.WRITER, _backup(article.get("_writer") or config.WRITER)),
                       temperature=0.0, max_tokens=4000)
    for k, v in article.items():
        fixed.setdefault(k, v)
    return fixed
