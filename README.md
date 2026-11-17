# बिजली न्यूज़: trend-to-article bot

Every hour (06:53–22:53 IST) a GitHub Action:

1. Reads **Google Trends India** and keeps topics with 500+ searches that it hasn't seen in the last 4 days.
2. **AI editor (Groq; GitHub Models as backup)** picks the topics worth covering, assigns a section and flags **sensitive** topics.
3. **Research, no API keys:** reads the full text of the articles Google Trends links to, plus a DuckDuckGo news search. It skips a topic unless 3+ outlets cover it and at least 2 articles could be read in full.
4. **Verified fact sheet:** the AI lists the facts, each with an exact quote from a report. Python throws away any fact whose quote isn't really in that report. At least 6 verified facts are needed.
5. **AI writer (GitHub Models GPT-4.1, free, no key; Groq as backup)** writes the Hindi article using only those verified facts.
6. **Fact-check:** Python checks that every number in the article appears in the sources. A different AI (Groq) checks every sentence against the facts and fresh DuckDuckGo web results. On FIX, the bad sentences are removed and it is checked again.
7. **Cover photo:** a generic Unsplash photo (objects or places, never people), with the photographer credited. Without an Unsplash key, a branded headline card is used.
8. **Publishes** only if: the check passes, every statement and number is supported, the topic isn't sensitive, and `PUBLISH_MODE=auto`. Otherwise it saves a **draft**.
9. **Emails you** for every article, with the fact-check table.

Keys needed: Groq, Unsplash, Blogger (Google OAuth) and Gmail. GitHub Models uses the Action's own token.

### Safety limits (change them under GitHub → Settings → Variables)

| Variable | Default | Meaning |
|---|---|---|
| `PUBLISH_MODE` | `draft` | `auto` = publish when every check passes. Start with `draft` for a few days. |
| `MAX_PER_RUN` | 2 | articles per hour |
| `MAX_PER_DAY` | 8 | articles per day |
| `MIN_TRAFFIC` | 500 | minimum Google Trends search volume |
| `WRITER` / `TRIAGE` | github / groq | which AI writes articles / picks topics |
| `GITHUB_MODEL` / `GROQ_MODEL` | openai/gpt-4.1 / openai/gpt-oss-120b | if a model is retired, the bot picks the best available one automatically |

Every article ends with a line saying it was prepared with AI help and checked automatically against other sources, with a link to the corrections page.

Setup instructions are in **SETUP.md**.

If both AI services are down, the run ends quietly and tries again next hour (no error email).
