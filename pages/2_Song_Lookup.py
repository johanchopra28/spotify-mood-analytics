"""Third page: paste a Spotify song link and see what Spotify, ReccoBeats and Last.fm say about it."""
import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

import covers
import lookup
from track_ui import MOOD_COLORS, TRACK_CSS, _esc, mood_badge

load_dotenv(ROOT / ".env")
MOODS = lookup.MOODS

st.markdown(TRACK_CSS, unsafe_allow_html=True)
st.markdown(
    "<style>.chip{display:inline-block;margin:1px 4px 1px 0;padding:0 8px;border-radius:999px;border:1px solid;"
    "font-size:.8rem}.chip.ign{border-style:dashed;opacity:.55}</style>", unsafe_allow_html=True)


# ------------------------------------------------------------------ cached lookups
@st.cache_data
def load_seed():
    """Tag -> mood, from the same seed file dbt uses."""
    out = {}
    with open(ROOT / "spotify_dbt" / "seeds" / "genre_mood_map.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["mood"] != "unclassified":
                out[r["genre"].strip().lower()] = r["mood"]
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def get_track(tid):
    return lookup.fetch_spotify_track(tid)


@st.cache_data(ttl=3600, show_spinner=False)
def get_recco(tid):
    return lookup.fetch_reccobeats(tid)


@st.cache_data(ttl=3600, show_spinner=False)
def get_lf_artist(name):
    return lookup.lastfm_artist(name, os.getenv("LASTFM_API_KEY"))


@st.cache_data(ttl=3600, show_spinner=False)
def get_lf_track(artist, track):
    return lookup.lastfm_track(artist, track, os.getenv("LASTFM_API_KEY"))


@st.cache_resource
def get_engine():
    return create_engine(
        f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}",
        pool_pre_ping=True, pool_recycle=300)  # recover on its own after the database restarts


def play_history(tid):
    """How many times this song is in the user's own history (None if the database is unreachable)."""
    try:
        q = text("SELECT count(*) AS plays, min(played_at) AS first_play, max(played_at) AS last_play "
                 "FROM dbt_dev.stg_recently_played WHERE track_id = :t")
        return pd.read_sql(q, get_engine(), params={"t": tid}).iloc[0]
    except Exception:
        return None


def fmt_ms(ms):
    return f"{ms // 60000}:{(ms // 1000) % 60:02d}" if ms else "unknown"


# ------------------------------------------------------------------ page
st.title("Song lookup")
st.markdown(
    "Paste a Spotify song link. This page asks ReccoBeats for its audio ratings and Last.fm for the artist's tags, "
    "then shows the mood each method gives the song. Nothing is saved: a looked-up song is not added to your listening history."
)
link = st.text_input("Spotify song link", placeholder="https://open.spotify.com/track/...", key="song_link")

if not link.strip():
    st.info("In Spotify, open a song, choose Share, then Copy Song Link, and paste it above.")
    st.stop()

tid = lookup.parse_track_id(link)
if not tid:
    st.error("That does not look like a Spotify song link. It should look like https://open.spotify.com/track/... "
             "(album, artist and playlist links do not work here).")
    st.stop()

try:
    with st.spinner("Asking Spotify..."):
        track = get_track(tid)
except lookup.LookupFailed as exc:
    st.error(str(exc))
    st.stop()

# ---- the song
c_img, c_info = st.columns([1, 3])
with c_img:
    if track["image"] and covers.is_spotify_image(track["image"]):
        st.image(track["image"], width=200)
with c_info:
    st.subheader(track["name"])
    st.markdown(f"**{', '.join(a['name'] for a in track['artists'])}**")
    bits = [track["album"], track["release_date"], fmt_ms(track["duration_ms"])]
    st.caption(" | ".join(str(b) for b in bits if b))
    if track["isrc"]:
        st.caption(f"ISRC {track['isrc']}")
    st.link_button("Open in Spotify", track["url"])
    hist = play_history(tid)
    if hist is not None and int(hist["plays"]) > 0:
        first = pd.Timestamp(hist["first_play"]).tz_convert("Asia/Kolkata").strftime("%d %b")
        last = pd.Timestamp(hist["last_play"]).tz_convert("Asia/Kolkata").strftime("%d %b")
        st.success(f"In your history: played {int(hist['plays'])} time(s), first {first}, last {last}.")

# ---- ReccoBeats
st.divider()
st.subheader("ReccoBeats")
rec, rec_error = None, None
try:
    with st.spinner("Asking ReccoBeats..."):
        rec = get_recco(tid)
except lookup.LookupFailed as exc:
    rec_error = str(exc)

audio = None
if rec_error:
    st.warning(rec_error)
elif rec is None:
    year = (track["release_date"] or "")[:4]
    st.info("ReccoBeats does not have this song, so there are no audio ratings. "
            + (f"It was released in {year}; in your own listening, ReccoBeats knew far fewer 2025 and 2026 releases than older ones."
               if year.isdigit() and int(year) >= 2025 else ""))
else:
    rows = [{"Rating": label, "Value": rec.get(key), "What it means": meaning}
            for key, label, meaning in lookup.FEATURES if rec.get(key) is not None]
    st.dataframe(
        pd.DataFrame(rows), hide_index=True, width="stretch",
        column_config={"Value": st.column_config.NumberColumn("Value", format="%.3f")},
    )
    v, e = rec.get("valence"), rec.get("energy")
    audio = lookup.audio_mood(v, e)
    if audio:
        st.markdown(f"**Audio mood:** {mood_badge(audio)}", unsafe_allow_html=True)
        st.latex(r"v=%.3f,\ e=%.3f\ \Rightarrow\ \text{%s}" % (v, e, audio))
        st.caption("Valence at or above 0.5 means positive, energy at or above 0.5 means energetic; "
                   "the four combinations are upbeat, intense, calm and mellow.")

# ---- Last.fm
st.divider()
st.subheader("Last.fm")
seed = load_seed()
st.caption("Last.fm tags artists, not songs. The genre mood is a vote among the artist's top tags "
           "(at most five, each with a weight of at least 10), using the seed list. The pipeline uses the **first-listed artist**.")

genre, primary_name = None, track["artists"][0]["name"] if track["artists"] else None
artist_results = {}
for i, art in enumerate(track["artists"]):
    name = art["name"]
    try:
        with st.spinner(f"Asking Last.fm about {name}..."):
            info = get_lf_artist(name)
    except lookup.LookupFailed as exc:
        st.warning(f"{name}: {exc}")
        continue
    v = lookup.vote(info["tags"], seed)
    artist_results[name] = (info, v)
    if i == 0:
        genre = v["winner"]
    with st.expander(f"{name}" + ("  (first-listed artist, used for the genre mood)" if i == 0 else ""), expanded=(i == 0)):
        if not info["found"]:
            st.info("Last.fm has no data for this artist.")
            continue
        m1, m2 = st.columns(2)
        m1.metric("Listeners", f"{info['listeners']:,}" if info["listeners"] else "n/a")
        m2.metric("Scrobbles", f"{info['playcount']:,}" if info["playcount"] else "n/a")
        if info["tags"]:
            tag_df = pd.DataFrame({
                "Tag": [t["tag"] for t in v["per_tag"]],
                "Weight": [t["weight"] for t in v["per_tag"]],
                "Used in the vote": ["yes" if t["used"] else "no" for t in v["per_tag"]],
                "Mood from the seed list": [t["mood"] or ("none (ignored)" if t["used"] else "") for t in v["per_tag"]],
            })
            st.dataframe(tag_df, hide_index=True, width="stretch", column_config={
                "Weight": st.column_config.ProgressColumn("Weight", min_value=0, max_value=100, format="%d")})
            votes = " &middot; ".join(f"{k} {v['counts'][k]}" for k in MOODS)
            label = mood_badge(v["winner"]) if v["winner"] else '<span class="muted">no mood</span>'
            st.markdown(f"**Votes:** {votes}  \n**Genre mood:** {label} "
                        f'<span class="muted">({_esc(v["how"])})</span>', unsafe_allow_html=True)
        else:
            st.info("Last.fm has no tags for this artist, so there is no genre mood.")
        if info["similar"]:
            st.markdown("**Similar artists:** " + ", ".join(_esc(s) for s in info["similar"]), unsafe_allow_html=True)

if primary_name:
    try:
        tr = get_lf_track(primary_name, track["name"])
    except lookup.LookupFailed as exc:
        tr = None
        st.warning(f"Song-level data: {exc}")
    if tr is not None:
        with st.expander("Song-level data from Last.fm"):
            if not tr["found"]:
                st.info("Last.fm has nothing about this exact song.")
            else:
                t1, t2 = st.columns(2)
                t1.metric("Song listeners", f"{tr['listeners']:,}" if tr["listeners"] else "n/a")
                t2.metric("Song scrobbles", f"{tr['playcount']:,}" if tr["playcount"] else "n/a")
                if tr["tags"]:
                    st.dataframe(pd.DataFrame(tr["tags"], columns=["Tag", "Weight"]), hide_index=True, width="stretch")
                else:
                    st.caption("No song-level tags. For most of the songs in your history Last.fm has none, so the artist's tags are used.")

# ---- comparison
st.divider()
st.subheader("Do the two methods agree?")
b1, b2, b3 = st.columns(3)
b1.markdown("**Last.fm genre mood**")
b1.markdown(mood_badge(genre) if genre else '<span class="muted">none</span>', unsafe_allow_html=True)
b2.markdown("**ReccoBeats audio mood**")
b2.markdown(mood_badge(audio) if audio else '<span class="muted">none</span>', unsafe_allow_html=True)
b3.markdown("**Result**")
if genre and audio:
    b3.markdown('<span style="color:#1DB954;font-weight:600">Same label</span>' if genre == audio
                else '<span style="color:#FFC000;font-weight:600">Different labels</span>', unsafe_allow_html=True)
else:
    b3.markdown('<span class="muted">needs both labels</span>', unsafe_allow_html=True)

if rec and audio:
    pt = pd.DataFrame({"valence": [rec["valence"]], "energy": [rec["energy"]], "song": [track["name"]],
                       "Last.fm genre mood": [genre or "none"]})
    fig = px.scatter(pt, x="valence", y="energy", color="Last.fm genre mood", hover_name="song",
                     color_discrete_map={**MOOD_COLORS, "none": "#8a919c"}, range_x=[0, 1], range_y=[0, 1],
                     labels={"valence": "Valence (positivity)", "energy": "Energy"})
    fig.add_vline(x=0.5, line_dash="dot", opacity=0.5)
    fig.add_hline(y=0.5, line_dash="dot", opacity=0.5)
    for x, y, lab in [(0.75, 0.97, "upbeat"), (0.25, 0.97, "intense"), (0.75, 0.03, "calm"), (0.25, 0.03, "mellow")]:
        fig.add_annotation(x=x, y=y, text=f"audio: {lab}", showarrow=False, opacity=0.55)
    fig.update_traces(marker=dict(size=16))
    fig.update_layout(height=380, margin=dict(t=10, b=10), legend=dict(orientation="h", y=-0.25, title_text=""))
    st.plotly_chart(fig, width="stretch")
    st.caption("Where this song sits on ReccoBeats' valence and energy scale. The dot's colour is the Last.fm label.")

with st.expander("All the raw data"):
    st.json({
        "spotify": track,
        "reccobeats": rec,
        "lastfm_artists": {n: {"info": i, "vote": {k: vv for k, vv in v.items()}} for n, (i, v) in artist_results.items()},
    }, expanded=False)
