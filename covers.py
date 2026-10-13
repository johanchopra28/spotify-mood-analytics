"""Album cover art for tracks, cached in Postgres (table track_covers).

Covers come from the Spotify payload when ingest already has it (free), and from Spotify's
keyless oEmbed endpoint for any track still missing one. Only Spotify image hosts are accepted.
"""
import time
from urllib.parse import urlparse

import requests

OEMBED_URL = "https://open.spotify.com/oembed"
ALLOWED_HOSTS = ("i.scdn.co",)
ALLOWED_SUFFIXES = (".spotifycdn.com", ".scdn.co")


def is_spotify_image(url):
    """True only for https URLs on Spotify's image hosts (guards what the dashboard renders)."""
    try:
        u = urlparse(url)
    except Exception:
        return False
    host = (u.hostname or "").lower()
    return u.scheme == "https" and (host in ALLOWED_HOSTS or host.endswith(ALLOWED_SUFFIXES))


def pick_image(images):
    """From Spotify's album.images (largest first) choose the ~300px one."""
    good = [i for i in (images or []) if i.get("url") and is_spotify_image(i["url"])]
    if not good:
        return None
    for img in good:
        if img.get("width") == 300:
            return img["url"]
    return good[1]["url"] if len(good) > 1 else good[0]["url"]


def oembed_cover(track_id, http_get=requests.get):
    """Cover URL for a track via oEmbed, or None if unavailable."""
    try:
        resp = http_get(OEMBED_URL, params={"url": f"https://open.spotify.com/track/{track_id}"}, timeout=15)
        if resp.status_code != 200:
            return None
        url = resp.json().get("thumbnail_url")
    except Exception:
        return None
    return url if url and is_spotify_image(url) else None


def fetch_missing(track_ids, known, http_get=requests.get, pause=0.2):
    """Return {track_id: url_or_None} for every id, using `known` first and oEmbed for the rest."""
    out = {}
    for tid in track_ids:
        url = known.get(tid)
        if not url:
            url = oembed_cover(tid, http_get)
            if pause:
                time.sleep(pause)
        out[tid] = url
    return out
