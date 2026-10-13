# Spotify Mood Pipeline

> Based on [sarthakgh29/spotify-mood-pipeline](https://github.com/sarthakgh29/spotify-mood-pipeline) by Sarthak Sharma (no license file in the original). This copy is adapted and extended for personal use.

An end-to-end data pipeline that turns Spotify listening history into a daily "mood" signal, with an interactive dashboard for exploring and reacting to it.

**Fetch -> land in Postgres -> transform with dbt -> orchestrate with Prefect -> visualize with Streamlit.**

## What changed from the original

This copy keeps Sarthak's architecture and adds the following. The full list, with reasons, is in [CHANGES.md](CHANGES.md).

* **ReccoBeats audio features** (valence, energy and more) and an audio-based mood next to the genre-based mood. Spotify's own audio-features endpoint is closed to new apps.
* **A genre-vs-audio validation analysis** (percent agreement, confusion matrix, Cohen's kappa) in Python and Stata.
* **Album cover cards** on hover, and every track name links to Spotify.
* **IST time handling**, an extended genre seed, `sql/init.sql` (the original had no table definitions), and a trimmed `requirements.txt`.
* **Fixes:** deterministic artist moods, and the scheduled flow now fetches genres and audio features.
* **Optional extra:** a weekly mood cat meme on the dashboard (`CAT_MEME=off` disables it).

## Architecture

```
Spotify API (recently played) --+
Last.fm API (artist genres) ----+--> ingest.py --> Postgres (public schema)
ReccoBeats API (audio features) +                        |
Spotify oEmbed (cover art) -----+                      dbt models
                                                           |
                                          Postgres (dbt_dev schema) --> Streamlit dashboard
                                                           |                 ^
                                                           +--> analysis/ (CSV export, Python + Stata)
                                               Prefect schedules + orchestrates
                                               Docker Compose runs Postgres
```

## What it does

* Pulls recently played tracks from the Spotify API
* Enriches each track's artist with genre tags from Last.fm
* Maps genres to one of four mood categories (`calm`, `mellow`, `intense`, `upbeat`) via a hand-curated dbt seed
* Looks up ReccoBeats audio features per track and derives a second, audio-based mood from valence and energy quadrants
* Rolls plays up into daily listening stats, a daily "dominant mood" and a daily audio mood
* Surfaces "Discovered recently": tracks new to the listening history in the last 7 days that have already been replayed
* Lets the user like tracks from the discovery list, persisted to Postgres from the dashboard itself (this does not change anything on Spotify)
* Shows track names as Spotify links with an album cover card on hover
* Displays it all on an interactive Streamlit dashboard, with an animated mood chart and smooth in-page navigation
* Runs on a daily schedule via Prefect (20:00 IST), with retries and dbt tests guarding data quality

## A real API surprise along the way

The original plan was to use Spotify's audio-features endpoint (valence, energy, danceability) to derive mood directly. Spotify deprecated that endpoint for all new apps in November 2024, with no official replacement. Spotify's artist `genres` field has also been returning empty or null for most artists.

The pipeline therefore uses Last.fm's community-tagged artist genres, paired with a hand-built genre-to-mood mapping (`seeds/genre_mood_map.csv`). ReccoBeats' free audio features are added as a second signal. They are ReccoBeats' estimates, not Spotify's, and coverage is partial: it depends mainly on release year, and in this project's data about 73% of tracks released up to 2024 were found against about 11% of 2025 releases.

## Tech stack

|Tool|Role|
|-|-|
|Python (`spotipy`, `requests`)|API ingestion|
|PostgreSQL (Docker)|Storage|
|dbt|Transformation, testing, documentation|
|Prefect|Orchestration and scheduling|
|Streamlit + Plotly|Interactive dashboard|
|Last.fm API|Genre data|
|ReccoBeats API|Audio features (valence, energy, ...)|
|pandas + scikit-learn, Stata|Validation analysis|

## Project structure

```
spotify-mood-pipeline/
  ingest.py                  - fetch, transform, load (Spotify, Last.fm, ReccoBeats, cover art)
  covers.py                  - album cover lookup and validation
  pipeline_flow.py           - Prefect flow: ingest -> dbt run -> dbt test
  dashboard.py               - Streamlit dashboard
  cat_meme.py                - optional weekly mood cat meme
  docker-compose.yml         - Postgres container (runs sql/init.sql on first start)
  sql/init.sql               - table definitions
  requirements.txt
  .env.example
  analysis/                  - genre-vs-audio validation (export, Python, Stata)
  tests/                     - Python unit tests
  CHANGES.md                 - what differs from the original
  spotify_dbt/
    seeds/
      genre_mood_map.csv     - hand-curated genre -> mood mapping
    models/
      staging/               - stg_recently_played, stg_artist_moods, stg_audio_features,
                               stg_track_audio_moods, stg_track_covers
      marts/                 - daily_listening_summary, daily_mood_summary, daily_dominant_mood,
                               daily_top_track, daily_audio_mood_summary,
                               mood_comparison_track, mood_comparison_artist
```

## User-generated data

`liked_tracks` is a Postgres table written to directly by the Streamlit dashboard (not managed by dbt). It stores songs the user has liked from the "Discovered recently" section. Unlike the dbt-managed marts, which are fully re-derived from raw data on every run, this table holds durable user state that persists independently of the pipeline. Likes stay in Postgres; nothing is written to Spotify.

## Data quality

* **45 dbt tests.** Not-null and uniqueness checks on key fields, a composite-uniqueness check on `(played_at, track_id)` so ingest is idempotent, `accepted_values` checks that every mood is one of the four categories, and range checks that audio features stay within 0 to 1.
* **17 Python unit tests** (`python -m unittest discover tests`) covering the weekly cat pick, cover-URL validation and the agreement statistics, including a hand-computed kappa.

## Setup

1. Clone the repo, create a venv and install: `python -m venv venv`, then `venv/Scripts/python.exe -m pip install -r requirements.txt` (use `python -m pip`, so packages land in the venv)
2. Create a Spotify Developer app (redirect URI `http://127.0.0.1:8888/callback`) and a Last.fm API key. Copy `.env.example` to `.env` and fill in the credentials. `.env` is gitignored, so never commit it
3. `docker compose up -d` starts Postgres and creates the tables from `sql/init.sql` on first start
4. Create `spotify_dbt/profiles.yml` (it is gitignored): profile `spotify_dbt`, type `postgres`, host `localhost`, port `5432`, user `spotify_user`, password `spotify_pass`, dbname `spotify_data`, schema `dbt_dev`
5. `python ingest.py` for a first fetch. The first run opens a browser tab to approve Spotify access
6. `cd spotify_dbt`, then `dbt deps`, `dbt seed`, `dbt run`, `dbt test`
7. `streamlit run dashboard.py`
8. Optional daily schedule (Prefect needs a real server to schedule runs): create a `prefect_meta` database in the same Postgres, run `prefect server start` with `PREFECT_API_DATABASE_CONNECTION_URL=postgresql+asyncpg://spotify_user:spotify_pass@localhost:5432/prefect_meta`, set `PREFECT_API_URL=http://127.0.0.1:4200/api`, then run `python pipeline_flow.py`
9. Optional validation analysis: `python analysis/export_mood_data.py`, then `python analysis/validate_moods.py` (for Stata, run `analysis/validate_moods.do` from the `analysis/` folder)

## Known limitations

* Spotify's "recently played" endpoint only returns the last 50 plays, so the pipeline has to run often enough to avoid gaps. Plays missed while it is not running are lost for good
* The pipeline only runs while the machine, Docker, the Prefect server and the flow process are all on. None of them restarts by itself after a reboot, and a missed 20:00 run is not caught up
* Genre coverage depends on Last.fm's community tagging. Smaller or newer artists are often untagged, and the genre mood is per artist, not per track
* ReccoBeats does not know every track, and coverage drops sharply for recent releases. Its values are estimates. The genre-vs-audio comparison therefore describes a non-random slice of the listening history, and kappa is unstable on small samples
* Prefect's own metadata is stored in a dedicated Postgres database (`prefect_meta`) rather than its SQLite default, after a SQLite lock-contention problem caused a scheduled run to fail silently under concurrent access
