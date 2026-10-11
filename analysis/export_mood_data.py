"""Export the genre-vs-audio mood comparison tables from Postgres to CSV.

Usage (from the repo root, with the dbt models built):
    python analysis/export_mood_data.py

Writes analysis/output/mood_comparison_track.csv and mood_comparison_artist.csv,
which analysis/validate_moods.py and analysis/validate_moods.do both read.
"""
import os
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "output"
TABLES = ["mood_comparison_track", "mood_comparison_artist"]


def main():
    load_dotenv(ROOT / ".env")
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT"), dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
    )
    OUT.mkdir(exist_ok=True)
    for table in TABLES:
        df = pd.read_sql(f"SELECT * FROM dbt_dev.{table} ORDER BY 1", conn)
        path = OUT / f"{table}.csv"
        df.to_csv(path, index=False, encoding="utf-8")
        print(f"{path.name}: {len(df)} rows")
    conn.close()


if __name__ == "__main__":
    main()
