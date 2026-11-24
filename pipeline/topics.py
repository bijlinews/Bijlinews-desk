"""Plain-Python filter for Google Trends topics, applied before the AI sees them.

These are trends a new Hindi site cannot win: people searching them want a live score, a price
table or a page in another language, and big sites already rank for them within minutes.
Writing them wastes the daily limit and makes the site look like it chases every trend.
"""
import re

# Indian scripts other than Devanagari (Bengali, Gurmukhi, Gujarati, Odia, Tamil, Telugu, Kannada,
# Malayalam), plus Arabic/Urdu: these readers search in their own language, not Hindi.
OTHER_SCRIPTS = re.compile(r"[ঀ-ൿ؀-ۿ]")

LIVE_MATCH = re.compile(
    r"(score\s*card|scorecard|live\s*score|\blive\b|standings|points\s*table|lineups?"
    r"|playing\s*(11|xi)|dream\s*11|prediction|highlights|स्कोर|लाइव)", re.I)
VERSUS = re.compile(r"(\bvs\.?\b|\bv/s\b|\bversus\b|बनाम)", re.I)
INDIA = re.compile(r"(\bind\b|\bindia\b|\bindian\b|भारत|इंडिया)", re.I)

DAILY_LOOKUP = re.compile(
    r"((gold|silver|petrol|diesel|cng|lpg|सोना|सोने|चांदी|पेट्रोल|डीजल).*(rate|price|भाव|कीमत|दाम|today|आज))"
    r"|((rate|price|भाव|कीमत|दाम)\s*(today|आज))"
    r"|(\b(lottery|satta|teer|matka)\b|लॉटरी|सट्टा)"
    r"|(\bresult\b.*\b(today|live)\b)|(कल का मौसम|आज का मौसम|weather today|weather tomorrow)", re.I)

GAMES_OTT = re.compile(r"(\bgta\s*(\d|vi\b)|\bbgmi\b|free\s*fire|\bott\b|new\s+releases?|web\s*series)", re.I)
# one-word / generic trends: no single news event behind them, so research mixes reports from different days
GENERIC = {"odi", "test", "t20", "t20i", "ipl", "cricket", "news", "weather", "india", "ind", "match", "today",
           "result", "results", "score", "gold", "sensex", "nifty", "share market", "stock market", "bitcoin",
           "क्रिकेट", "मौसम", "खबर", "समाचार", "आज", "मैच", "शेयर बाजार", "सोना"}
EXPLAINER = re.compile(r"^(why|how|what|क्यों|कैसे|क्या)\b", re.I)


def skip_reason(title):
    """Return a short reason to skip this trend, or '' to let the AI judge it."""
    t = (title or "").strip()
    if not t:
        return "empty"
    if t.lower() in GENERIC or len(t) <= 3:
        return "generic trend word (no single news event)"
    if OTHER_SCRIPTS.search(t):
        return "regional-language trend"
    if LIVE_MATCH.search(t):
        return "live match / score lookup"
    if VERSUS.search(t) and not INDIA.search(t):
        return "match between non-Indian teams"
    if EXPLAINER.search(t):
        return ""                 # "why is gold falling" is a question we can answer well: let the AI judge
    if DAILY_LOOKUP.search(t):
        return "daily price / lottery / weather lookup"
    if GAMES_OTT.search(t):
        return "games / OTT listings"
    return ""
