-- Audio-based counterpart of daily_mood_summary (genre-based).
select
    date_trunc('day', p.played_at) as listen_date,
    m.audio_mood as mood,
    count(*) as plays,
    round(sum(p.duration_minutes)::numeric, 1) as minutes_listened
from {{ ref('stg_recently_played') }} p
inner join {{ ref('stg_track_audio_moods') }} m
    on p.track_id = m.track_id
group by 1, 2
order by 1 desc, minutes_listened desc
