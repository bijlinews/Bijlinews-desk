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

# --- AI (Gemini) ---
GEMINI_API_KEY = env("GEMINI_API_KEY")
WRITER_MODEL = env("WRITER_MODEL", "gemini-flash-latest")
CHECKER_MODEL = env("CHECKER_MODEL", "gemini-flash-latest")
# Let the fact-checker run its own Google searches (uses the Gemini "grounding" quota).
CHECKER_WEB_SEARCH = env("CHECKER_WEB_SEARCH", "1") == "1"

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
MAX_PER_RUN = int(env("MAX_PER_RUN", "2"))
MAX_PER_DAY = int(env("MAX_PER_DAY", "8"))
MIN_TRAFFIC = int(env("MIN_TRAFFIC", "500"))  # Google Trends "approx traffic" threshold
MIN_OUTLETS = int(env("MIN_OUTLETS", "3"))    # independent news outlets needed before writing
REPO = env("GITHUB_REPOSITORY", "")           # owner/repo, set automatically by GitHub Actions

# Labels the live theme reads. The writer must pick exactly one of these.
SECTIONS = ["भारत", "दुनिया", "बिजनेस", "शेयर बाजार", "टेक्नोलॉजी", "खेल", "मनोरंजन", "हेल्थ"]
TREND_LABEL = "ट्रेंडिंग"

STATE_FILE = "state/state.json"
IMAGE_DIR = "images"
FONT_BOLD = env("FONT_BOLD", "fonts/Mukta-ExtraBold.ttf")
FONT_REGULAR = env("FONT_REGULAR", "fonts/Mukta-Medium.ttf")
