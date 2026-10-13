# Changes from the original

This project is built on [sarthakgh29/spotify-mood-pipeline](https://github.com/sarthakgh29/spotify-mood-pipeline) by Sarthak Sharma. The original has no license file. The architecture (Spotify + Last.fm -> Postgres -> dbt -> Prefect -> Streamlit), the original dbt models and the original dashboard are his. This copy was adapted and extended by Johan Chopra, as listed below.

The history here is a fresh start: the original's commits are not included (they contained a committed `logs/dbt.log`).

## Setup and infrastructure
- **`sql/init.sql` (new):** DDL for `raw_recently_played`, `raw_artist_genres`, `liked_tracks` and `raw_audio_features`. The original repo had none. Columns for the first three were inferred from `ingest.py`, `dashboard.py` and the staging SQL. The file is mounted into the Postgres container via `docker-compose.yml` and runs on first start of an empty volume.
- **`requirements.txt`:** replaced the UTF-16, ~150-package freeze (including Windows-only `pywin32`) with a trimmed list of direct dependencies. `sqlalchemy` is pinned below 2.1 because 2.1 defaults to psycopg3 and the dashboard needs psycopg2.
- **`.gitignore`:** added `logs/`, `spotify_dbt/profiles.yml`, `spotify_dbt/target/`, `spotify_dbt/dbt_packages/` and `spotify_dbt/.user.yml`.
- **dbt profile:** `profiles.yml` is created locally (profile `spotify_dbt`, schema `dbt_dev`) and is not committed.
- **Docs:** the README credits the original and links here.

## Data and models
- **`seeds/genre_mood_map.csv`:** extended with about 45 genre-to-mood rows for tags found in Johan's Last.fm data. Place and label tags (e.g. `india`, `canada`) map to `unclassified`.
- **`stg_artist_moods.sql`:** added `mood` as a tie-breaker in the ranking. Without it, an artist with equally many tags in two moods got an arbitrary mood that changed between runs.
- **`daily_top_track`:** now carries `track_id` (needed for the Spotify links).

## Timezone (IST)
- **Database:** `alter database spotify_data set timezone to 'Asia/Kolkata'`, so day bucketing in the dbt marts follows IST. Existing databases need this run by hand, because `init.sql` only runs on an empty volume.
- **`dashboard.py`:** play times, liked-at dates and daily labels are explicitly converted to `Asia/Kolkata`, because pandas converts `timestamptz` to UTC on read.

## ReccoBeats audio features
- **Ingest:** `ingest.py` sends uncached tracks to `https://api.reccobeats.com/v1/audio-features` using Spotify track IDs directly, in batches of 40 (the API's limit; larger requests return HTTP 400). Results go to `raw_audio_features`, keyed by Spotify `track_id`. Tracks ReccoBeats does not know are cached as `found = false` and retried after 3 days (`RECCOBEATS_RETRY_DAYS` in `.env`). Every track ever played is considered on each run, not just the latest 50 plays, so old misses are retried too. `first_fetched_at` is never updated, so a miss that later turns into a hit is visible as `found AND fetched_at > first_fetched_at`. 429 responses honour `Retry-After`.
- **dbt models:** `stg_audio_features`, `stg_track_audio_moods` and the mart `daily_audio_mood_summary`, with tests (feature values in [0, 1], accepted mood values, unique track IDs).
- **Audio mood mapping** (valence x energy, cut-off 0.5): upbeat = high valence + high energy, intense = low valence + high energy, calm = high valence + low energy, mellow = low valence + low energy.
- **Dashboard:** new "Audio mood (ReccoBeats)" section with a coverage caption.
- **Caveats:** the features are ReccoBeats' estimates, not Spotify's. Coverage in Johan's data was 15 of 50 tracks (30%) when first tested. It depends mainly on release year: about 73% for tracks released up to 2024 versus about 11% for 2025 and later. Re-requesting misses (singly or in batch) returned nothing new, so misses are not transient. Spotify's own audio-features endpoint is closed to new apps, which is why ReccoBeats is used.

## Dashboard
- **Spotify links and cover cards:** every track name on the dashboard is a link that opens the track in Spotify, and hovering it shows a card with the album cover, title, artist and album. This applies to all track tables and to "Discovered recently". Covers come from the Spotify payload at ingest, and from Spotify's keyless oEmbed endpoint for older tracks, and are cached in the new `track_covers` table (dbt model `stg_track_covers`). Only Spotify image hosts are accepted (`covers.py`, with tests). The track tables are HTML tables, so they are no longer sortable. "Discovered recently" no longer sits in a scroll box (it would clip the card), and shows the first 15 rows with the rest under an expander.
- **Click a mood block to see its songs:** in "Mood over time", clicking a coloured block (in either the minutes or % view) lists the songs behind it for that day, with cover, artist, plays and minutes, each linking to Spotify. The songs are embedded in the chart, so a click needs no page reload. Minutes match the chart. The same chart, with the same click behaviour, is used for the genre-based mood and for the audio-based mood ("Audio mood (ReccoBeats)", which replaced a plain Plotly bar chart); plays with no mood for that method are not in the chart, so not in the list either.
- **Audio mood section:** see above.
- **IST display:** see above.

## Orchestration (Prefect)
- **`pipeline_flow.py`:** now also fetches artist genres and audio features. The original flow skipped the genre fetch, so scheduled runs never tagged new artists.
- **Schedule:** `serve()` no longer accepts a `timezone` argument in Prefect 3.8, so the flow now uses `Cron("0 20 * * *", timezone="Asia/Kolkata")`.
- **Server required:** Prefect cannot schedule on its ephemeral server. Run `prefect server start` with `PREFECT_API_DATABASE_CONNECTION_URL` pointing at a `prefect_meta` database (created in the same Postgres), then set `PREFECT_API_URL=http://127.0.0.1:4200/api` before `python pipeline_flow.py`. Both processes must stay running, and neither restarts by itself after a reboot.

## Validation analysis: genre-based vs audio-based mood
- **dbt:** marts `mood_comparison_track` (tracks with both a genre mood and an audio mood) and `mood_comparison_artist` (artist audio mood = most common audio mood across their tracks, alphabetical tie-break), with tests.
- **`analysis/`:** `export_mood_data.py` writes both tables to CSV; `validate_moods.py` (pandas + scikit-learn) and `validate_moods.do` (Stata) report percent agreement, a confusion matrix (rows = genre mood, columns = audio mood) and Cohen's kappa at track and artist level. The Python and Stata results match.
- **Run it:** `python analysis/export_mood_data.py`, then `python analysis/validate_moods.py`; for Stata, run `validate_moods.do` from the `analysis/` folder. Generated CSVs and Stata logs are gitignored.
- **First result (11 tracks, 7 artists):** 54.5% agreement and kappa 0.07 at track level; 42.9% and kappa 0.03 at artist level. With this few rows, and the genre mood labelling 10 of 11 tracks "intense", kappa is unstable and should not be over-read. ReccoBeats coverage also skews toward older tracks.
- **Tests:** `tests/test_mood_stats.py` checks kappa against a hand-computed example.
- `scikit-learn` was added to `requirements.txt`.

## Known issues carried over from the original
- Spotify's recently-played endpoint returns at most 50 plays, so the pipeline must run regularly to avoid gaps. One run a day can lose plays on heavy-listening days.
- The README's "11 dbt tests" is out of date (30 now).

## Optional: weekly mood cat meme (not practical)

> **Flag: not practical.** This is a novelty feature. It depends on a free third-party service (CATAAS) whose tags are user-submitted and unfiltered, so an unwanted image can slip through, and it adds a network call to every dashboard load. The pool of cats per mood is small. Treat it as optional and disable it if you share or host the dashboard.

- **What it does:** `cat_meme.py` picks the dominant genre-based mood of the last 7 days, queries [CATAAS](https://cataas.com) for cats tagged with matching words, and the dashboard shows one in the top right with a meme caption.
- **Behaviour:** the pick is deterministic per ISO week and cached for 6 hours. Cats carrying blocked tags are skipped, which reduces but cannot remove the risk. If CATAAS is down, an emoji card is shown instead.
- **Turn it off:** set `CAT_MEME=off`.
- **CATAAS quirk:** its `/says/` caption endpoint returns HTTP 500 when `width` is set, so captions are drawn in HTML over the plain image.
- **Tests:** `python -m unittest discover tests`.
