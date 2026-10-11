import os
import time
import requests
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import psycopg2
from psycopg2.extras import execute_values

load_dotenv()

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
    scope="user-read-recently-played",
    cache_path=".spotify_cache"
))

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_URL = "http://ws.audioscrobbler.com/2.0/"

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )

def fetch_recently_played():
    results = sp.current_user_recently_played(limit=50)
    return results["items"]

def transform(tracks):
    """Turn Spotify's raw JSON into flat tuples matching our table columns."""
    rows = []
    for item in tracks:
        track = item["track"]
        rows.append((
            item["played_at"],
            track["id"],
            track["name"],
            ", ".join([a["name"] for a in track["artists"]]),
            track["artists"][0]["id"],  # primary artist's Spotify ID
            track["album"]["name"],
            track["duration_ms"],
        ))
    return rows

def load(rows):
    """Insert play rows into Postgres, skipping duplicates."""
    if not rows:
        print("No rows to insert.")
        return

    conn = get_db_connection()
    cur = conn.cursor()

    query = """
        INSERT INTO raw_recently_played
            (played_at, track_id, track_name, artist_names, primary_artist_id, album_name, duration_ms)
        VALUES %s
        ON CONFLICT (played_at, track_id) DO NOTHING
    """
    execute_values(cur, query, rows)
    inserted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()

    print(f"Inserted {inserted} new play rows (out of {len(rows)} fetched).")

def get_unique_artists(tracks):
    """Return a dict of {spotify_artist_id: artist_name} from a batch of played tracks."""
    artists = {}
    for item in tracks:
        for artist in item["track"]["artists"]:
            artists[artist["id"]] = artist["name"]
    return artists

def fetch_lastfm_tags(artist_name):
    """Query Last.fm for an artist's top tags, keeping only reasonably common ones."""
    try:
        resp = requests.get(LASTFM_URL, params={
            "method": "artist.gettoptags",
            "artist": artist_name,
            "api_key": LASTFM_API_KEY,
            "format": "json",
        }, timeout=10)
        data = resp.json()
        tags = data.get("toptags", {}).get("tag", [])
        # Keep tags with a meaningful count, top 5 max, to avoid noisy one-off user tags
        genres = [t["name"] for t in tags if int(t.get("count", 0)) >= 10][:5]
        return genres
    except Exception as e:
        print(f"  Warning: failed to fetch tags for '{artist_name}': {e}")
        return []

def fetch_and_load_artist_genres(artists_dict):
    """Fetch genres for artists we haven't already stored, via Last.fm."""
    if not artists_dict:
        print("No artists to process.")
        return

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute(
        "SELECT artist_id FROM raw_artist_genres WHERE artist_id = ANY(%s)",
        (list(artists_dict.keys()),)
    )
    already_have = {row[0] for row in cur.fetchall()}
    to_fetch = {aid: name for aid, name in artists_dict.items() if aid not in already_have}

    if not to_fetch:
        print("No new artists to fetch genres for.")
        cur.close()
        conn.close()
        return

    rows = []
    for artist_id, artist_name in to_fetch.items():
        genres = fetch_lastfm_tags(artist_name)
        rows.append((artist_id, artist_name, genres))
        time.sleep(0.25)  # stay comfortably under Last.fm's rate limit

    query = """
        INSERT INTO raw_artist_genres (artist_id, artist_name, genres)
        VALUES %s
        ON CONFLICT (artist_id) DO NOTHING
    """
    execute_values(cur, query, rows)
    conn.commit()
    cur.close()
    conn.close()

    print(f"Fetched and stored genres for {len(rows)} artists via Last.fm.")

RECCOBEATS_URL = "https://api.reccobeats.com/v1/audio-features"
RECCOBEATS_BATCH = 40          # API rejects more than 40 ids per request
MISS_RETRY_DAYS = 30           # retry tracks ReccoBeats did not know after this long
AUDIO_COLS = ["acousticness", "danceability", "energy", "instrumentalness",
              "liveness", "loudness", "speechiness", "tempo", "valence", "key", "mode"]

def fetch_audio_batch(track_ids):
    """Return {spotify_track_id: feature_dict} for the tracks ReccoBeats knows."""
    for attempt in range(4):
        resp = requests.get(RECCOBEATS_URL, params={"ids": ",".join(track_ids)}, timeout=30)
        if resp.status_code == 429:
            time.sleep(int(resp.headers.get("Retry-After", 5)))
            continue
        resp.raise_for_status()
        break
    else:
        raise RuntimeError("ReccoBeats kept returning 429")
    found = {}
    for item in resp.json().get("content", []):
        found[item["href"].rsplit("/", 1)[-1]] = item  # href holds the Spotify track URL
    return found

def fetch_and_load_audio_features(track_ids):
    """Fetch ReccoBeats audio features for uncached tracks; cache misses as found=false."""
    track_ids = list(dict.fromkeys(track_ids))
    if not track_ids:
        return

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT track_id FROM raw_audio_features
           WHERE track_id = ANY(%s)
             AND (found OR fetched_at > now() - make_interval(days => %s))""",
        (track_ids, MISS_RETRY_DAYS)
    )
    cached = {r[0] for r in cur.fetchall()}
    to_fetch = [t for t in track_ids if t not in cached]
    if not to_fetch:
        print("No new tracks needing audio features.")
        cur.close(); conn.close()
        return

    rows, n_found = [], 0
    for i in range(0, len(to_fetch), RECCOBEATS_BATCH):
        batch = to_fetch[i:i + RECCOBEATS_BATCH]
        found = fetch_audio_batch(batch)
        for tid in batch:
            item = found.get(tid)
            if item:
                n_found += 1
                rows.append((tid, True, item.get("id"), item.get("isrc"),
                             *[item.get(c) for c in AUDIO_COLS]))
            else:
                rows.append((tid, False, None, None, *[None] * len(AUDIO_COLS)))
        time.sleep(0.5)

    query = f"""
        INSERT INTO raw_audio_features
            (track_id, found, reccobeats_id, isrc, {", ".join(AUDIO_COLS)})
        VALUES %s
        ON CONFLICT (track_id) DO UPDATE SET
            found = EXCLUDED.found, fetched_at = now(),
            reccobeats_id = EXCLUDED.reccobeats_id, isrc = EXCLUDED.isrc,
            {", ".join(f"{c} = EXCLUDED.{c}" for c in AUDIO_COLS)}
    """
    execute_values(cur, query, rows)
    conn.commit()
    cur.close(); conn.close()
    print(f"ReccoBeats audio features: {n_found} found, {len(rows) - n_found} missing "
          f"(out of {len(rows)} requested).")

if __name__ == "__main__":
    raw_tracks = fetch_recently_played()

    play_rows = transform(raw_tracks)
    load(play_rows)

    artists = get_unique_artists(raw_tracks)
    fetch_and_load_artist_genres(artists)
    fetch_and_load_audio_features([item["track"]["id"] for item in raw_tracks])
