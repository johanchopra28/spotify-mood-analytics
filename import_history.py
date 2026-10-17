"""Load the Spotify Extended Streaming History (the zip you download from Spotify) into Postgres.

Usage (from the repo root):
    python import_history.py "C:/Users/DELL/Downloads/my_spotify_data.zip"

Only music plays are loaded. The IP address and country in the export are NOT copied.
Safe to run again: plays already stored (same end time and track) are skipped.
The zip itself is personal data and never goes into the repo.
"""
import json
import os
import sys
import zipfile
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values

ROOT = Path(__file__).resolve().parent
BATCH = 5000

COLUMNS = ("played_at", "track_id", "track_name", "artist_name", "album_name", "ms_played",
           "reason_start", "reason_end", "skipped", "shuffle", "offline", "incognito", "platform")


def read_rows(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        for name in sorted(z.namelist()):
            base = name.rsplit("/", 1)[-1]
            if base.startswith("Streaming_History_Audio_") and base.endswith(".json"):
                yield from json.loads(z.read(name).decode("utf-8"))


def to_row(r):
    uri = r.get("spotify_track_uri")
    if not uri or r.get("ms_played") is None:
        return None                                   # podcasts and other non-music rows
    platform = (r.get("platform") or "unknown").split(" ")[0].lower()
    return (r["ts"], uri.split(":")[-1], r.get("master_metadata_track_name"),
            r.get("master_metadata_album_artist_name"), r.get("master_metadata_album_album_name"),
            int(r["ms_played"]), r.get("reason_start"), r.get("reason_end"),
            bool(r.get("skipped")), bool(r.get("shuffle")), bool(r.get("offline")), bool(r.get("incognito")), platform)


def main(zip_path):
    load_dotenv(ROOT / ".env")
    conn = psycopg2.connect(host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT"), dbname=os.getenv("DB_NAME"),
                            user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"))
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM raw_streaming_history")
    before = cur.fetchone()[0]

    sql = f"INSERT INTO raw_streaming_history ({', '.join(COLUMNS)}) VALUES %s ON CONFLICT (played_at, track_id) DO NOTHING"
    seen = skipped_rows = 0
    batch = []
    for r in read_rows(zip_path):
        row = to_row(r)
        if row is None:
            skipped_rows += 1
            continue
        batch.append(row)
        seen += 1
        if len(batch) >= BATCH:
            execute_values(cur, sql, batch)
            batch = []
    if batch:
        execute_values(cur, sql, batch)
    conn.commit()

    cur.execute("SELECT count(*), min(played_at), max(played_at) FROM raw_streaming_history")
    after, first, last = cur.fetchone()
    cur.close()
    conn.close()
    print(f"music plays read from the zip: {seen:,} (non-music rows skipped: {skipped_rows:,})")
    print(f"newly stored: {after - before:,} | rows in raw_streaming_history now: {after:,}")
    print(f"covers {first:%Y-%m-%d} to {last:%Y-%m-%d}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python import_history.py <path to my_spotify_data.zip>")
    main(sys.argv[1])
