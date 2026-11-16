"""Email the editor after every post (published or held as draft)."""
import html
import smtplib
from email.mime.text import MIMEText

from . import config

COLORS = {"supported": "#1a7f37", "unsupported": "#b26a00", "contradicted": "#c62828"}


def send(subject, body_html):
    if config.DRY_RUN or not (config.SMTP_USER and config.SMTP_PASS and config.NOTIFY_TO):
        print(f"  (email not sent) {subject}")
        return
    msg = MIMEText(body_html, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = f"Bijli News Bot <{config.SMTP_USER}>"
    msg["To"] = config.NOTIFY_TO
    with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as s:
        s.login(config.SMTP_USER, config.SMTP_PASS)
        s.send_message(msg)


def post_report(status, reason, article, post, check, trend):
    e = html.escape
    published = status == "published"
    head = ("✅ प्रकाशित हुआ — कृपया एक बार पढ़ लें" if published
            else f"✋ ड्राफ्ट में रखा गया — आपकी जाँच ज़रूरी है ({e(reason)})")
    rows = "".join(
        f"<tr><td style='padding:6px;border-bottom:1px solid #eee'>{e(c.get('claim',''))}</td>"
        f"<td style='padding:6px;border-bottom:1px solid #eee;color:{COLORS.get(c.get('status'),'#555')};font-weight:700'>{e(c.get('status',''))}</td>"
        f"<td style='padding:6px;border-bottom:1px solid #eee;font-size:12px;color:#666'>{e(str(c.get('evidence',''))[:120])}</td></tr>"
        for c in (check or {}).get("claims", []))
    link = post.get("url") or post.get("edit_url")
    body = f"""<div style="font-family:Arial,sans-serif;max-width:680px">
<p style="font-size:16px;font-weight:700">{head}</p>
<h2 style="margin:6px 0">{e(article['title_hi'])}</h2>
<p>ट्रेंड: <b>{e(trend['title'])}</b> ({trend['traffic']}+ searches)</p>
<p>
  {'<a href="'+e(post.get('url',''))+'" style="background:#111;color:#fff;padding:10px 16px;border-radius:8px;text-decoration:none">लेख खोलें</a> ' if published else ''}
  <a href="{e(post['edit_url'])}" style="background:#FFD000;color:#111;padding:10px 16px;border-radius:8px;text-decoration:none">Blogger में एडिट करें</a>
</p>
{'<p style="color:#666;font-size:13px">हटाना हो तो: Blogger में एडिट खोलें → ऊपर "Revert to draft" दबाएँ।</p>' if published else
 f'<p style="color:#666;font-size:13px">प्रकाशित करने से पहले: तथ्य जाँचें, फिर Settings में Permalink → Custom: <b>{e(article.get("slug_en",""))}</b> और Search description भरें।</p>'}
<p><b>Search description (कॉपी करें):</b><br>{e(article.get('search_description',''))}</p>
<h3>Fact-check: {e((check or {}).get('verdict','—'))}</h3>
<p style="color:#555">{e((check or {}).get('notes',''))}</p>
<table style="border-collapse:collapse;width:100%;font-size:14px">{rows}</table>
</div>"""
    subject = ("[प्रकाशित] " if published else "[ड्राफ्ट] ") + article["title_hi"][:80]
    send(subject, body)
    return link


def run_failed(error_text):
    send("[Bijli bot] run failed", f"<pre>{html.escape(error_text)[:5000]}</pre>")
