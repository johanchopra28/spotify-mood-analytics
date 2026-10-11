"""Weekly mood -> cat meme, using the CATAAS service (https://cataas.com).

Everything here is automatic: the dashboard computes the dominant mood of the last
7 days from the database, asks CATAAS for cats tagged with matching words, and picks
one deterministically per ISO week (so it is stable all week and changes weekly).
If CATAAS is unreachable or has nothing suitable, get_cat_meme() returns None and the
dashboard falls back to an emoji card. Set CAT_MEME=off to disable the feature.

CATAAS tags are user-submitted, so cats carrying any tag in BLOCKED_TAGS are skipped.
That reduces, but cannot eliminate, the chance of an unwanted image.
"""
import random
import pandas as pd
import requests

CATAAS = "https://cataas.com"

# Tags to search per mood (one query per tag; CATAAS ANDs multiple tags in one query).
MOOD_TAGS = {
    "calm":    ["Sleeping", "Sleepy", "Sleep", "Relaxed", "Shhhsh"],
    "mellow":  ["Cute", "Curious", "Smol", "Lay"],
    "intense": ["Angry", "Fierce", "Grumpy", "Evil", "Roar", "Screaming"],
    "upbeat":  ["Happy", "Silly", "Funny", "Meme"],
}

CAPTIONS = {
    "calm":    ["me, horizontal and thriving", "vibes: unbothered"],
    "mellow":  ["soft hours only", "gentle cat energy"],
    "intense": ["ABSOLUTELY LOCKED IN", "this week's villain arc"],
    "upbeat":  ["main character week", "dancing in the kitchen"],
}

EMOJI = {"calm": "😴", "mellow": "😺", "intense": "😾", "upbeat": "😸"}

BLOCKED_TAGS = {"nsfw", "nazi", "hitler", "porn", "gore", "blood", "dead", "death", "nude", "sex"}
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}


def weekly_dominant_mood(daily_mood, now=None, days=7):
    """Mood with the most minutes over the last `days` days, or None if no data.

    daily_mood needs `listen_date` (tz-aware or naive) and `mood`, `minutes_listened`.
    """
    if daily_mood is None or daily_mood.empty:
        return None
    now = now if now is not None else pd.Timestamp.now(tz="Asia/Kolkata")
    dates = pd.to_datetime(daily_mood["listen_date"])
    if dates.dt.tz is not None and now.tzinfo is None:
        now = now.tz_localize(dates.dt.tz)
    cutoff = now.normalize() - pd.Timedelta(days=days - 1)
    recent = daily_mood[dates >= cutoff]
    if recent.empty:
        return None
    totals = recent.groupby("mood")["minutes_listened"].sum()
    # highest minutes; alphabetical tie-break so the result is deterministic
    return sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def is_safe(cat):
    tags = {str(t).strip().lower() for t in cat.get("tags", [])}
    if tags & BLOCKED_TAGS:
        return False
    return cat.get("mimetype") in ALLOWED_TYPES


def candidate_cat_ids(mood, http_get=requests.get):
    """Ids of safe cats tagged for this mood (sorted for determinism)."""
    ids = set()
    for tag in MOOD_TAGS.get(mood, []):
        resp = http_get(f"{CATAAS}/api/cats", params={"tags": tag, "limit": 100}, timeout=10)
        resp.raise_for_status()
        ids.update(c["id"] for c in resp.json() if is_safe(c))
    return sorted(ids)


def image_url(cat_id, width=300):
    # CATAAS's /says/ caption endpoint returns HTTP 500 whenever `width` is set, so the
    # caption is drawn over the plain (resized) image by the dashboard instead.
    return f"{CATAAS}/cat/{cat_id}?width={width}"


def get_cat_meme(mood, week_key, http_get=requests.get):
    """Return {"mood", "url", "caption"} for the mood and week, or None on failure."""
    if mood not in MOOD_TAGS:
        return None
    try:
        ids = candidate_cat_ids(mood, http_get)
    except Exception:
        return None
    if not ids:
        return None
    rng = random.Random(f"{week_key}-{mood}")   # stable for the whole week
    caption = rng.choice(CAPTIONS[mood])
    return {"mood": mood, "url": image_url(rng.choice(ids)), "caption": caption}


def week_key(now=None):
    iso = (now if now is not None else pd.Timestamp.now(tz="Asia/Kolkata")).isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"
