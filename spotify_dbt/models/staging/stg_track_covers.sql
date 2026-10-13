select
    track_id,
    image_url
from {{ source('spotify_raw', 'track_covers') }}
where image_url is not null
