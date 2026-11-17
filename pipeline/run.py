"""Hourly job: trends -> pick -> research -> verified fact sheet -> write -> fact-check -> photo -> publish or draft -> email."""
import datetime as dt
import json
import os
import re
import subprocess
import traceback

from . import blogger, compose, config, editorial, image, llm, notify, search, sources

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
NOW = dt.datetime.now(IST)
TODAY = NOW.strftime("%Y-%m-%d")


def norm(s):
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def load_state():
    try:
        with open(config.STATE_FILE, encoding="utf-8") as f:
            st = json.load(f)
    except FileNotFoundError:
        st = {}
    st.setdefault("seen", {})       # normalised trend -> date first handled
    st.setdefault("posts", [])      # {date, trend, title, status, url}
    cutoff = (NOW - dt.timedelta(days=4)).strftime("%Y-%m-%d")
    st["seen"] = {k: v for k, v in st["seen"].items() if v >= cutoff}
    st["posts"] = st["posts"][-300:]
    return st


def save_state(st):
    os.makedirs(os.path.dirname(config.STATE_FILE), exist_ok=True)
    with open(config.STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def git_push(paths, message):
    """Commit images/state so the image URL works (served from GitHub via jsDelivr)."""
    if config.DRY_RUN or not config.REPO:
        return None
    subprocess.run(["git", "add", *paths], check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    subprocess.run(["git", "commit", "-m", message], check=True)
    subprocess.run(["git", "push"], check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def research(trend, query):
    """Full-text news reports (no API keys): the articles Google Trends links to, plus DuckDuckGo news
    search. Google News headlines are used only to count outlets if search finds too few."""
    q = query or trend["title"]
    found, seen = [], set()

    def add(item):
        u = item.get("url", "")
        if u and u not in seen and "news.google.com" not in u:
            seen.add(u)
            found.append(item)

    for n in trend["news"][:4]:
        add({**n, "snippet": ""})
    for h in search.news(q, timelimit="w", max_results=10) + search.news(trend["title"], timelimit="d", max_results=6):
        add(h)
    fetched = 0
    for item in found:
        if fetched >= 8 or sum(1 for x in found if x.get("text")) >= 6:
            break
        item["text"] = search.article_text(item["url"])
        fetched += 1
    full = [x for x in found if len(x.get("text") or "") >= 400]
    rest = [x for x in found if x not in full and x.get("snippet")]
    srcs = (full + rest)[:10]
    outlets = {sources.outlet_key(x["source"]) for x in found if x.get("source")}
    if len(outlets) < config.MIN_OUTLETS:
        outlets |= {sources.outlet_key(x["source"]) for x in sources.google_news(q, "en", 10) if x.get("source")}
    full_outlets = {sources.outlet_key(x["source"]) for x in full}
    print(f"  research: {len(full)} full articles from {len(full_outlets)} outlets, {len(outlets)} outlets in all")
    return srcs, len(outlets), len(full_outlets)


def similar_exists(title, recent):
    words = set(re.findall(r"\w+", norm(title)))
    for r in recent:
        rw = set(re.findall(r"\w+", norm(r)))
        if words and len(words & rw) / max(1, len(words)) > 0.6:
            return True
    return False


def main():
    st = load_state()
    made_today = sum(1 for p in st["posts"] if p["date"] == TODAY)
    if made_today >= config.MAX_PER_DAY:
        print("Daily limit reached; nothing to do.")
        return

    trends = [t for t in sources.fetch_trends()
              if t["traffic"] >= config.MIN_TRAFFIC and norm(t["title"]) not in st["seen"]]
    print(f"{len(trends)} fresh trends above {config.MIN_TRAFFIC}+ searches")
    if not trends:
        return
    trends = sorted(trends, key=lambda t: -t["traffic"])[:15]

    try:
        picks = editorial.triage(trends)
    except llm.AIUnavailable as e:
        print(f"AI services unavailable right now, trying again next hour: {e}")
        save_state(st)
        return
    for p in picks:  # remember every trend we looked at, so we don't re-check it every hour
        i = p.get("index")
        if isinstance(i, int) and 0 <= i < len(trends):
            st["seen"][norm(trends[i]["title"])] = TODAY
    picks = [p for p in picks if p.get("relevant") and p.get("section") in config.SECTIONS]
    picks.sort(key=lambda p: -int(p.get("priority", 0)))
    print("Picked:", [(trends[p["index"]]["title"], p.get("priority"), p.get("sensitive")) for p in picks])

    bl = None if config.DRY_RUN else blogger.Blogger()
    recent = bl.recent_titles() if bl else []
    done = 0
    for p in picks:
        if done >= config.MAX_PER_RUN or made_today + done >= config.MAX_PER_DAY:
            break
        trend = trends[p["index"]]
        print(f"\n=== {trend['title']} ({trend['traffic']}+) -> {p['section']}")
        try:
            srcs, n_outlets, n_full = research(trend, p.get("query"))
            if n_outlets < config.MIN_OUTLETS or n_full < config.MIN_FULLTEXT:
                print(f"  skip: {n_outlets} outlets, {n_full} readable in full (need {config.MIN_OUTLETS}/{config.MIN_FULLTEXT})")
                continue

            facts, rejected, event_en, _ = editorial.extract_facts(trend["title"], srcs)
            if len(facts) < config.MIN_FACTS:
                print(f"  skip: only {len(facts)} verified facts")
                continue

            article = editorial.write(trend["title"], p["section"], facts, event_en)
            if similar_exists(article["title_hi"], recent):
                print("  skip: we already have a similar post")
                continue

            check = editorial.fact_check(article, facts, srcs)
            if check.get("verdict") == "FIX":
                article = editorial.revise(article, check, facts)
                check = editorial.fact_check(article, facts, srcs)
            print(f"  fact-check: {check.get('verdict')} | {check.get('notes','')[:160]}")
            check["facts_rejected"] = len(rejected)

            # ---- decide: publish or hold as draft
            reasons = []
            if config.PUBLISH_MODE != "auto":
                reasons.append("safe mode: PUBLISH_MODE=draft")
            if p.get("sensitive") or check.get("sensitive"):
                reasons.append("संवेदनशील विषय")
            if check.get("verdict") != "PASS":
                reasons.append(f"fact-check {check.get('verdict')}")
            if any(c.get("status") != "supported" for c in check.get("claims", [])):
                reasons.append("कुछ दावे पुष्ट नहीं हुए")
            if check.get("numbers_not_in_sources"):
                reasons.append("कुछ संख्याएँ स्रोतों में नहीं मिलीं")
            publish = not reasons

            # ---- image: Unsplash photo (shown from Unsplash), else a branded card committed to the repo
            slug = compose.slug(article.get("slug_en") or trend["title"])
            photo = image.unsplash_photo(article.get("image_query_en"), used=st.setdefault("photos", [])[-200:])
            if photo:
                img_url = photo["url"]
                article["_photo"] = photo
                st["photos"].append(photo["id"])
            else:
                img_rel = f"{config.IMAGE_DIR}/{NOW:%Y/%m}/{slug}-{NOW:%H%M}.jpg"
                image.make_card(article["title_hi"], p["section"], img_rel)
                sha = git_push([img_rel], f"image: {slug}") or "main"
                img_url = f"https://cdn.jsdelivr.net/gh/{config.REPO}@{sha}/{img_rel}"

            html = compose.build_post(article, img_url, srcs)
            labels = [p["section"], config.TREND_LABEL]
            if config.DRY_RUN:
                os.makedirs("out", exist_ok=True)
                with open(f"out/{slug}.html", "w", encoding="utf-8") as f:
                    f.write(f"<h1>{article['title_hi']}</h1>\n<!-- publish={publish} reasons={reasons} -->\n{html}")
                with open(f"out/{slug}.check.json", "w", encoding="utf-8") as f:
                    json.dump({"check": check, "facts": facts, "rejected_facts": rejected,
                               "sources": [{k: x.get(k) for k in ("source", "title", "url")} for x in srcs]},
                              f, ensure_ascii=False, indent=1)
                post = {"url": "", "edit_url": f"out/{slug}.html"}
            else:
                post = bl.create(slug.replace("-", " "), article["title_hi"], html, labels, publish)

            status = "published" if publish else "draft"
            notify.post_report(status, ", ".join(reasons), article, post, check, trend)
            st["posts"].append({"date": TODAY, "trend": trend["title"], "title": article["title_hi"],
                                "status": status, "url": post.get("url", ""), "why": reasons})
            recent.append(article["title_hi"])
            done += 1
            print(f"  -> {status} {post.get('url') or post.get('edit_url')}")
        except llm.AIUnavailable as e:
            print(f"  skip (AI unavailable): {e}")
        except Exception:  # one bad topic must not stop the run
            err = traceback.format_exc()
            print(err)
            notify.run_failed(f"Topic: {trend['title']}\n\n{err}")

    save_state(st)
    git_push([config.STATE_FILE], f"state: {NOW:%Y-%m-%d %H:%M} IST")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        notify.run_failed(traceback.format_exc())
        raise
