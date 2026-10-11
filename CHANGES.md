# Changes from the original

This project is built on [sarthakgh29/spotify-mood-pipeline](https://github.com/sarthakgh29/spotify-mood-pipeline) by Sarthak Sharma. The original has no license file. The architecture (Spotify + Last.fm -> Postgres -> dbt -> Prefect -> Streamlit), the dbt models and the dashboard are his. This copy was adapted and extended by Johan Chopra, as listed below.

The history here is a fresh start: the original's commits are not included.

## Setup and infrastructure
- **`sql/init.sql` (new):** DDL for `raw_recently_played`, `raw_artist_genres` and `liked_tracks`. The original repo had none. Columns were inferred from `ingest.py`, `dashboard.py` and the staging SQL. It is mounted into the Postgres container via `docker-compose.yml`.
- **`requirements.txt`:** replaced the UTF-16, ~150-package freeze (including Windows-only `pywin32`) with a trimmed list of direct dependencies. `sqlalchemy` is pinned below 2.1 because 2.1 defaults to psycopg3 and the dashboard needs psycopg2.
- **`.gitignore`:** added `logs/`, `spotify_dbt/profiles.yml`, `spotify_dbt/target/`, `spotify_dbt/dbt_packages/` and `spotify_dbt/.user.yml`. The original committed `logs/dbt.log`.
- **dbt profile:** `profiles.yml` is created locally (profile `spotify_dbt`, schema `dbt_dev`) and is not committed.

## Data and models
- **`seeds/genre_mood_map.csv`:** extended with about 45 genre-to-mood rows for tags found in Johan's Last.fm data. Place and label tags (e.g. `india`, `canada`) map to `unclassified`.
- **`stg_artist_moods.sql`:** added `mood` as a tie-breaker in the ranking. Without it, an artist with equally many tags in two moods got an arbitrary mood that changed between runs.

## Timezone (IST)
- **Database:** `alter database spotify_data set timezone to 'Asia/Kolkata'`, so day bucketing in the dbt marts follows IST.
- **`dashboard.py`:** play times, liked-at dates and daily labels are explicitly converted to `Asia/Kolkata`, because pandas converts `timestamptz` to UTC on read.

## Known issues carried over from the original
- `pipeline_flow.py` does not call `fetch_and_load_artist_genres`, so the scheduled run does not fetch genres for new artists. Only a manual `python ingest.py` does.
- Spotify's recently-played endpoint returns at most 50 plays, so the pipeline must run regularly to avoid gaps.
