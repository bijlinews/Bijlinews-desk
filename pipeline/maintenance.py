"""Clean-up of old posts. Two modes (GitHub Actions -> "Bijli maintenance" -> Run workflow):

audit  : READ-ONLY. Scans every post and writes maintenance/report.html + maintenance/actions.txt.
         Every suggested action in actions.txt starts with '#' (= off). Nothing on the blog changes.
apply  : Runs only the lines in maintenance/actions.txt that you un-commented (removed the '#'):
           draft <postId>      move a post back to draft (can be undone: just publish it again)
           fix-url <postId>    re-publish at an English address (same date, same content) and move the
                               old copy to draft; the old->new redirect is listed for Blogger settings
           add-image <postId>  add our branded card + an Unsplash photo to a post that has no image
preview: same as apply, but only prints what it would do.
"""
import datetime as dt
import html
import json
import os
import re
import sys
from difflib import SequenceMatcher

import requests

from . import blogger, brand, compose, config, image, llm

DIR = "maintenance"
ACTIONS = os.path.join(DIR, "actions.txt")
REPORT = os.path.join(DIR, "report.html")
RESULTS = os.path.join(DIR, "results.md")
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
BOT_FIX_DATE = "2026-11-17"   # drafts the bot made before the fact-check fixes


def _text(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h or "")).strip()


def _path(url):
    m = re.match(r"https?://[^/]+(/.*)", url or "")
    return m.group(1) if m else ""


def bad_url(url):
    """True for addresses like /2026/11/20-145.html or /2026/11/blog-post_17.html."""
    m = re.search(r"/([^/]+)\.html$", url or "")
    if not m:
        return False
    s = m.group(1)
    return not re.search(r"[a-z]{3,}", s) or s.startswith("blog-post")


def all_posts(bl):
    out = []
    for status in ("live", "draft", "scheduled"):
        token = None
        while True:
            params = {"status": status, "fetchBodies": "true", "maxResults": 100, "view": "ADMIN"}
            if token:
                params["pageToken"] = token
            r = requests.get(bl.base, headers=bl.h, params=params, timeout=90)
            r.raise_for_status()
            j = r.json()
            for p in j.get("items", []):
                p["_status"] = status
                out.append(p)
            token = j.get("nextPageToken")
            if not token:
                break
    return out


def audit():
    bl = blogger.Blogger()
    posts = all_posts(bl)
    rows = []
    norm = lambda t: re.sub(r"[^\w]+", " ", (t or "").lower()).strip()
    titles = [(p["id"], norm(p.get("title"))) for p in posts]
    for p in posts:
        body = p.get("content", "")
        words = len(_text(body).split())
        has_img = bool(re.search(r"<img\b", body, re.I))
        flags, suggest = [], []
        if p["_status"] == "live" and bad_url(p.get("url")):
            flags.append("खराब URL")
            suggest.append("fix-url")
        if words < 150:
            flags.append(f"छोटा ({words} शब्द)")
        if not has_img:
            flags.append("फोटो नहीं")
            suggest.append("add-image")
        if not p.get("labels"):
            flags.append("लेबल नहीं")
        dup = [i for i, t in titles if i != p["id"] and t and SequenceMatcher(None, t, norm(p.get("title"))).ratio() > 0.85]
        if dup:
            flags.append("डुप्लिकेट? " + ", ".join(dup[:2]))
        made_by_bot = 'class="bn-ai"' in body
        if p["_status"] == "draft" and made_by_bot and (p.get("published") or p.get("updated", ""))[:10] <= BOT_FIX_DATE \
                and "bn-slug" not in body:
            flags.append("बॉट का पुराना ड्राफ्ट (fact-check सुधार से पहले)")
        if p["_status"] == "live" and (words < 120 or any(f.startswith("डुप्लिकेट") for f in flags)):
            suggest.insert(0, "draft")
        if p["_status"] != "live":
            suggest = []          # drafts aren't public: listed only, delete them in Blogger if unwanted
        if flags:
            rows.append({"id": p["id"], "status": p["_status"], "title": p.get("title", ""), "url": p.get("url", ""),
                         "date": (p.get("published") or "")[:10], "words": words, "flags": flags, "suggest": suggest})
    os.makedirs(DIR, exist_ok=True)
    e = html.escape
    trs = "".join(
        f"<tr><td>{e(r['status'])}</td><td>{e(r['date'])}</td><td><a href='{e(r['url'] or '#')}'>{e(r['title'][:90])}</a>"
        f"<br><small>{e(r['id'])}</small></td><td>{e(' · '.join(r['flags']))}</td><td>{e(', '.join(r['suggest']) or '-')}</td></tr>"
        for r in rows)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(f"<!doctype html><meta charset='utf-8'><title>Bijli audit</title><h2>{len(posts)} posts scanned, "
                f"{len(rows)} need attention</h2><table border=1 cellpadding=6 style='border-collapse:collapse;font-family:sans-serif'>"
                f"<tr><th>status</th><th>date</th><th>post</th><th>problems</th><th>suggested</th></tr>{trs}</table>")
    lines = ["# Remove the '#' at the start of a line to run that action, then run the workflow in 'apply' mode.",
             "# draft = move back to draft (undo: publish again)  | fix-url = English address + redirect",
             "# add-image = add branded card + Unsplash photo. Lines starting with # are ignored.", ""]
    for r in rows:
        lines.append(f"# ---- {r['title'][:80]}  [{r['status']}, {', '.join(r['flags'])}]")
        acts = r["suggest"] or (["draft"] if r["status"] == "live" else [])
        if r["status"] != "live":
            lines.append("#   (draft: not public. Delete it in Blogger if you don't want it.)")
        for a in acts:
            lines.append(f"# {a} {r['id']}")
        lines.append("")
    with open(ACTIONS, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Audit: {len(posts)} posts, {len(rows)} flagged. See {REPORT} and {ACTIONS}")
    return [REPORT, ACTIONS], len(posts), len(rows)


def _slug_for(post):
    m = re.search(r"<!--bn-slug:([a-z0-9-]+)-->", post.get("content", ""))
    if m and m.group(1) != "news":
        return m.group(1)
    try:
        res, _ = llm.ask("Write a short English URL slug (lowercase words joined by hyphens, max 6 words, no dates) "
                         'for this Hindi news headline. Return JSON {"slug": "..."}.\n' + post.get("title", ""),
                         temperature=0.0, max_tokens=300)
        s = compose.slug(res.get("slug", ""))
        if s and s != "news":
            return s
    except llm.AIUnavailable:
        pass
    return f"news-{post['id'][-6:]}"


def apply(preview=False, push=None):
    try:
        with open(ACTIONS, encoding="utf-8") as f:
            raw = f.read().splitlines()
    except FileNotFoundError:
        print("No maintenance/actions.txt - run the audit first.")
        return [], ""
    todo = []
    for ln in raw:
        m = re.match(r"^\s*(draft|fix-url|add-image)\s+(\d{6,})\s*$", ln)
        if m:
            todo.append((m.group(1), m.group(2)))
    if not todo:
        print("Nothing to do: no un-commented lines in maintenance/actions.txt")
        return [], ""
    print(f"{len(todo)} action(s): {todo}")
    if preview:
        return [], ""
    bl = blogger.Blogger()
    log, redirects, changed = [], [], []
    st_photos = []
    for act, pid in todo:
        try:
            r = requests.get(f"{bl.base}/{pid}", headers=bl.h, params={"view": "ADMIN"}, timeout=60)
            r.raise_for_status()
            post = r.json()
            if act == "draft":
                if post.get("status") == "DRAFT":
                    log.append(f"- draft {pid}: already a draft")
                    continue
                requests.post(f"{bl.base}/{pid}/revert", headers=bl.h, timeout=60).raise_for_status()
                log.append(f"- draft {pid}: moved to draft ({post.get('title', '')[:60]})")
            elif act == "fix-url":
                if post.get("status") != "LIVE" or not bad_url(post.get("url")):
                    log.append(f"- fix-url {pid}: skipped (not live, or address already fine)")
                    continue
                slug = _slug_for(post)
                hindi = post.get("title", "")
                new = requests.post(bl.base, headers=bl.h, params={"isDraft": "true"}, timeout=60, json={
                    "title": slug.replace("-", " "), "content": post.get("content", ""), "labels": post.get("labels", [])})
                new.raise_for_status()
                new = new.json()
                pub = requests.post(f"{bl.base}/{new['id']}/publish", headers=bl.h, timeout=60,
                                    params={"publishDate": post.get("published")})
                pub.raise_for_status()
                fin = requests.patch(f"{bl.base}/{new['id']}", headers=bl.h, timeout=60, json={"title": hindi})
                fin.raise_for_status()
                new_url = fin.json().get("url", "")
                requests.post(f"{bl.base}/{pid}/revert", headers=bl.h, timeout=60).raise_for_status()
                redirects.append((_path(post.get("url")), _path(new_url)))
                log.append(f"- fix-url {pid}: {post.get('url')} -> {new_url} (old copy moved to draft)")
            elif act == "add-image":
                body = post.get("content", "")
                if re.search(r"<img\b", body, re.I):
                    log.append(f"- add-image {pid}: skipped (already has an image)")
                    continue
                try:
                    res, _ = llm.ask("Give 2-4 English words for a GENERIC stock photo (objects or places only, no people "
                                     'names, brands or parties) for this Hindi headline. JSON {"q": "..."}.\n' + post.get("title", ""),
                                     temperature=0.0, max_tokens=200)
                    q = res.get("q", "")
                except llm.AIUnavailable:
                    q = ""
                photo = image.unsplash_photo(q, used=st_photos) if q else None
                section = next((l for l in post.get("labels", []) if l in config.SECTIONS), "")
                slug = compose.slug(_slug_for(post))
                card_rel = f"{config.IMAGE_DIR}/fix/{pid}-{slug}.jpg"
                brand.share_card(post.get("title", ""), section, card_rel)
                sha = push([card_rel], f"card: fix {pid}") if push else None
                if not sha:
                    log.append(f"- add-image {pid}: could not save the card image, skipped")
                    continue
                card_url = f"https://cdn.jsdelivr.net/gh/{config.REPO}@{sha}/{card_rel}"
                e = html.escape
                top = (f'<div class="bn-share" style="display:none"><img src="{e(card_url)}" alt="{e(post.get("title", ""))}" '
                       f'width="1200" height="675" /></div>\n') if photo else ""
                fig = (f'<div class="separator bn-photo" data-section="{e(section)}"><img src="{e(photo["url"])}" '
                       f'alt="{e(post.get("title", ""))}" width="1200" height="675" /></div>\n{compose._caption(photo)}\n') if photo else \
                      (f'<div class="separator bn-cardimg"><img src="{e(card_url)}" alt="{e(post.get("title", ""))}" '
                       f'width="1200" height="675" /></div>\n')
                if photo:
                    st_photos.append(photo["id"])
                requests.patch(f"{bl.base}/{pid}", headers=bl.h, timeout=60,
                               json={"content": top + fig + body}).raise_for_status()
                log.append(f"- add-image {pid}: added {'card + Unsplash photo' if photo else 'branded card'}")
        except Exception as ex:  # noqa: BLE001  - one bad post must not stop the rest
            log.append(f"- {act} {pid}: FAILED: {str(ex)[:200]}")
    # mark processed lines as done so they don't run twice
    done = {f"{a} {p}" for a, p in todo}
    stamp = dt.datetime.now(IST).strftime("%Y-%m-%d %H:%M")
    with open(ACTIONS, "w", encoding="utf-8") as f:
        f.write("\n".join(f"# done {stamp}: {ln.strip()}" if ln.strip() in done else ln for ln in raw) + "\n")
    with open(RESULTS, "a", encoding="utf-8") as f:
        f.write(f"\n## {stamp} IST\n" + "\n".join(log) + "\n")
        if redirects:
            f.write("\n### Add these in Blogger -> Settings -> Errors and redirects -> Custom redirects (Permanent: ON)\n")
            f.write("\n".join(f"- From `{a}` To `{b}`" for a, b in redirects) + "\n")
    print("\n".join(log))
    if redirects:
        print("REDIRECTS:\n" + "\n".join(f"{a} -> {b}" for a, b in redirects))
    return [ACTIONS, RESULTS], json.dumps(redirects)


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "audit").strip().lower()
    from .run import git_push, NOW
    if mode == "audit":
        paths, n, k = audit()
        git_push(paths, f"maintenance: audit {NOW:%Y-%m-%d %H:%M}")
        from . import notify
        notify.send(f"[Bijli] Audit: {k} of {n} posts need attention",
                    "<p>GitHub repo -> maintenance/report.html (open with 'Raw' or download) and maintenance/actions.txt.</p>"
                    "<p>Remove the # from the actions you want, commit, then run 'Bijli maintenance' in apply mode.</p>")
    elif mode in ("apply", "preview"):
        paths, _ = apply(preview=(mode == "preview"), push=git_push)
        if paths:
            git_push(paths, f"maintenance: apply {NOW:%Y-%m-%d %H:%M}")
    else:
        raise SystemExit(f"unknown mode {mode}")


if __name__ == "__main__":
    main()
