-- One row per track that has BOTH a genre-based mood (via its primary artist's Last.fm
-- tags) and an audio-based mood (ReccoBeats valence x energy). Input to the validation analysis.
with tracks as (

    select
        track_id,
        max(track_name) as track_name,
        max(primary_artist_id) as primary_artist_id,
        count(*) as plays
    from {{ ref('stg_recently_played') }}
    group by track_id

)

select
    t.track_id,
    t.track_name,
    t.primary_artist_id,
    t.plays,
    g.mood as genre_mood,
    a.audio_mood,
    a.valence,
    a.energy
from tracks t
inner join {{ ref('stg_artist_moods') }} g
    on g.artist_id = t.primary_artist_id
inner join {{ ref('stg_track_audio_moods') }} a
    on a.track_id = t.track_id
