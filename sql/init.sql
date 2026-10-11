-- Raw tables for the pipeline. Columns inferred from ingest.py (INSERTs),
-- dashboard.py (liked_tracks) and spotify_dbt/models/staging/*.sql.
-- Runs automatically on first start of the postgres container (empty volume only).

create table if not exists raw_recently_played (
    played_at         timestamptz not null,
    track_id          text        not null,
    track_name        text,
    artist_names      text,
    primary_artist_id text,
    album_name        text,
    duration_ms       int,
    ingested_at       timestamptz not null default now(),
    unique (played_at, track_id)
);

create table if not exists raw_artist_genres (
    artist_id   text primary key,
    artist_name text,
    genres      text[]
);

-- Written by dashboard.py (toggle_like); not managed by dbt.
create table if not exists liked_tracks (
    track_id     text primary key,
    track_name   text,
    artist_names text,
    liked_at     timestamptz not null default now()
);
