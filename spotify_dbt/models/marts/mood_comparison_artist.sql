-- One row per artist with a genre mood and at least one track with an audio mood.
-- The artist's audio mood is the most common audio mood across their tracks
-- (alphabetical tie-break, so it is deterministic).
with counted as (

    select
        primary_artist_id,
        genre_mood,
        audio_mood,
        count(*) as n_tracks
    from {{ ref('mood_comparison_track') }}
    group by primary_artist_id, genre_mood, audio_mood

),

ranked as (

    select
        *,
        row_number() over (
            partition by primary_artist_id
            order by n_tracks desc, audio_mood
        ) as rn,
        sum(n_tracks) over (partition by primary_artist_id) as n_tracks_with_audio
    from counted

)

select
    r.primary_artist_id,
    g.artist_name,
    r.genre_mood,
    r.audio_mood,
    r.n_tracks_with_audio
from ranked r
inner join {{ ref('stg_artist_moods') }} g
    on g.artist_id = r.primary_artist_id
where r.rn = 1
