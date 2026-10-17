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

-- ReccoBeats audio features (estimates, not Spotify's), keyed by Spotify track id.
-- found = false caches a miss so it is not re-requested until retried.
create table if not exists raw_audio_features (
    track_id         text primary key,
    found            boolean     not null,
    first_fetched_at timestamptz not null default now(),  -- never updated; shows when a miss later turned into a hit
    fetched_at       timestamptz not null default now(),   -- last attempt
    reccobeats_id    text,
    isrc             text,
    acousticness     double precision,
    danceability     double precision,
    energy           double precision,
    instrumentalness double precision,
    liveness         double precision,
    loudness         double precision,
    speechiness      double precision,
    tempo            double precision,
    valence          double precision,
    key              int,
    mode             int
);

-- Album cover art per track (url null = looked up, none available).
create table if not exists track_covers (
    track_id   text primary key,
    image_url  text,
    fetched_at timestamptz not null default now()
);

-- Spotify Extended Streaming History (the downloaded export), music plays only.
-- Loaded by import_history.py. The export's IP address and country are deliberately not stored.
create table if not exists raw_streaming_history (
    played_at    timestamptz not null,       -- when the play ended
    track_id     text        not null,
    track_name   text,
    artist_name  text,                       -- album artist, as the export gives it (there is no artist id)
    album_name   text,
    ms_played    integer     not null,
    reason_start text,
    reason_end   text,
    skipped      boolean,
    shuffle      boolean,
    offline      boolean,
    incognito    boolean,
    platform     text,
    unique (played_at, track_id)
);
create index if not exists raw_streaming_history_track_idx on raw_streaming_history (track_id);

-- Day bucketing in dbt marts and the dashboard follows the session timezone.
alter database spotify_data set timezone to 'Asia/Kolkata';
