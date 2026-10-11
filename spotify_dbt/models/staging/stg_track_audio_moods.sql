-- Audio-based mood from valence x energy quadrants (cut-off 0.5):
--   high valence, high energy -> upbeat     low valence, high energy -> intense
--   high valence, low energy  -> calm       low valence, low energy  -> mellow
select
    track_id,
    valence,
    energy,
    case
        when valence >= 0.5 and energy >= 0.5 then 'upbeat'
        when valence <  0.5 and energy >= 0.5 then 'intense'
        when valence >= 0.5 and energy <  0.5 then 'calm'
        else 'mellow'
    end as audio_mood
from {{ ref('stg_audio_features') }}
where valence is not null and energy is not null
