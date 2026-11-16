# बिजली न्यूज़: trend-to-article bot

Every hour (06:53–22:53 IST) a GitHub Action:

1. Reads **Google Trends India** and keeps topics with 500+ searches that it hasn't seen in the last 4 days.
2. **AI editor (Gemini)** picks the topics worth covering for Hindi readers, assigns a section, and flags **sensitive** topics (deaths, crime, allegations, elections, health, investment tips…).
3. **Research:** reads the articles Google Trends links to, plus Hindi and English Google News. It skips a topic if fewer than 3 different outlets cover it.
4. **AI writer** drafts a Hindi explainer using only facts in the sources: headline, "30 सेकंड में समझें" box, article, search description and an English slug.
5. **AI fact-checker** (a separate step) checks every claim against *other* outlets, runs its own Google searches, and returns PASS / FIX / FAIL. On FIX the article is corrected once and checked again.
6. Makes a branded **1200×675 cover image** with the Hindi headline. There are no third-party photos, so there's no copyright risk.
7. **Publishes** to Blogger only if: the fact-check passes, every claim is supported, the topic isn't sensitive, and `PUBLISH_MODE=auto`. Otherwise it saves a **draft**.
8. **Emails you** for every article (published or draft) with the fact-check table and links.

### Safety limits (change them under GitHub → Settings → Variables)

| Variable | Default | Meaning |
|---|---|---|
| `PUBLISH_MODE` | `draft` | `auto` = publish when every check passes. Start with `draft` for a few days. |
| `MAX_PER_RUN` | 2 | articles per hour |
| `MAX_PER_DAY` | 8 | articles per day |
| `MIN_TRAFFIC` | 500 | minimum Google Trends search volume |
| `WRITER_MODEL` / `CHECKER_MODEL` | gemini-2.5-flash | change if Google renames models |

Every article ends with a line saying it was prepared with AI help and checked automatically against other sources, with a link to the corrections page.

Setup instructions are in **SETUP.md**.
