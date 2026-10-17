-- Lifetime plays: the downloaded history, then the live pipeline from where the history ends.
-- The pipeline only reports the track length, not how long you listened, so those plays count as full plays.
with history as (

    select
        'history' as source,
        played_at, track_id, track_name, artist_name, album_name,
        seconds_played, is_real_play, skipped, platform
    from {{ ref('stg_streaming_history') }}

),

pipeline as (

    select
        'pipeline' as source,
        p.played_at,
        p.track_id,
        p.track_name,
        coalesce(g.artist_name, split_part(p.artist_names, ', ', 1)) as artist_name,
        p.album_name,
        p.duration_ms / 1000.0 as seconds_played,
        true as is_real_play,
        false as skipped,
        'pipeline' as platform
    from {{ ref('stg_recently_played') }} p
    left join {{ source('spotify_raw', 'raw_artist_genres') }} g
        on g.artist_id = p.primary_artist_id
    where p.played_at > (select coalesce(max(played_at), '-infinity'::timestamptz) from history)

)

select * from history
union all
select * from pipeline
