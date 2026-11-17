"""Turn the AI output into the post HTML the theme expects."""
import html
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


def build_post(article, image_url, sources):
    e = html.escape
    bullets = "".join(f"<li>{e(b)}</li>" for b in article["summary"][:3])
    used = [s for s in sources if s.get("text")] or sources[:5]
    seen, links = set(), []
    for s in used:
        if s["source"] in seen or not s.get("url"):
            continue
        seen.add(s["source"])
        links.append(f'<a href="{e(s["url"])}" rel="nofollow noopener" target="_blank">{e(s["source"])}</a>')
    return f"""<div class="bn-summary"><b class="t">⚡ 30 सेकंड में समझें</b><ul>{bullets}</ul></div>
<!--more-->
<div class="separator"><img src="{e(image_url)}" alt="{e(article['image_alt'])}" width="1200" height="675" /></div>
{_caption(article.get('_photo'))}
{clean_html(article['body_html'])}
<p class="bn-source"><strong>स्रोत:</strong> {' · '.join(links[:5])}</p>
<p class="bn-ai">यह लेख AI की मदद से ऊपर दिए गए समाचार स्रोतों के आधार पर तैयार किया गया है और प्रकाशन से पहले स्वचालित रूप से जाँचा गया है। कोई गलती दिखे तो <a href="/p/corrections.html">हमें बताएँ</a>।</p>"""


def slug(s):
    s = re.sub(r"[^a-z0-9\s-]", "", (s or "").lower())
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return "-".join(s.split("-")[:7]) or "news"
