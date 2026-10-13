"""Shared HTML helpers for the Streamlit pages: track names that link to Spotify and show an
album cover card on hover, and small mood badges."""
import html as _html

import covers

SPOTIFY_TRACK_URL = "https://open.spotify.com/track/"

MOOD_COLORS = {
    "calm": "#5B9BD5",
    "mellow": "#1DB954",
    "intense": "#E33A3A",
    "upbeat": "#FFC000",
}


def _esc(v):
    return _html.escape("" if v is None else str(v), quote=True)


def track_cell(track_id, name, artist, album, image, link=False):
    """Track name that shows a card with the album cover when hovered."""
    img = ""
    if image and covers.is_spotify_image(image):
        img = f'<img src="{_esc(image)}" alt="">'
    card = (f'<span class="pop">{img}<b>{_esc(name)}</b>'
            f'<span>{_esc(artist)}</span><span>{_esc(album)}</span></span>')
    label = _esc(name)
    if link:
        label = f'<a href="{SPOTIFY_TRACK_URL}{_esc(track_id)}" target="_blank" rel="noopener">{label}</a>'
    return f'<span class="tt" tabindex="0">{label}{card}</span>'


def mood_badge(mood):
    color = MOOD_COLORS.get(mood, "#999999")
    return (f'<span class="badge" style="background:{color}26;border:1px solid {color};color:{color}">'
            f'{_esc(mood)}</span>')


def tracks_table(df, cols, meta):
    """HTML table with hover cover cards. cols = [(header, key)]; key '__track__' is the track
    name: a link that opens the track in Spotify, with the cover card on hover.
    meta = DataFrame(track_id, album_name, image_url)."""
    d = df.merge(meta, on="track_id", how="left")
    head = "".join(f"<th>{_esc(h)}</th>" for h, _ in cols)
    body = []
    for _, r in d.iterrows():
        tds = []
        for _, key in cols:
            if key == "__track__":
                tds.append(track_cell(r["track_id"], r["track_name"], r["artist_names"], r.get("album_name"), r.get("image_url"), link=True))
            else:
                tds.append(_esc(r[key]))
        body.append("<tr>" + "".join(f"<td>{t}</td>" for t in tds) + "</tr>")
    return f'<table class="tt-table"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'


TRACK_CSS = """<style>
.tt-table{width:100%;border-collapse:collapse;font-size:0.92rem}
.tt-table th{text-align:left;font-weight:600;opacity:.65;padding:6px 10px;border-bottom:1px solid rgba(128,128,128,.35)}
.tt-table td{padding:7px 10px;border-bottom:1px solid rgba(128,128,128,.18);vertical-align:middle}
.tt{position:relative;display:inline-block;font-weight:600;cursor:default;border-bottom:1px dotted rgba(128,128,128,.7)}
.tt a{color:inherit;text-decoration:none}
.tt .pop{display:none;position:absolute;left:0;top:100%;z-index:1000;width:200px;padding:8px;border-radius:10px;background:#101418;color:#f1f3f4;border:1px solid #2c333a;box-shadow:0 8px 24px rgba(0,0,0,.4);font-weight:400;line-height:1.3;white-space:normal}
.tt:hover .pop,.tt:focus-within .pop{display:block}
.tt .pop img{display:block;width:184px;height:184px;object-fit:cover;border-radius:6px;margin-bottom:6px}
.tt .pop b{display:block;font-size:.9rem}
.tt .pop span{display:block;opacity:.75;font-size:.8rem}
.tt a:hover{text-decoration:underline}
.badge{display:inline-block;padding:1px 10px;border-radius:999px;font-size:.82rem;font-weight:600}
.muted{opacity:.7;font-size:.85rem}
</style>"""
