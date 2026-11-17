"""Hourly job: trends -> pick -> research -> verified fact sheet -> write -> fact-check -> photo -> publish or draft -> email."""
import datetime as dt
import json
import os
import re
import subprocess
import time
import traceback

from . import blogger, brand, compose, config, editorial, image, llm, notify, search, sources, stories

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
    # Someone may have committed while we ran (e.g. a file upload): rebase onto it and retry.
    for attempt in range(4):
        if subprocess.run(["git", "push"]).returncode == 0:
            return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        print(f"  ! push rejected, updating from GitHub and retrying ({attempt + 1}/4)")
        subprocess.run(["git", "fetch", "origin", "main"], check=True)
        if subprocess.run(["git", "rebase", "origin/main"]).returncode != 0:
            # both sides changed the same file (usually state.json): keep our newer copy
            subprocess.run(["git", "rebase", "--abort"])
            keep = {f: open(f, "rb").read() for f in paths if os.path.exists(f)}
            subprocess.run(["git", "reset", "--hard", "origin/main"], check=True)
            for f, data in keep.items():
                os.makedirs(os.path.dirname(f) or ".", exist_ok=True)
                with open(f, "wb") as fh:
                    fh.write(data)
            subprocess.run(["git", "add", *paths], check=True)
            if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode != 0:
                subprocess.run(["git", "commit", "-m", message], check=True)
        time.sleep(3 * (attempt + 1))
    print("  ! could not save to GitHub this run; it will be saved next run")
    return None


def pages_changed():
    """Tell the workflow to redeploy GitHub Pages (Web Stories)."""
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write("docs=1\n")


def make_story(st, data, post_url, post_id):
    """Write a Web Story for a published post and push it. Never breaks the run."""
    try:
        art = data["article"]
        changed, url = stories.save(art, data["section"], post_url, data["card_url"], post_id)
        if not config.DRY_RUN and git_push(changed, f"web story: {art.get('slug_en', '')}"):
            pages_changed()
        return url
    except Exception as e:  # noqa: BLE001
        print(f"  ! web story failed: {e}")
        return None


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


def publish_approved(st):
    """Drafts you approved (label 'publish') are published with their English URL."""
    if config.DRY_RUN:
        return
    try:
        bl = blogger.Blogger()
        for post in bl.approved_drafts():
            m = re.search(r"<!--bn-slug:([a-z0-9-]+)-->", post.get("content", ""))
            slug_ = m.group(1) if m and m.group(1) != "news" else ""
            if not slug_:   # older drafts: ask the AI for an English slug from the Hindi headline
                try:
                    res, _ = llm.ask("Write a short English URL slug (lowercase words joined by hyphens, max 6 words, "
                                     "no dates) for this Hindi news headline. Return JSON {\"slug\": \"...\"}.\n"
                                     + post.get("title", ""), temperature=0.0, max_tokens=1500)
                    slug_ = compose.slug(res.get("slug", ""))
                except llm.AIUnavailable:
                    slug_ = ""
            if not slug_ or slug_ == "news":
                slug_ = f"news-{post['id'][-6:]}"
            live = bl.publish_with_slug(post, slug_.replace("-", " "))
            print(f"Published your approved draft: {live.get('url')}")
            data = st.get("pending", {}).pop(post["id"], None)
            if data and live.get("url"):
                make_story(st, data, live["url"], post["id"])
            st["posts"].append({"date": TODAY, "trend": "(approved draft)", "title": live.get("title", ""),
                                "status": "approved", "url": live.get("url", ""), "why": []})
            notify.send("[प्रकाशित] " + live.get("title", "")[:80],
                        f"<p>आपका मंज़ूर किया हुआ ड्राफ्ट प्रकाशित हो गया:</p><p><a href='{live.get('url', '')}'>{live.get('url', '')}</a></p>")
    except Exception as e:  # noqa: BLE001  — never block the hourly run
        print(f"  ! approved-draft publishing failed: {e}")


def main():
    st = load_state()
    cutoff = (NOW - dt.timedelta(days=21)).strftime("%Y-%m-%d")
    st["pending"] = {k: v for k, v in st.get("pending", {}).items() if v.get("date", "") >= cutoff}
    publish_approved(st)
    made_today = sum(1 for p in st["posts"] if p["date"] == TODAY and p.get("status") != "approved")
    if made_today >= config.MAX_PER_DAY:
        print("Daily limit reached; no new articles today.")
        save_state(st)
        git_push([config.STATE_FILE], f"state: {NOW:%Y-%m-%d %H:%M} IST")
        return

    # Groq keys take turns: this run starts with the next key in line (the others are backups)
    keys = config.GROQ_KEYS
    if keys:
        turn = int(st.get("groq_turn", 0)) % len(keys)
        llm.use_groq_keys(keys[turn:] + keys[:turn])
        st["groq_turn"] = turn + 1

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

            # ---- images: our branded card (thumbnail + social preview, committed to the repo)
            #      + an Unsplash photo inside the article (shown from Unsplash's own URL)
            slug = compose.slug(article.get("slug_en") or trend["title"])
            article["slug_en"] = slug
            photo = image.unsplash_photo(article.get("image_query_en"), used=st.setdefault("photos", [])[-200:])
            if photo:
                article["_photo"] = photo
                st["photos"].append(photo["id"])
            nums = [n for n in (article.get("key_numbers") or []) if isinstance(n, dict) and n.get("value")]
            card_rel = f"{config.IMAGE_DIR}/{NOW:%Y/%m}/{slug}-{NOW:%H%M}.jpg"
            brand.share_card(article["title_hi"], p["section"], card_rel, nums[0] if nums else None)
            sha = git_push([card_rel], f"card: {slug}") or "main"
            card_url = f"https://cdn.jsdelivr.net/gh/{config.REPO}@{sha}/{card_rel}"

            html = compose.build_post(article, card_url, srcs, p["section"])
            labels = [p["section"], config.TREND_LABEL]
            story_data = {"article": {k: article.get(k) for k in ("title_hi", "slug_en", "summary", "key_numbers", "_photo")},
                          "section": p["section"], "card_url": card_url, "date": TODAY}
            if config.DRY_RUN:
                os.makedirs("out", exist_ok=True)
                with open(f"out/{slug}.html", "w", encoding="utf-8") as f:
                    f.write(f"<h1>{article['title_hi']}</h1>\n<!-- publish={publish} reasons={reasons} -->\n{html}")
                with open(f"out/{slug}.check.json", "w", encoding="utf-8") as f:
                    json.dump({"check": check, "facts": facts, "rejected_facts": rejected,
                               "sources": [{k: x.get(k) for k in ("source", "title", "url")} for x in srcs]},
                              f, ensure_ascii=False, indent=1)
                try:
                    name, _, doc = stories.build(story_data["article"], p["section"], "https://www.bijlinews.com/", card_url)
                    with open(f"out/story-{name}", "w", encoding="utf-8") as f:
                        f.write(doc)
                except Exception as e:  # noqa: BLE001
                    print(f"  ! web story preview failed: {e}")
                post = {"url": "", "edit_url": f"out/{slug}.html"}
            else:
                post = bl.create(slug.replace("-", " "), article["title_hi"], html, labels, publish)
                if publish and post.get("url"):
                    make_story(st, story_data, post["url"], post.get("id", ""))
                elif post.get("id"):
                    st.setdefault("pending", {})[post["id"]] = story_data   # story is made when you approve it

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
