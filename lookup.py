"""Look up one Spotify song across Spotify, ReccoBeats and Last.fm.

Pure functions with injectable HTTP, so they can be tested without the network. Nothing here writes
to the database. The only user input is a Spotify link, from which a 22-character track id is
extracted; every URL that is fetched is built from fixed hosts plus that id, never from the input.
"""
import os
import re

import requests

import covers

ID_RE = re.compile(r"^[A-Za-z0-9]{22}$")
URL_RE = re.compile(r"open\.spotify\.com/(?:intl-[A-Za-z-]+/)?track/([A-Za-z0-9]{22})")
URI_RE = re.compile(r"^spotify:track:([A-Za-z0-9]{22})$")

RECCOBEATS_URL = "https://api.reccobeats.com/v1/audio-features"
LASTFM_URL = "http://ws.audioscrobbler.com/2.0/"
MOODS = ["calm", "mellow", "intense", "upbeat"]
TAG_MIN_WEIGHT = 10   # the pipeline keeps tags with a Last.fm weight of at least 10 ...
TAG_LIMIT = 5         # ... and at most the top five

FEATURES = [  # (key, label, meaning)
    ("valence", "Valence", "Musical positivity: low sounds sad or angry, high sounds happy"),
    ("energy", "Energy", "Intensity and activity"),
    ("danceability", "Danceability", "How suitable the song is for dancing"),
    ("acousticness", "Acousticness", "Confidence that the song is acoustic"),
    ("speechiness", "Speechiness", "How much of the song is spoken words"),
    ("instrumentalness", "Instrumentalness", "Likelihood that there are no vocals"),
    ("liveness", "Liveness", "Likelihood of a live audience in the recording"),
    ("loudness", "Loudness (dB)", "Average loudness, negative; closer to 0 is louder"),
    ("tempo", "Tempo (BPM)", "Beats per minute"),
    ("key", "Key", "Pitch class, 0 = C, 1 = C sharp, and so on"),
    ("mode", "Mode", "1 = major, 0 = minor"),
]


class LookupFailed(Exception):
    """A lookup failed in a way worth showing to the user."""


def parse_track_id(text):
    """Spotify track id from a link, URI or bare id; None if it is not one."""
    s = (text or "").strip()
    for rx in (URL_RE, URI_RE):
        m = rx.search(s) if rx is URL_RE else rx.match(s)
        if m:
            return m.group(1)
    return s if ID_RE.match(s) else None


def audio_mood(valence, energy):
    """The pipeline's rule: valence and energy quadrants with a 0.5 cut-off."""
    if valence is None or energy is None:
        return None
    if valence >= 0.5:
        return "upbeat" if energy >= 0.5 else "calm"
    return "intense" if energy >= 0.5 else "mellow"


# ------------------------------------------------------------------ Spotify
def build_spotify_client():
    """Spotify client that needs no user login (public song details only)."""
    import spotipy
    from spotipy.cache_handler import MemoryCacheHandler
    from spotipy.oauth2 import SpotifyClientCredentials
    return spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=os.getenv("SPOTIPY_CLIENT_ID"), client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
            cache_handler=MemoryCacheHandler()),
        requests_timeout=15, retries=1)


def fetch_spotify_track(track_id, client=None):
    client = client or build_spotify_client()
    try:
        t = client.track(track_id)
    except Exception as exc:
        status = getattr(exc, "http_status", None)
        if status == 404:
            raise LookupFailed("Spotify could not find that song.") from exc
        raise LookupFailed(f"Spotify did not return the song details ({exc.__class__.__name__}).") from exc
    album = t.get("album") or {}
    return {
        "id": t["id"],
        "name": t["name"],
        "artists": [{"name": a["name"], "id": a.get("id")} for a in t.get("artists", [])],
        "album": album.get("name"),
        "release_date": album.get("release_date"),
        "duration_ms": t.get("duration_ms"),
        "isrc": (t.get("external_ids") or {}).get("isrc"),
        "explicit": t.get("explicit"),
        "image": covers.pick_image(album.get("images")),
        "url": f"https://open.spotify.com/track/{t['id']}",
    }


# ------------------------------------------------------------------ ReccoBeats
def fetch_reccobeats(track_id, http_get=requests.get):
    """ReccoBeats' ratings for the song, or None if ReccoBeats does not know it."""
    try:
        resp = http_get(RECCOBEATS_URL, params={"ids": track_id}, timeout=20)
    except Exception as exc:
        raise LookupFailed(f"Could not reach ReccoBeats ({exc.__class__.__name__}).") from exc
    if resp.status_code != 200:
        raise LookupFailed(f"ReccoBeats returned HTTP {resp.status_code}.")
    for item in resp.json().get("content", []):
        if str(item.get("href", "")).rstrip("/").endswith(track_id):
            return item
    return None


# ------------------------------------------------------------------ Last.fm
def _lastfm(method, key, http_get, **params):
    if not key:
        raise LookupFailed("No Last.fm API key is configured (LASTFM_API_KEY in .env).")
    try:
        resp = http_get(LASTFM_URL, params={"method": method, "api_key": key, "format": "json", **params}, timeout=20)
        return resp.json()
    except Exception as exc:
        raise LookupFailed(f"Could not reach Last.fm ({exc.__class__.__name__}).") from exc


def _tags(payload, path):
    node = payload
    for p in path:
        node = (node or {}).get(p, {})
    return [(t["name"], int(t.get("count", 0))) for t in (node if isinstance(node, list) else [])]


def lastfm_artist(name, key, http_get=requests.get):
    """Tags (with weights), listener counts and similar artists for an artist."""
    tags = _tags(_lastfm("artist.gettoptags", key, http_get, artist=name, autocorrect=1), ["toptags", "tag"])
    info = _lastfm("artist.getinfo", key, http_get, artist=name, autocorrect=1).get("artist", {})
    stats = info.get("stats", {})
    return {
        "name": info.get("name") or name,
        "tags": tags,
        "listeners": int(stats["listeners"]) if stats.get("listeners") else None,
        "playcount": int(stats["playcount"]) if stats.get("playcount") else None,
        "similar": [s["name"] for s in info.get("similar", {}).get("artist", [])][:6],
        "found": bool(info) or bool(tags),
    }


def lastfm_track(artist, track, key, http_get=requests.get):
    """Track-level tags (with weights) and listener counts."""
    tags = _tags(_lastfm("track.gettoptags", key, http_get, artist=artist, track=track, autocorrect=1), ["toptags", "tag"])
    info = _lastfm("track.getinfo", key, http_get, artist=artist, track=track, autocorrect=1).get("track", {})
    return {
        "tags": tags,
        "listeners": int(info["listeners"]) if info.get("listeners") else None,
        "playcount": int(info["playcount"]) if info.get("playcount") else None,
        "found": bool(info) or bool(tags),
    }


def vote(tags, seed):
    """The pipeline's genre-mood rule, applied to [(tag, weight)].

    Keep the top five tags with weight >= 10, give each the mood the seed list assigns (case-insensitive),
    and pick the mood with the most votes, ties going to the alphabetically earlier mood.
    """
    used = [(t, w) for t, w in tags if w >= TAG_MIN_WEIGHT][:TAG_LIMIT]
    used_names = {t for t, _ in used}
    counts = {k: 0 for k in MOODS}
    per_tag = []
    for t, w in tags:
        is_used = t in used_names
        mood = seed.get(t.lower()) if is_used else None
        per_tag.append({"tag": t, "weight": w, "used": is_used, "mood": mood})
        if mood:
            counts[mood] += 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    top, second = ranked[0][1], ranked[1][1]
    total = sum(counts.values())
    if total == 0:
        how = "no tag maps to a mood"
    elif total == 1:
        how = "one tag decided it"
    elif top == second:
        how = "tie, broken alphabetically"
    else:
        how = "clear majority"
    return {"counts": counts, "per_tag": per_tag, "winner": ranked[0][0] if top else None,
            "top": top, "second": second, "how": how}
