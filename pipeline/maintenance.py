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

import requests

from . import blogger, brand, compose, config, descriptions, image, llm

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
    """Every post (live, draft, scheduled). Guards against Blogger repeating page tokens."""
    out, seen_ids = [], set()
    for status in ("live", "draft", "scheduled"):
        token, seen_tokens = None, set()
        for page in range(60):                      # hard cap: 60 x 100 posts per status
            params = {"status": status, "fetchBodies": "true", "maxResults": 100, "view": "ADMIN"}
            if token:
                params["pageToken"] = token
            r = requests.get(bl.base, headers=bl.h, params=params, timeout=90)
            r.raise_for_status()
            j = r.json()
            items = j.get("items", [])
            new = [p for p in items if p["id"] not in seen_ids]
            for p in new:
                p["_status"] = status
                seen_ids.add(p["id"])
                out.append(p)
            token = j.get("nextPageToken")
            print(f"  {status}: page {page + 1}, {len(items)} posts ({len(new)} new)", flush=True)
            if not token or not new or token in seen_tokens:
                break
            seen_tokens.add(token)
    print(f"  total: {len(out)} posts", flush=True)
    return out


def find_duplicates(titles, threshold=0.8):
    """Near-duplicate titles by word overlap, using an index so big blogs stay fast."""
    words = {i: set(t.split()) for i, t in titles if t}
    df = {}
    for ws in words.values():
        for w in ws:
            df[w] = df.get(w, 0) + 1
    limit = max(20, int(0.05 * len(words)))          # ignore very common words (में, की, ...)
    index = {}
    for i, ws in words.items():
        for w in ws:
            if df[w] <= limit:
                index.setdefault(w, []).append(i)
    out = {}
    same = {}
    for i, t in titles:                               # identical titles (after cleanup)
        if t:
            same.setdefault(t, []).append(i)
    for ids in same.values():
        for i in ids:
            out[i] = [j for j in ids if j != i]
    for i, ws in words.items():
        cand = {}
        for w in ws:
            for j in index.get(w, ()):
                if j != i:
                    cand[j] = cand.get(j, 0) + 1
        for j, shared in cand.items():
            union = len(ws | words[j])
            if union and len(ws & words[j]) / union >= threshold and j not in out.get(i, []):
                out.setdefault(i, []).append(j)
    return out


def audit():
    bl = blogger.Blogger()
    posts = all_posts(bl)
    rows = []
    norm = lambda t: re.sub(r"[^\w]+", " ", (t or "").lower()).strip()
    dups = find_duplicates([(p["id"], norm(p.get("title"))) for p in posts])
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
        dup = dups.get(p["id"], [])
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
        acts = r["suggest"]          # only real suggestions (e.g. a missing label has no action)
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
                         temperature=0.0, max_tokens=1500)
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
        m = re.match(r"^\s*(draft|fix-url|add-image|auto-label)\s+(\d{6,})\s*$", ln)
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
            elif act == "auto-label":
                if post.get("labels"):
                    log.append(f"- auto-label {pid}: skipped (already has labels)")
                    continue
                sections = ", ".join(config.SECTIONS)
                try:
                    res, _ = llm.ask(f"Pick the ONE best section for this Hindi news/article headline from: [{sections}]. "
                                     'Reply JSON {"section": "..."}.\n' + post.get("title", ""), temperature=0.0, max_tokens=1500)
                    sec = res.get("section", "")
                except llm.AIUnavailable:
                    sec = ""
                if sec not in config.SECTIONS:
                    log.append(f"- auto-label {pid}: skipped (no clear section)")
                    continue
                requests.patch(f"{bl.base}/{pid}", headers=bl.h, timeout=60, json={"labels": [sec]}).raise_for_status()
                log.append(f"- auto-label {pid}: label '{sec}' added")
            elif act == "add-image":
                body = post.get("content", "")
                if re.search(r"<img\b", body, re.I):
                    log.append(f"- add-image {pid}: skipped (already has an image)")
                    continue
                try:
                    res, _ = llm.ask("Give 2-4 English words for a GENERIC stock photo (objects or places only, no people "
                                     'names, brands or parties) for this Hindi headline. JSON {"q": "..."}.\n' + post.get("title", ""),
                                     temperature=0.0, max_tokens=1500)
                    q = res.get("q", "")
                except llm.AIUnavailable:
                    q = ""
                photo = image.unsplash_photo(q, used=st_photos) if q else None
                section = next((l for l in post.get("labels", []) if l in config.SECTIONS), "")
                slug = compose.slug(_slug_for(post))
                card_rel = f"{config.IMAGE_DIR}/fix/{pid}-{slug}.jpg"
                branded = bool(photo and brand.branded_photo(photo["url"], section, card_rel))
                if not branded:
                    brand.share_card(post.get("title", ""), section, card_rel)
                sha = push([card_rel], f"card: fix {pid}") if push else None
                if not sha:
                    log.append(f"- add-image {pid}: could not save the card image, skipped")
                    continue
                card_url = f"https://cdn.jsdelivr.net/gh/{config.REPO}@{sha}/{card_rel}"
                e = html.escape
                top = ""
                if branded:
                    fig = (f'<div class="separator bn-branded"><img src="{e(card_url)}" alt="{e(post.get("title", ""))}" '
                           f'width="1200" height="675" /></div>\n{compose._caption(photo)}\n')
                else:
                    fig = (f'<div class="separator bn-cardimg"><img src="{e(card_url)}" alt="{e(post.get("title", ""))}" '
                           f'width="1200" height="675" /></div>\n')
                if photo:
                    st_photos.append(photo["id"])
                requests.patch(f"{bl.base}/{pid}", headers=bl.h, timeout=60,
                               json={"content": top + fig + body}).raise_for_status()
                log.append(f"- add-image {pid}: added {'branded Unsplash photo' if branded else 'branded card'}")
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


UNSPLASH_IMG = re.compile(r'<img\b[^>]*?src="(https://images\.unsplash\.com/[^"]+)"[^>]*>', re.I)


def rebrand_all(push):
    """Every post that still shows a photo from images.unsplash.com gets our branded copy (hosted on GitHub)."""
    bl = blogger.Blogger()
    posts = [p for p in all_posts(bl) if UNSPLASH_IMG.search(p.get("content", ""))]
    print(f"{len(posts)} post(s) still use images.unsplash.com")
    log = []
    for post in posts:
        pid, body = post["id"], post.get("content", "")
        try:
            src = html.unescape(UNSPLASH_IMG.search(body).group(1))
            base = src.split("?")[0]
            q = dict(kv.split("=", 1) for kv in src.split("?", 1)[1].split("&") if "=" in kv) if "?" in src else {}
            dl = base + ("?ixid=" + q["ixid"] + "&" if "ixid" in q else "?") + "w=1600&q=85&fm=jpg"
            section = next((l for l in post.get("labels", []) if l in config.SECTIONS), "")
            rel = f"{config.IMAGE_DIR}/rebrand/{pid}.jpg"
            if not brand.branded_photo(dl, section, rel):
                log.append(f"- rebrand {pid}: photo download failed, skipped")
                continue
            sha = push([rel], f"image: rebrand {pid}")
            if not sha:
                log.append(f"- rebrand {pid}: could not save image, skipped")
                continue
            url = f"https://cdn.jsdelivr.net/gh/{config.REPO}@{sha}/{rel}"
            new = re.sub(r'<div class="bn-share" style="display:none">.*?</div>\s*', "", body, count=1, flags=re.S)
            m = UNSPLASH_IMG.search(new)
            tag = m.group(0).replace(m.group(1), html.escape(url))
            new = new[:m.start()] + tag + new[m.end():]
            # the wrapper becomes "bn-branded" so the theme doesn't add a second badge
            head, tail = new[:m.start()], new[m.start():]
            k = head.rfind('<div class="separator')
            if k >= 0 and "</div>" not in head[k:]:
                close = head.find(">", k)
                head = head[:k] + '<div class="separator bn-branded">' + head[close + 1:]
            new = head + tail
            requests.patch(f"{bl.base}/{pid}", headers=bl.h, timeout=60, json={"content": new}).raise_for_status()
            log.append(f"- rebrand {pid}: {post.get('title', '')[:60]} -> branded photo")
        except Exception as ex:  # noqa: BLE001
            log.append(f"- rebrand {pid}: FAILED: {str(ex)[:200]}")
    stamp = dt.datetime.now(IST).strftime("%Y-%m-%d %H:%M")
    os.makedirs(DIR, exist_ok=True)
    with open(RESULTS, "a", encoding="utf-8") as f:
        f.write(f"\n## {stamp} IST (rebrand)\n" + "\n".join(log or ["- nothing to do"]) + "\n")
    print("\n".join(log))
    return [RESULTS]


NUM_RE = re.compile(r"\d[\d,.]*\d|\d")


def _nums(t):
    return {n.replace(",", "") for n in NUM_RE.findall(t or "")}


def _describe(post, text):
    """One Hindi sentence (110-155 chars) from the post's own text. Every number must be in the post."""
    try:
        res, _ = llm.ask(
            "Write the Google/WhatsApp search description for this Hindi news article: ONE complete Hindi sentence, "
            "100-145 characters (never more than 145), with the single most important fact (who/what/how much). Use only facts from the "
            "text. No question, no 'जानें', no 'पूरी खबर', no emoji. Return ONLY JSON: {\"description\": \"...\"}\n\n"
            f"TITLE: {post.get('title', '')}\nTEXT: {text[:3000]}", temperature=0.2, max_tokens=1500)
        desc = descriptions.clean((res or {}).get("description", ""))
    except llm.AIUnavailable:
        return ""
    if len(desc) < 60 or not _nums(desc) <= _nums(post.get("title", "") + " " + text):
        return ""
    return desc


def describe_all(preview, push):
    """Ready-made Search descriptions for live posts that aren't in state/descriptions.json yet, newest first.
    The Description Filler extension types them into Blogger. DESC_COUNT limits how many per run (0 = all)."""
    limit = min(500, max(0, int(os.getenv("DESC_COUNT") or "0")))
    bl = blogger.Blogger()
    items = descriptions.load()
    have = {str(i.get("post_id")) for i in items}
    posts = [p for p in all_posts(bl) if p["_status"] == "live" and p["id"] not in have]
    posts.sort(key=lambda p: p.get("published", ""), reverse=True)
    if limit > 0:
        posts = posts[:limit]
    log = []
    for post in posts:
        pid, body = post["id"], post.get("content", "")
        desc = _describe(post, _text(body))
        if not desc:   # fall back to the first '30 सेकंड' point of bot posts
            m = re.search(r'<div class="bn-summary">.*?<li>(.*?)</li>', body, flags=re.S)
            desc = descriptions.clean(html.unescape(_text(m.group(1)))) if m else ""
        if len(desc) < 40:
            log.append(f"- describe {pid}: no description (skipped) {post.get('title', '')[:50]}")
            continue
        edit = f"https://www.blogger.com/blog/post/edit/{config.BLOG_ID}/{pid}"
        items = descriptions.add(items, pid, post.get("title", ""), post.get("url", ""), edit, desc)
        log.append(f"- describe {pid}: {desc}")
        print(log[-1], flush=True)
    stamp = dt.datetime.now(IST).strftime("%Y-%m-%d %H:%M")
    os.makedirs(DIR, exist_ok=True)
    with open(RESULTS, "a", encoding="utf-8") as f:
        f.write(f"\n## {stamp} IST (describe{' preview' if preview else ''})\n" + "\n".join(log or ["- nothing to do"]) + "\n")
    print(f"{len(log)} post(s) handled")
    if preview:
        return [RESULTS]
    descriptions.save(items)
    return [RESULTS, descriptions.PATH]


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
    elif mode == "rebrand":
        paths = rebrand_all(push=git_push)
        git_push(paths, f"maintenance: rebrand {NOW:%Y-%m-%d %H:%M}")
    elif mode in ("describe", "describe-preview"):
        paths = describe_all(preview=(mode == "describe-preview"), push=git_push)
        git_push(paths, f"maintenance: {mode} {NOW:%Y-%m-%d %H:%M}")
    elif mode in ("apply", "preview"):
        paths, _ = apply(preview=(mode == "preview"), push=git_push)
        if paths:
            git_push(paths, f"maintenance: apply {NOW:%Y-%m-%d %H:%M}")
    else:
        raise SystemExit(f"unknown mode {mode}")


if __name__ == "__main__":
    main()
