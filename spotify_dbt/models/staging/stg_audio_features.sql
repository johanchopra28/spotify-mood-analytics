-- Tracks ReccoBeats knows about. Cached misses (found = false) are excluded.
select
    track_id,
    reccobeats_id,
    isrc,
    acousticness,
    danceability,
    energy,
    instrumentalness,
    liveness,
    loudness,
    speechiness,
    tempo,
    valence,
    key,
    mode,
    fetched_at
from {{ source('spotify_raw', 'raw_audio_features') }}
where found
