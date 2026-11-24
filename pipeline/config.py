"""All settings in one place. Values come from GitHub Secrets / Variables (environment)."""
import os

def env(name, default=None, required=False):
    v = os.environ.get(name, default)
    if required and not v:
        raise SystemExit(f"Missing required setting: {name}")
    return v

# --- Blogger ---
BLOG_ID = env("BLOG_ID", "547752296303974213")
SITE_URL = env("SITE_URL", "https://www.bijlinews.com")
GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = env("GOOGLE_CLIENT_SECRET")
GOOGLE_REFRESH_TOKEN = env("GOOGLE_REFRESH_TOKEN")

# --- AI ---
# Groq (free): "groq" writes, "groq_alt" (a different model, same key) is the backup writer and the
# independent fact-checker, so the article is never checked by the model that wrote it.
GROQ_API_KEY = env("GROQ_API_KEY")          # your key (the active key is switched at run time)
# Groq keys used in turn, one run each: Friend 1 -> Friend 2 -> yours -> Friend 1 ...
GROQ_KEYS = [(label, key) for label, key in (
    ("Friend 1", env("GROQ_API_KEY_FRIEND1")),
    ("Friend 2", env("GROQ_API_KEY_FRIEND2")),
    ("Mine", env("GROQ_API_KEY")),
) if key]
OPENROUTER_API_KEY = env("OPENROUTER_API_KEY")
MISTRAL_API_KEY = env("MISTRAL_API_KEY")   # optional (Mistral's API is paid-only now)
GROQ_MODEL = env("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_ALT_MODEL = env("GROQ_ALT_MODEL", "llama-3.3-70b-versatile")
OPENROUTER_MODEL = env("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
MISTRAL_MODEL = env("MISTRAL_MODEL", "mistral-medium-latest")
WRITER = env("WRITER", "groq")            # who writes; the other Groq model is the backup
TRIAGE = env("TRIAGE", "groq")            # who picks topics every hour (Groq has the bigger daily limit)

# --- Cover photos (Unsplash, free) ---
UNSPLASH_ACCESS_KEY = env("UNSPLASH_ACCESS_KEY")

# --- Email (Gmail SMTP with an App Password) ---
SMTP_HOST = env("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(env("SMTP_PORT", "465"))
SMTP_USER = env("SMTP_USER")
SMTP_PASS = env("SMTP_PASS")
NOTIFY_TO = env("NOTIFY_TO")

# --- Behaviour ---
# "auto": publish when every check passes, otherwise save a draft.
# "draft": never publish; always save drafts (safe mode / testing).
PUBLISH_MODE = env("PUBLISH_MODE", "auto")
DRY_RUN = env("DRY_RUN", "0") == "1"          # do everything except touch Blogger / send email
MAX_PER_RUN = int(env("MAX_PER_RUN", "1"))
MAX_PER_DAY = int(env("MAX_PER_DAY", "6"))
MIN_TRAFFIC = int(env("MIN_TRAFFIC", "2000"))  # Google Trends "approx traffic" threshold
MIN_OUTLETS = int(env("MIN_OUTLETS", "3"))    # independent news outlets needed before writing
MIN_FULLTEXT = int(env("MIN_FULLTEXT", "2"))  # articles we could actually read in full
MIN_FACTS = int(env("MIN_FACTS", "6"))        # verified facts needed before writing
REPO = env("GITHUB_REPOSITORY", "")           # owner/repo, set automatically by GitHub Actions

# Labels the live theme reads. The writer must pick exactly one of these.
SECTIONS = ["भारत", "दुनिया", "बिजनेस", "शेयर बाजार", "टेक्नोलॉजी", "खेल", "मनोरंजन", "हेल्थ"]
TREND_LABEL = "ट्रेंडिंग"

# Focus: the bot writes only in these sections (a site that covers a few beats well earns Google's
# trust faster than one that covers everything). Comma-separated; must be names from SECTIONS.
ALLOWED_SECTIONS = [s.strip() for s in env("ALLOWED_SECTIONS", "भारत,बिजनेस,शेयर बाजार,खेल").split(",")
                    if s.strip() in SECTIONS] or SECTIONS

# FAQ box + FAQPage schema under each post. Google no longer shows FAQ rich results, and the identical
# box on every post makes the site look templated, so it is off unless SHOW_FAQ=1.
SHOW_FAQ = env("SHOW_FAQ", "0") == "1"

STATE_FILE = "state/state.json"
IMAGE_DIR = "images"
FONT_BOLD = env("FONT_BOLD", "fonts/Mukta-ExtraBold.ttf")
FONT_REGULAR = env("FONT_REGULAR", "fonts/Mukta-Medium.ttf")
