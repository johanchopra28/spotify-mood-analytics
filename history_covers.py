"""Fetch album covers for the songs the Lifetime Wrapped page shows.

Run after import_history.py and dbt:
    python history_covers.py

Covers the overall top songs, every song that was a month's number one, and each year's top songs
(about two thousand songs). Songs already in track_covers are skipped, and the rest are looked up through
Spotify's keyless oEmbed endpoint, a few per second. Safe to run again.
"""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from psycopg2.extras import execute_values
import psycopg2

import covers
import wrapped as w

ROOT = Path(__file__).resolve().parent
TOP_OVERALL, TOP_PER_YEAR = 2000, 60


def wanted_track_ids(conn):
    df = pd.read_sql(
        "select played_at, track_id, track_name, artist_name, album_name, seconds_played::float as seconds_played, "
        "is_real_play, skipped from dbt_dev.all_plays", conn)
    real = w.real_plays(w.prepare(df))
    ids = set(w.top_songs(real, TOP_OVERALL)["track_id"])
    for year in sorted(real["year"].unique()):
        ids |= set(w.monthly_rulers(real, year)["track_id"])
        ids |= set(w.top_songs(real, TOP_PER_YEAR, year)["track_id"])
    return sorted(ids)


def main():
    load_dotenv(ROOT / ".env")
    conn = psycopg2.connect(host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT"), dbname=os.getenv("DB_NAME"),
                            user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"))
    ids = wanted_track_ids(conn)
    cur = conn.cursor()
    cur.execute("SELECT track_id FROM track_covers WHERE image_url IS NOT NULL")
    have = {r[0] for r in cur.fetchall()}
    todo = [t for t in ids if t not in have]
    print(f"songs wanted: {len(ids):,} | already have a cover: {len(ids) - len(todo):,} | to fetch: {len(todo):,}", flush=True)

    done = 0
    for i in range(0, len(todo), 100):
        chunk = todo[i:i + 100]
        found = covers.fetch_missing(chunk, {})
        execute_values(cur, """
            INSERT INTO track_covers (track_id, image_url) VALUES %s
            ON CONFLICT (track_id) DO UPDATE SET image_url = EXCLUDED.image_url, fetched_at = now()
        """, list(found.items()))
        conn.commit()
        done += len(chunk)
        print(f"  {done:,} / {len(todo):,}", flush=True)
    cur.execute("SELECT count(*) FILTER (WHERE image_url IS NOT NULL), count(*) FROM track_covers")
    ok, total = cur.fetchone()
    print(f"track_covers now holds {ok:,} covers ({total - ok:,} looked up with no cover available)")
    conn.close()


if __name__ == "__main__":
    main()
