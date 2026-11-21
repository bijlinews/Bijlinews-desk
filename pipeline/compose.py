"""Turn the AI output into the post HTML the theme expects."""
import html
import json
import re

ALLOWED = {"p", "h2", "h3", "ul", "ol", "li", "strong", "em", "b", "i", "br", "blockquote"}


def clean_html(s):
    s = re.sub(r"<(script|style|iframe)[^>]*>.*?</\1>", "", s or "", flags=re.S | re.I)
    s = re.sub(r"\son\w+\s*=\s*(['\"]).*?\1", "", s)               # no inline JS
    s = re.sub(r"<a\b[^>]*>(.*?)</a>", r"\1", s, flags=re.S | re.I)  # writer may not add links

    def tag(m):
        name = m.group(2).lower()
        return f"<{m.group(1)}{name}>" if name in ALLOWED else ""
    return re.sub(r"<(/?)([a-zA-Z0-9]+)[^>]*>", tag, s).strip()


def _caption(photo):
    if not photo:
        return ""
    e = html.escape
    return ('<p class="bn-caption" style="font-size:13px;color:#888;text-align:center;margin-top:6px">'
            f'प्रतीकात्मक चित्र · फोटो: <a href="{e(photo["credit_url"])}" rel="nofollow noopener" target="_blank">{e(photo["credit_name"])}</a>'
            f' / <a href="{e(photo["unsplash_url"])}" rel="nofollow noopener" target="_blank">Unsplash</a></p>')


def _numbers(article):
    e = html.escape
    tiles = [n for n in (article.get("key_numbers") or []) if isinstance(n, dict) and n.get("value")][:3]
    if not tiles:
        return ""
    return '<div class="bn-nums">' + "".join(
        f'<div class="bn-num"><b>{e(str(n["value"]))}</b><span>{e(str(n.get("label", "")))}</span></div>' for n in tiles) + "</div>"


def _timeline(article):
    e = html.escape
    items = [t for t in (article.get("timeline") or []) if isinstance(t, dict) and t.get("what")][:5]
    if len(items) < 3:
        return ""
    lis = "".join(f'<li><b>{e(str(t.get("when", "")))}</b> {e(str(t["what"]))}</li>' for t in items)
    return f'<div class="bn-timeline"><h2>घटनाक्रम</h2><ol>{lis}</ol></div>'


def _faq(article):
    e = html.escape
    qa = [f for f in (article.get("faq") or []) if isinstance(f, dict) and f.get("q") and f.get("a")][:3]
    if not qa:
        return ""
    items = "".join(f'<details><summary>{e(str(f["q"]))}</summary><p>{e(str(f["a"]))}</p></details>' for f in qa)
    ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": str(f["q"]), "acceptedAnswer": {"@type": "Answer", "text": str(f["a"])}} for f in qa]}
    ld_s = json.dumps(ld, ensure_ascii=True).replace("</", "<\\/")
    return (f'<div class="bn-faq"><h2>लोग पूछ रहे हैं</h2>{items}</div>\n'
            f'<script type="application/ld+json">{ld_s}</script>')


def _sensitive_note(article):
    if not article.get("_sensitive"):
        return ""
    return ('<p class="bn-note-sensitive" style="font-size:14.5px;line-height:1.6;border-left:4px solid #e1001a;'
            'background:#fff3f4;padding:10px 14px;border-radius:0 8px 8px 0">यदि इस खबर से किसी को कोई आपत्ति है, '
            'तो कृपया हमें <a href="mailto:hello@bijlinews.com">hello@bijlinews.com</a> पर ईमेल करें। '
            'जाँच के बाद हम इस खबर को सुधारेंगे या हटा देंगे।</p>\n')


def build_post(article, card_url, sources, section=""):
    """card_url: our branded card (first image = thumbnail and social preview).
    The Unsplash photo (article['_photo']) is shown in the article from Unsplash's own URL."""
    e = html.escape
    bullets = "".join(f"<li>{e(b)}</li>" for b in article["summary"][:3])
    used = [s for s in sources if s.get("text")] or sources[:5]
    seen, links = set(), []
    for s in used:
        if s["source"] in seen or not s.get("url"):
            continue
        seen.add(s["source"])
        links.append(f'<a class="bn-chip" href="{e(s["url"])}" rel="nofollow noopener" target="_blank">{e(s["source"])}</a>')
    photo = article.get("_photo")
    alt = e(article.get("image_alt") or article["title_hi"])
    if photo and article.get("_branded_url"):   # our branded copy of the Unsplash photo (main + preview image)
        share = ""
        figure = (f'<div class="separator bn-branded"><img src="{e(article["_branded_url"])}" alt="{alt}" '
                  f'width="1200" height="675" /></div>\n{_caption(photo)}')
    elif photo:
        share = (f'<div class="bn-share" style="display:none"><img src="{e(card_url)}" alt="{e(article["title_hi"])}" '
                 f'width="1200" height="675" /></div>\n')
        figure = (f'<div class="separator bn-photo" data-section="{e(section)}"><img src="{e(photo["url"])}" alt="{alt}" '
                  f'width="1200" height="675" /></div>\n{_caption(photo)}')
    else:  # no photo: the branded card itself is shown
        share = ""
        figure = f'<div class="separator bn-cardimg"><img src="{e(card_url)}" alt="{alt}" width="1200" height="675" /></div>'
    return f"""<!--bn-slug:{slug(article.get("slug_en") or "")}-->
{share}<div class="bn-summary"><b class="t">⚡ 30 सेकंड में समझें</b><ul>{bullets}</ul></div>
<!--more-->
{figure}
{_numbers(article)}
{clean_html(article['body_html'])}
{_timeline(article)}
{_faq(article)}
<div class="bn-source"><strong>स्रोत:</strong> {' '.join(links[:5])}</div>
{_sensitive_note(article)}<p class="bn-ai">इस खबर को हमने कई विश्वसनीय स्रोतों से जाँचा और सत्यापित किया है और प्रकाशन से पहले स्वचालित रूप से जाँचा गया है। कोई गलती दिखे तो <a href="/p/corrections.html">हमें बताएँ</a>।</p>"""


def slug(s):
    s = re.sub(r"[^a-z0-9\s-]", "", (s or "").lower())
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return "-".join(s.split("-")[:7]) or "news"
