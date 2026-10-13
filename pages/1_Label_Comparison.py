"""Second page: how Last.fm-based and ReccoBeats-based mood labels differ, for songs that have both."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "analysis"))

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine

from track_ui import MOOD_COLORS, TRACK_CSS, _esc, mood_badge, track_cell

try:
    import mood_stats          # needs scikit-learn; the page still works without it
except Exception:              # pragma: no cover
    mood_stats = None

load_dotenv(ROOT / ".env")
MOODS = ["calm", "mellow", "intense", "upbeat"]

st.set_page_config(page_title="Genre vs audio labels", page_icon=":material/compare_arrows:", layout="wide")
st.markdown(TRACK_CSS, unsafe_allow_html=True)


@st.cache_resource
def get_engine():
    return create_engine(
        f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    )


QUERY = """
    SELECT t.track_id, t.track_name, t.plays, t.genre_mood, t.audio_mood, t.valence, t.energy,
           r.artist_names, r.album_name, c.image_url, g.genres
    FROM dbt_dev.mood_comparison_track t
    LEFT JOIN (
        SELECT DISTINCT ON (track_id) track_id, artist_names, album_name
        FROM dbt_dev.stg_recently_played
        ORDER BY track_id, played_at DESC
    ) r ON r.track_id = t.track_id
    LEFT JOIN dbt_dev.stg_track_covers c ON c.track_id = t.track_id
    LEFT JOIN public.raw_artist_genres g ON g.artist_id = t.primary_artist_id
    ORDER BY t.plays DESC, t.track_name
"""


@st.cache_data(ttl=300)
def load():
    return pd.read_sql(QUERY, get_engine())


st.title("Genre vs audio labels")
st.markdown(
    "Songs that have **both** a Last.fm-based label and a ReccoBeats-based label, side by side. "
    "The two methods can disagree, and this page shows where."
)
with st.expander("How each label is made"):
    st.markdown(
        "* **Last.fm genre mood:** the artist's Last.fm tags are mapped to calm, mellow, intense or upbeat "
        "with a hand-made list (`genre_mood_map.csv`). It describes the **artist**, so every song by the "
        "same artist gets the same label.\n"
        "* **ReccoBeats audio mood:** ReccoBeats' estimate of the **song's** valence (positivity) and energy. "
        "High valence and high energy is upbeat, low valence and high energy is intense, high valence and "
        "low energy is calm, and low valence and low energy is mellow. The cut-off is 0.5.\n"
        "* ReccoBeats does not know every song, so this page only covers the songs it does know."
    )

df = load()
if df.empty:
    st.info("No songs have both labels yet. Keep the pipeline running and check back.")
    st.stop()

df["match"] = df["genre_mood"] == df["audio_mood"]
n = len(df)
pct = df["match"].mean() * 100
kappa = None
if mood_stats is not None and n >= 2:
    kappa = mood_stats.kappa(df["genre_mood"], df["audio_mood"])

m1, m2, m3 = st.columns(3)
m1.metric("Songs with both labels", n)
m2.metric("Same label", f"{pct:.0f}%")
m3.metric(
    "Cohen's kappa",
    "n/a" if kappa is None or pd.isna(kappa) else f"{kappa:.2f}",
    help="Agreement beyond what chance alone would give. 0 means no better than chance, 1 means perfect agreement.",
)
st.caption(
    "Small samples make these numbers unstable. ReccoBeats knows older songs far better than new releases, "
    "so this is not a random sample of your listening."
)

left, right = st.columns(2)
with left:
    st.subheader("Where they differ")
    ct = pd.crosstab(
        pd.Categorical(df["genre_mood"], categories=MOODS),
        pd.Categorical(df["audio_mood"], categories=MOODS),
        rownames=["Last.fm genre mood"], colnames=["ReccoBeats audio mood"], dropna=False,
    )
    fig_cm = px.imshow(ct, text_auto=True, aspect="auto", color_continuous_scale="Blues")
    fig_cm.update_layout(coloraxis_showscale=False, margin=dict(t=10, b=10))
    st.plotly_chart(fig_cm, width="stretch")
    st.caption("Rows: the Last.fm label. Columns: the ReccoBeats label. The diagonal is agreement.")
with right:
    st.subheader("Each song by its audio features")
    plot = df.assign(Result=df["match"].map({True: "Same label", False: "Different labels"}))
    fig_sc = px.scatter(
        plot, x="valence", y="energy", color="genre_mood", symbol="Result",
        color_discrete_map=MOOD_COLORS, category_orders={"genre_mood": MOODS},
        hover_name="track_name", hover_data={"artist_names": True, "audio_mood": True, "valence": ":.2f", "energy": ":.2f"},
        labels={"genre_mood": "Last.fm genre mood", "valence": "Valence (positivity)", "energy": "Energy"},
        range_x=[0, 1], range_y=[0, 1],
    )
    fig_sc.add_vline(x=0.5, line_dash="dot", opacity=0.5)
    fig_sc.add_hline(y=0.5, line_dash="dot", opacity=0.5)
    for x, y, label in [(0.75, 0.97, "upbeat"), (0.25, 0.97, "intense"), (0.75, 0.03, "calm"), (0.25, 0.03, "mellow")]:
        fig_sc.add_annotation(x=x, y=y, text=f"audio: {label}", showarrow=False, opacity=0.55)
    fig_sc.update_traces(marker=dict(size=11))
    fig_sc.update_layout(margin=dict(t=10, b=10), legend=dict(orientation="h", y=-0.3, title_text=""))
    st.plotly_chart(fig_sc, width="stretch")
    st.caption("Colour is the Last.fm label; the dotted lines are the 0.5 cut-offs that give the audio label.")

st.subheader("Song by song")
f1, f2, f3 = st.columns([2, 2, 2])
view = f1.radio("Show", ["All songs", "Only differences", "Only matches"], horizontal=True)
g_sel = f2.multiselect("Last.fm genre mood", MOODS, default=MOODS)
a_sel = f3.multiselect("ReccoBeats audio mood", MOODS, default=MOODS)

shown = df[df["genre_mood"].isin(g_sel) & df["audio_mood"].isin(a_sel)]
if view == "Only differences":
    shown = shown[~shown["match"]]
elif view == "Only matches":
    shown = shown[shown["match"]]

if shown.empty:
    st.info("No songs match these filters.")
else:
    rows = []
    for r in shown.itertuples():
        tags = ", ".join(r.genres[:5]) if isinstance(r.genres, (list, tuple)) and r.genres else "no tags"
        result = ('<span style="color:#1DB954;font-weight:600">Same</span>' if r.match
                  else '<span style="color:#FFC000;font-weight:600">Differs</span>')
        cells = [
            track_cell(r.track_id, r.track_name, r.artist_names, r.album_name, r.image_url, link=True),
            _esc(r.artist_names),
            f'<span class="muted">{_esc(tags)}</span>',
            mood_badge(r.genre_mood),
            mood_badge(r.audio_mood),
            f"{r.valence:.2f}",
            f"{r.energy:.2f}",
            result,
        ]
        rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    head = "".join(f"<th>{h}</th>" for h in
                   ["Song", "Artist", "Artist's Last.fm tags", "Last.fm genre mood", "ReccoBeats audio mood",
                    "Valence", "Energy", "Result"])
    st.markdown(f'<table class="tt-table"><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>',
                unsafe_allow_html=True)
    st.caption(f"{len(shown)} of {n} songs. Hover a song for its cover; click it to open it in Spotify.")
