"""Hourly job: trends -> pick -> research -> write -> fact-check -> image -> publish or draft -> email."""
import datetime as dt
import json
import os
import re
import subprocess
import traceback

from . import blogger, compose, config, editorial, image, notify, sources

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
    """Writer set = articles linked from Google Trends + Hindi Google News.
    Checker set = English Google News (different outlets where possible)."""
    writer, checker = [], []
    for n in trend["news"][:3]:
        writer.append({**n, "text": sources.article_text(n["url"])})
    for n in sources.google_news(query or trend["title"], "hi", 8):
        writer.append(n)
    for n in sources.google_news(query or trend["title"], "en", 10):
        checker.append(n)
    outlets = {sources.outlet_key(s["source"]) for s in writer + checker if s.get("source")}
    return writer[:10], checker[:10], len(outlets)


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

    picks = editorial.triage(trends)
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
            writer_src, checker_src, n_outlets = research(trend, p.get("query"))
            if n_outlets < config.MIN_OUTLETS:
                print(f"  skip: only {n_outlets} outlets")
                continue

            article = editorial.write(trend["title"], p["section"], writer_src)
            if similar_exists(article["title_hi"], recent):
                print("  skip: we already have a similar post")
                continue

            check = editorial.fact_check(article, checker_src)
            if check.get("verdict") == "FIX" and check.get("corrections"):
                article = editorial.revise(article, check)
                check = editorial.fact_check(article, checker_src)
            print(f"  fact-check: {check.get('verdict')} | {check.get('notes','')[:120]}")

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
            publish = not reasons

            # ---- image (committed to the repo and served by jsDelivr)
            slug = compose.slug(article.get("slug_en") or trend["title"])
            img_rel = f"{config.IMAGE_DIR}/{NOW:%Y/%m}/{slug}-{NOW:%H%M}.png"
            image.make_card(article.get("image_text") or article["title_hi"], p["section"], img_rel)
            sha = git_push([img_rel], f"image: {slug}") or "main"
            img_url = f"https://cdn.jsdelivr.net/gh/{config.REPO}@{sha}/{img_rel}"

            html = compose.build_post(article, img_url, writer_src)
            labels = [p["section"], config.TREND_LABEL]
            if config.DRY_RUN:
                os.makedirs("out", exist_ok=True)
                with open(f"out/{slug}.html", "w", encoding="utf-8") as f:
                    f.write(f"<h1>{article['title_hi']}</h1>\n<!-- publish={publish} reasons={reasons} -->\n{html}")
                with open(f"out/{slug}.check.json", "w", encoding="utf-8") as f:
                    json.dump(check, f, ensure_ascii=False, indent=1)
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
