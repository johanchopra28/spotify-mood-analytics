# Changes from the original

This project is built on [sarthakgh29/spotify-mood-pipeline](https://github.com/sarthakgh29/spotify-mood-pipeline) by Sarthak Sharma. The original has no license file. The architecture (Spotify + Last.fm -> Postgres -> dbt -> Prefect -> Streamlit), the original dbt models and the original dashboard are his. This copy was adapted and extended by Johan Chopra.

This file reads in order: first what Sarthak's original already did, then everything added on top, in the order it was built. The history here is a fresh start: the original's commits are not included (they contained a committed `logs/dbt.log`).

## Where this started: Sarthak's original
- **Ingest:** `ingest.py` pulls the last 50 recently played tracks from Spotify and each artist's tags from Last.fm into Postgres (running in Docker).
- **dbt:** staging models and marts, a hand-made genre-to-mood seed (`calm`, `mellow`, `intense`, `upbeat`) and data tests.
- **Orchestration:** a Prefect flow (ingest, `dbt run`, `dbt test`) on a daily schedule.
- **Dashboard:** a Streamlit app with the daily mood, listening stats, top tracks, a "Discovered recently" list and likes stored in a `liked_tracks` table.
- **What it did not have:** table definitions, a working dbt profile, a clean requirements file, time-zone handling, or audio features (Spotify's own audio-features endpoint is closed to new apps).

## What was added, in order

### 1. Getting it running
- **`sql/init.sql` (new):** DDL for `raw_recently_played`, `raw_artist_genres`, `liked_tracks` and, later, `raw_audio_features` and `track_covers`. The original repo had none. Columns for the first three were inferred from `ingest.py`, `dashboard.py` and the staging SQL. The file is mounted into the Postgres container via `docker-compose.yml` and runs on first start of an empty volume.
- **`requirements.txt`:** replaced the UTF-16, ~150-package freeze (including Windows-only `pywin32`) with a trimmed list of direct dependencies. `sqlalchemy` is pinned below 2.1 because 2.1 defaults to psycopg3 and the dashboard needs psycopg2. `scikit-learn` was added for the validation analysis.
- **`.gitignore`:** added `logs/`, `spotify_dbt/profiles.yml`, `spotify_dbt/target/`, `spotify_dbt/dbt_packages/`, `spotify_dbt/.user.yml`, `analysis/output/` and `analysis/*.log` (the Stata log contains licence details).
- **dbt profile:** `profiles.yml` is created locally (profile `spotify_dbt`, schema `dbt_dev`) and is not committed.
- **Docs:** the README credits the original, and was rewritten (stale test count, missing setup steps, broken characters).

### 2. Tuning the genre moods to Johan's listening
- **`seeds/genre_mood_map.csv`:** extended with about 45 genre-to-mood rows for tags found in Johan's Last.fm data. Place and label tags (e.g. `india`, `canada`) map to `unclassified`.
- **`stg_artist_moods.sql`:** added `mood` as a tie-breaker in the ranking. Without it, an artist with equally many tags in two moods got an arbitrary mood that changed between runs.

### 3. Time zone (IST)
- **Database:** `alter database spotify_data set timezone to 'Asia/Kolkata'`, so day bucketing in the dbt marts follows IST. Existing databases need this run by hand, because `init.sql` only runs on an empty volume.
- **Dashboard (`pages/0_Dashboard.py`, formerly `dashboard.py`):** play times, liked-at dates and daily labels are explicitly converted to `Asia/Kolkata`, because pandas converts `timestamptz` to UTC on read.

### 4. ReccoBeats audio features
- **Ingest:** `ingest.py` sends uncached tracks to `https://api.reccobeats.com/v1/audio-features` using Spotify track IDs directly, in batches of 40 (the API's limit; larger requests return HTTP 400). Results go to `raw_audio_features`, keyed by Spotify `track_id`. Tracks ReccoBeats does not know are cached as `found = false` and retried after 3 days (`RECCOBEATS_RETRY_DAYS` in `.env`). Every track ever played is considered on each run, not just the latest 50 plays, so old misses are retried too. `first_fetched_at` is never updated, so a miss that later turns into a hit is visible as `found AND fetched_at > first_fetched_at`. 429 responses honour `Retry-After`.
- **dbt models:** `stg_audio_features`, `stg_track_audio_moods` and the mart `daily_audio_mood_summary`, with tests (feature values in [0, 1], accepted mood values, unique track IDs).
- **Audio mood mapping** (valence x energy, cut-off 0.5): upbeat = high valence + high energy, intense = low valence + high energy, calm = high valence + low energy, mellow = low valence + low energy.
- **Dashboard:** a new "Audio mood (ReccoBeats)" section with a coverage caption.
- **Caveats:** the features are ReccoBeats' estimates, not Spotify's. Coverage in Johan's data was 15 of 50 tracks (30%) when first tested. It depends mainly on release year: about 73% for tracks released up to 2024 versus about 11% for 2025 and later. Re-requesting misses (singly or in batch) returned nothing new, so misses are not transient. Spotify's own audio-features endpoint is closed to new apps, which is why ReccoBeats is used.

### 5. Spotify links, cover art and hover cards
- **Spotify links and cover cards:** every track name on the dashboard is a link that opens the track in Spotify, and hovering it shows a card with the album cover, title, artist and album. This applies to all track tables and to "Discovered recently". Covers come from the Spotify payload at ingest, and from Spotify's keyless oEmbed endpoint for older tracks, and are cached in the new `track_covers` table (dbt model `stg_track_covers`). Only Spotify image hosts are accepted (`covers.py`, with tests). The track tables are HTML tables, so they are no longer sortable. "Discovered recently" no longer sits in a scroll box (it would clip the card), and shows the first 15 rows with the rest under an expander.
- **`daily_top_track`:** now carries `track_id` (needed for the links).

### 6. Scheduling with Prefect
- **`pipeline_flow.py`:** now also fetches artist genres, audio features and album covers. The original flow skipped the genre fetch, so scheduled runs never tagged new artists.
- **Schedule:** `serve()` no longer accepts a `timezone` argument in Prefect 3.8, so the flow now uses `Cron("0 20 * * *", timezone="Asia/Kolkata")`.
- **Server required:** Prefect cannot schedule on its ephemeral server. Run `prefect server start` with `PREFECT_API_DATABASE_CONNECTION_URL` pointing at a `prefect_meta` database (created in the same Postgres), then set `PREFECT_API_URL=http://127.0.0.1:4200/api` before `python pipeline_flow.py`. Both processes must stay running, and neither restarts by itself after a reboot.

### 7. Validation analysis: genre-based vs audio-based mood
- **dbt:** marts `mood_comparison_track` (tracks with both a genre mood and an audio mood) and `mood_comparison_artist` (artist audio mood = most common audio mood across their tracks, alphabetical tie-break), with tests.
- **`analysis/`:** `export_mood_data.py` writes both tables to CSV; `validate_moods.py` (pandas + scikit-learn) and `validate_moods.do` (Stata) report percent agreement, a confusion matrix (rows = genre mood, columns = audio mood) and Cohen's kappa at track and artist level. The Python and Stata results match.
- **Run it:** `python analysis/export_mood_data.py`, then `python analysis/validate_moods.py`; for Stata, run `validate_moods.do` from the `analysis/` folder. Generated CSVs and Stata logs are gitignored.
- **First result (11 tracks, 7 artists):** 54.5% agreement and kappa 0.07 at track level; 42.9% and kappa 0.03 at artist level. With this few rows, and the genre mood labelling 10 of 11 tracks "intense", kappa is unstable and should not be over-read. ReccoBeats coverage also skews toward older tracks. The sample has since grown (about 96 songs with both labels), and the Label Comparison page below shows the current figures.
- **Tests:** `tests/test_mood_stats.py` checks kappa against a hand-computed example.

### 8. Clickable mood charts
- **Click a mood block to see its songs:** in "Mood over time", clicking a coloured block (in either the minutes or % view) lists the songs behind it for that day, with cover, artist, plays and minutes, each linking to Spotify. The songs are embedded in the chart, so a click needs no page reload. Minutes match the chart.
- **Same chart for the audio mood:** "Audio mood (ReccoBeats)" uses the same chart, with the same click behaviour (it replaced a plain Plotly bar chart). Plays with no mood for that method are not in the chart, so not in the list either.

### 9. The "Label Comparison" page
For songs that have both a Last.fm-based genre mood and a ReccoBeats audio mood, it shows the agreement rate and Cohen's kappa, a confusion matrix, a valence/energy scatter coloured by the Last.fm label, and a song-by-song table (cover card, artist, the artist's Last.fm tags, both labels, valence, energy, same or differs) with filters. Below that, three toggles hold the detail: **Last.fm** (the votes behind each artist's label, with a chart and a tag-by-tag table), **ReccoBeats** (a sortable table of all nine ratings per song, with a bar for each 0-to-1 value) and **The math** (the formulas in LaTeX with a worked example). The shared hover-card helpers live in `track_ui.py`.

### 10. The "Song Lookup" page
Paste a Spotify song link to see the song's details, all of ReccoBeats' ratings and the audio mood, Last.fm's tags with weights, votes and genre mood for every credited artist, and whether the two labels agree. Song details come from Spotify's public track data (client credentials, so no personal login is needed), the ratings from ReccoBeats and the tags from Last.fm. Nothing is saved to the database. Logic is in `lookup.py`, with tests in `tests/test_lookup.py`.

### 11. Top navigation
The pages are reached from a horizontal tab bar (Dashboard, Label Comparison, Song Lookup) instead of the sidebar. `dashboard.py` is now a small router using `st.navigation(..., position="top")`, and the dashboard itself moved to `pages/0_Dashboard.py`. `streamlit run dashboard.py` still starts everything.

### 12. Keeping it running
- **Database connections recover by themselves:** the dashboard pages create their SQLAlchemy engines with `pool_pre_ping=True` and `pool_recycle=300`. Before this, a database restart (for example Docker being closed and reopened) left the cached connection broken and every page showed `PendingRollbackError` until Streamlit was restarted.
- **Local start-up helpers (not committed):** three small Windows scripts live in the project folder on Johan's machine and are listed in the local `.git/info/exclude`, so git does not see them.
  - **`start_all.bat`** (the steps are in `start_all.ps1`) starts or repairs everything, in order: Docker Desktop (if closed), the Postgres container, the Prefect server (restarted if it cannot reach its database), the daily flow, the dashboard, and finally a fetch of the latest plays. Anything already running and healthy is left alone, so it is safe to run at any time. `-SkipIngest` skips the final fetch.
  - **`start_localhost.bat`** is the lighter version for when only the dashboard is down: Docker, Postgres and the dashboard, then it opens http://localhost:8501. It runs `start_all.ps1 -DashboardOnly -Open`.
  - Both call PowerShell with `-ExecutionPolicy Bypass` for that one run only, so no Windows setting is changed.
  - Spotify's recently-played endpoint only returns the last 50 plays, so the fetch saves only plays that are not already stored, and plays beyond the last 50 since the previous run are lost.
- **`conversations.md`:** a personal running list of ideas and parked topics, also kept out of git locally.

## Optional: weekly mood cat meme (not practical)

> **Flag: not practical.** This is a novelty feature. It depends on a free third-party service (CATAAS) whose tags are user-submitted and unfiltered, so an unwanted image can slip through, and it adds a network call to every dashboard load. The pool of cats per mood is small. Treat it as optional and disable it if you share or host the dashboard.

- **What it does:** `cat_meme.py` picks the dominant genre-based mood of the last 7 days, queries [CATAAS](https://cataas.com) for cats tagged with matching words, and the dashboard shows one in the top right with a meme caption.
- **Behaviour:** the pick is deterministic per ISO week and cached for 6 hours. Cats carrying blocked tags are skipped, which reduces but cannot remove the risk. If CATAAS is down, an emoji card is shown instead.
- **Turn it off:** set `CAT_MEME=off`.
- **CATAAS quirk:** its `/says/` caption endpoint returns HTTP 500 when `width` is set, so captions are drawn in HTML over the plain image.
- **Tests:** `python -m unittest discover tests`.

## Known issues carried over from the original
- Spotify's recently-played endpoint returns at most 50 plays, so the pipeline must run regularly to avoid gaps. One run a day can lose plays on heavy-listening days.
