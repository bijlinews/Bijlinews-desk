"""Google Web Stories (AMP) for published articles, served from GitHub Pages (folder docs/).

Each story: cover (photo + headline) -> the 3 summary points -> key numbers -> "read the full article".
Photos are Unsplash photos shown from Unsplash's own URL (their rules), cropped to portrait by URL.
"""
import datetime as dt
import html
import json
import os
import re

from . import brand, config

DOCS = "docs"
DIR = os.path.join(DOCS, "stories")
INDEX = os.path.join(DIR, "index.json")
LOGO = os.path.join(DOCS, "assets", "logo.png")
ACCENT = {k: "#%02x%02x%02x" % v for k, v in brand.ACCENT.items()}


def base_url():
    if config.STORIES_URL:
        return config.STORIES_URL.rstrip("/")
    owner, _, repo = (config.REPO or "bijlinews/Bijlinews-desk").partition("/")
    return f"https://{owner.lower()}.github.io/{repo}"


def _photo(photo, w, h):
    if not photo or not photo.get("raw"):
        return ""
    return f"{photo['raw']}&w={w}&h={h}&fit=crop&crop=entropy&q=80&fm=jpg"


def _clip(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def build(article, section, post_url, card_url, when=None):
    """Return (file_name, html). Never raises for missing optional data."""
    when = when or dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30)))
    e = html.escape
    slug = re.sub(r"[^a-z0-9-]", "", (article.get("slug_en") or "news").lower())[:60] or "news"
    name = f"{when:%Y%m%d}-{slug}.html"
    url = f"{base_url()}/stories/{name}"
    title = _clip(article["title_hi"], 90)
    photo = article.get("_photo")
    bg = _photo(photo, 720, 1280)
    poster = _photo(photo, 640, 853) or card_url
    acc = ACCENT.get(section, "#e1001a")
    logo = f"{base_url()}/assets/logo.png"

    def page(pid, inner, img=None, zoom="zoom-in"):
        layer = (f'<amp-story-grid-layer template="fill"><amp-img src="{e(img)}" width="720" height="1280" '
                 f'layout="responsive" alt="" animate-in="{zoom}" animate-in-duration="9s"></amp-img></amp-story-grid-layer>'
                 if img else '<amp-story-grid-layer template="fill"><div class="plain"></div></amp-story-grid-layer>')
        return (f'<amp-story-page id="{pid}" auto-advance-after="7s">{layer}'
                f'<amp-story-grid-layer template="fill"><div class="shade"></div></amp-story-grid-layer>'
                f'<amp-story-grid-layer template="vertical" class="bottom">{inner}</amp-story-grid-layer></amp-story-page>')

    pages = [page("cover",
                  f'<div class="brand" animate-in="fade-in"><span class="mark">⚡</span>बिजली न्यूज़</div>'
                  f'<span class="chip" animate-in="fade-in">{e(section or "ट्रेंडिंग")}</span>'
                  f'<h1 animate-in="fly-in-bottom">{e(title)}</h1>', bg)]
    for i, b in enumerate((article.get("summary") or [])[:3], 1):
        pages.append(page(f"p{i}", f'<span class="num" animate-in="fade-in">{i}/3</span>'
                                   f'<p class="big" animate-in="fly-in-bottom">{e(_clip(b, 160))}</p>', bg,
                          "pan-left" if i % 2 else "pan-right"))
    nums = [n for n in (article.get("key_numbers") or []) if isinstance(n, dict) and n.get("value")][:3]
    if nums:
        tiles = "".join(f'<div class="tile" animate-in="whoosh-in-right" animate-in-delay="{0.2 * k:.1f}s">'
                        f'<b>{e(_clip(n["value"], 18))}</b><span>{e(_clip(n.get("label", ""), 40))}</span></div>'
                        for k, n in enumerate(nums))
        pages.append(page("nums", f'<h2 animate-in="fade-in">अहम आँकड़े</h2>{tiles}', None))
    pages.append(f'<amp-story-page id="end">'
                 f'<amp-story-grid-layer template="fill"><div class="plain"></div></amp-story-grid-layer>'
                 f'<amp-story-grid-layer template="vertical" class="center">'
                 f'<div class="brand big2"><span class="mark">⚡</span>बिजली न्यूज़</div>'
                 f'<p class="tag">खबर भी, वजह भी</p><p class="big">{e(title)}</p></amp-story-grid-layer>'
                 f'<amp-story-page-outlink layout="nodisplay" cta-image="{e(logo)}">'
                 f'<a href="{e(post_url)}">पूरी खबर पढ़ें</a></amp-story-page-outlink></amp-story-page>')

    css = """
amp-story{font-family:'Mukta',sans-serif;color:#fff}
.shade{background:linear-gradient(180deg,rgba(0,0,0,.15) 0%,rgba(0,0,0,.25) 45%,rgba(0,0,0,.88) 100%)}
.plain{background:linear-gradient(160deg,ACC 0%,#140306 75%)}
.bottom{align-content:end;padding:28px 22px 56px}
.center{align-content:center;justify-items:center;text-align:center;padding:30px}
.brand{display:flex;align-items:center;gap:8px;font-weight:800;font-size:20px}
.brand.big2{font-size:34px}
.mark{display:inline-flex;width:34px;height:34px;border-radius:50%;background:#e1001a;align-items:center;justify-content:center;font-size:18px}
.chip{justify-self:start;background:#ffc107;color:#111;font-weight:800;font-size:15px;padding:3px 10px;border-radius:6px;margin-top:10px}
h1{font-size:31px;line-height:1.3;font-weight:800;margin:10px 0 0}
h2{font-size:28px;font-weight:800;margin:0 0 12px}
.big{font-size:25px;line-height:1.45;font-weight:700;margin:6px 0 0}
.num{font-weight:800;color:#ffc107;font-size:18px}
.tag{color:#ffc107;font-weight:700;margin:6px 0 18px}
.tile{background:#fff;color:#111;border-left:8px solid ACC;border-radius:12px;padding:14px 16px;margin:0 0 12px}
.tile b{display:block;font-size:30px;color:ACC;line-height:1.2}
.tile span{font-size:17px}
""".replace("ACC", acc)
    ld = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": title, "inLanguage": "hi-IN",
          "datePublished": when.isoformat(), "image": [poster], "mainEntityOfPage": url,
          "publisher": {"@type": "NewsMediaOrganization", "name": "बिजली न्यूज़", "logo": {"@type": "ImageObject", "url": logo}}}
    doc = f"""<!doctype html>
<html ⚡ lang="hi">
<head>
<meta charset="utf-8">
<title>{e(title)} | बिजली न्यूज़</title>
<link rel="canonical" href="{e(url)}">
<meta name="viewport" content="width=device-width">
<meta name="description" content="{e(_clip(' '.join(article.get('summary') or []), 155))}">
<script async src="https://cdn.ampproject.org/v0.js"></script>
<script async custom-element="amp-story" src="https://cdn.ampproject.org/v0/amp-story-1.0.js"></script>
<link rel="preconnect" href="https://fonts.gstatic.com">
<link href="https://fonts.googleapis.com/css2?family=Mukta:wght@400;700;800&display=swap" rel="stylesheet">
<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False).replace("</", "<\\/")}</script>
<style amp-boilerplate>body{{-webkit-animation:-amp-start 8s steps(1,end) 0s 1 normal both;-moz-animation:-amp-start 8s steps(1,end) 0s 1 normal both;-ms-animation:-amp-start 8s steps(1,end) 0s 1 normal both;animation:-amp-start 8s steps(1,end) 0s 1 normal both}}@-webkit-keyframes -amp-start{{from{{visibility:hidden}}to{{visibility:visible}}}}@-moz-keyframes -amp-start{{from{{visibility:hidden}}to{{visibility:visible}}}}@-ms-keyframes -amp-start{{from{{visibility:hidden}}to{{visibility:visible}}}}@-o-keyframes -amp-start{{from{{visibility:hidden}}to{{visibility:visible}}}}@keyframes -amp-start{{from{{visibility:hidden}}to{{visibility:visible}}}}</style><noscript><style amp-boilerplate>body{{-webkit-animation:none;-moz-animation:none;-ms-animation:none;animation:none}}</style></noscript>
<style amp-custom>{css}</style>
</head>
<body>
<amp-story standalone title="{e(title)}" publisher="बिजली न्यूज़" publisher-logo-src="{e(logo)}" poster-portrait-src="{e(poster)}">
{''.join(pages)}
</amp-story>
</body>
</html>
"""
    return name, url, doc


def save(article, section, post_url, card_url, post_id=""):
    """Write the story + update the index used by the website. Returns list of changed paths."""
    name, url, doc = build(article, section, post_url, card_url)
    os.makedirs(DIR, exist_ok=True)
    with open(os.path.join(DIR, name), "w", encoding="utf-8") as f:
        f.write(doc)
    changed = [os.path.join(DIR, name)]
    if not os.path.exists(LOGO):
        brand.logo(LOGO)
        changed.append(LOGO)
    try:
        with open(INDEX, encoding="utf-8") as f:
            idx = json.load(f)
    except (FileNotFoundError, ValueError):
        idx = []
    idx = [s for s in idx if s.get("story") != url and s.get("post") != post_url]
    idx.insert(0, {"title": article["title_hi"], "story": url, "post": post_url, "id": post_id,
                   "poster": _photo(article.get("_photo"), 480, 853) or card_url, "section": section,
                   "date": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    idx = idx[:60]
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=0)
    changed.append(INDEX)
    _write_listing(idx)
    changed.append(os.path.join(DIR, "index.html"))
    nojekyll = os.path.join(DOCS, ".nojekyll")
    if not os.path.exists(nojekyll):
        open(nojekyll, "w").close()
        changed.append(nojekyll)
    print(f"  web story: {url}")
    return changed, url


def _write_listing(idx):
    e = html.escape
    cards = "".join(f'<a href="{e(s["story"])}"><img src="{e(s["poster"])}" alt="" loading="lazy"><b>{e(s["title"])}</b></a>'
                    for s in idx)
    doc = f"""<!doctype html><html lang="hi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>वेब स्टोरीज़ | बिजली न्यूज़</title><link rel="canonical" href="{base_url()}/stories/">
<style>body{{margin:0;font-family:Mukta,system-ui,sans-serif;background:#111;color:#fff}}h1{{margin:0;padding:18px 16px;background:#e1001a}}
main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;padding:16px}}
a{{position:relative;display:block;aspect-ratio:9/15;border-radius:10px;overflow:hidden;color:#fff;text-decoration:none;background:#222}}
img{{width:100%;height:100%;object-fit:cover}}b{{position:absolute;left:0;right:0;bottom:0;padding:40px 10px 10px;background:linear-gradient(transparent,#000);font-size:15px;line-height:1.4}}</style>
</head><body><h1>⚡ बिजली न्यूज़ वेब स्टोरीज़</h1><main>{cards}</main>
<p style="padding:0 16px 24px"><a href="https://www.bijlinews.com/" style="display:inline;aspect-ratio:auto;background:none;color:#ffc107">bijlinews.com पर सभी खबरें →</a></p></body></html>
"""
    with open(os.path.join(DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(doc)
