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

st.markdown(TRACK_CSS, unsafe_allow_html=True)


@st.cache_resource
def get_engine():
    return create_engine(
        f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}",
        pool_pre_ping=True, pool_recycle=300,  # recover on its own after the database restarts
    )


QUERY = """
    SELECT t.track_id, t.track_name, t.plays, t.genre_mood, t.audio_mood, t.valence, t.energy,
           f.danceability, f.acousticness, f.speechiness, f.instrumentalness, f.liveness, f.loudness, f.tempo,
           r.artist_names, r.album_name, c.image_url, g.genres,
           t.primary_artist_id, g.artist_name AS primary_artist
    FROM dbt_dev.mood_comparison_track t
    LEFT JOIN dbt_dev.stg_audio_features f ON f.track_id = t.track_id
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
def load(query):
    # the query text is part of the cache key, so editing it never serves a stale result
    return pd.read_sql(query, get_engine())


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

df = load(QUERY)
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

# ---------------------------------------------------------------- data for the three toggles below
@st.cache_data(ttl=300)
def load_seed(query):
    s = pd.read_sql(query, get_engine())
    return dict(zip(s["genre"], s["mood"]))


seed = load_seed("SELECT lower(genre) AS genre, mood FROM dbt_dev.genre_mood_map WHERE mood <> 'unclassified'")

artists = (df.sort_values("plays", ascending=False)
             .drop_duplicates("primary_artist_id")
             [["primary_artist_id", "primary_artist", "genres", "genre_mood"]].copy())
artists["songs"] = artists["primary_artist_id"].map(df.groupby("primary_artist_id").size())
artists = artists.sort_values(["songs", "primary_artist"], ascending=[False, True]).reset_index(drop=True)


def vote(tags):
    """Votes per mood from an artist's tags, the same rule as the pipeline."""
    tags = list(tags) if isinstance(tags, (list, tuple)) else []
    counts = {k: 0 for k in MOODS}
    per_tag = []
    for t in tags:
        m = seed.get(str(t).lower())
        per_tag.append((t, m))
        if m:
            counts[m] += 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    winner = ranked[0][0] if ranked[0][1] > 0 else None
    top, second = ranked[0][1], ranked[1][1]
    total = sum(counts.values())
    if total == 0:
        how = "no mood tags"
    elif total == 1:
        how = "one tag decided it"
    elif top == second:
        how = "tie, broken alphabetically"
    else:
        how = "clear majority"
    return {"counts": counts, "per_tag": per_tag, "winner": winner, "top": top, "second": second,
            "ignored": sum(1 for _, m in per_tag if not m), "how": how}


voted = {r.primary_artist_id: vote(r.genres) for r in artists.itertuples()}
artists["winner"] = artists["primary_artist_id"].map(lambda i: voted[i]["winner"])
artists["how"] = artists["primary_artist_id"].map(lambda i: voted[i]["how"])

# ---------------------------------------------------------------- toggles: Last.fm, ReccoBeats, the math
st.divider()
st.markdown("**Behind the labels.** Open a toggle to see the Last.fm analysis, the ReccoBeats ratings, or the math.")

with st.expander("Last.fm", expanded=False):
    st.markdown(
        "Last.fm does not rate songs. It gives each **artist** a list of tags, and the genre mood is a vote among "
        "those tags. The chart shows the votes behind each artist's label; the table shows which tag voted for which mood."
    )

    mismatch = int((artists["winner"] != artists["genre_mood"]).sum())
    if mismatch:
        st.warning(f"{mismatch} artist(s) get a different label here than the one stored by the pipeline, "
                   "so their tag list or the seed list has changed since the last run.")

    hc = artists["how"].value_counts()
    c1, c2, c3 = st.columns(3)
    c1.metric("Artists", len(artists))
    c2.metric("Label rests on a single tag", int(hc.get("one tag decided it", 0)))
    c3.metric("Ties broken alphabetically", int(hc.get("tie, broken alphabetically", 0)))

    long_rows = []
    for r in artists.itertuples():
        v = voted[r.primary_artist_id]
        tagtxt = ", ".join(str(t) for t, _ in v["per_tag"]) or "no tags"
        for k in MOODS:
            long_rows.append({"Artist": r.primary_artist, "Votes for": k, "Tags": v["counts"][k], "tags": tagtxt})
        long_rows.append({"Artist": r.primary_artist, "Votes for": "ignored (no mood)", "Tags": v["ignored"], "tags": tagtxt})
    long_df = pd.DataFrame(long_rows)
    fig_votes = px.bar(
        long_df, y="Artist", x="Tags", color="Votes for", orientation="h",
        color_discrete_map={**MOOD_COLORS, "ignored (no mood)": "#8a919c"},
        category_orders={"Artist": list(artists["primary_artist"]), "Votes for": MOODS + ["ignored (no mood)"]},
        hover_data={"tags": True, "Artist": False},
        labels={"Tags": "Number of tags"},
    )
    fig_votes.update_yaxes(autorange="reversed", title=None)
    fig_votes.update_layout(height=max(320, 26 * len(artists) + 120), margin=dict(t=10, b=10),
                            legend=dict(orientation="h", y=-0.12, title_text=""))
    st.plotly_chart(fig_votes, width="stretch")
    st.caption("Each bar is one artist's tags, split by the mood the seed list gives them. The tallest colour wins; "
               "grey tags such as place names are ignored. This is the Last.fm counterpart of the valence and energy chart above.")

    st.markdown(
        "<style>.chip{display:inline-block;margin:1px 4px 1px 0;padding:0 8px;border-radius:999px;border:1px solid;"
        "font-size:.8rem}.chip.ign{border-style:dashed;opacity:.55}</style>", unsafe_allow_html=True)
    vrows = []
    for r in artists.itertuples():
        v = voted[r.primary_artist_id]
        chips = "".join(
            (f'<span class="chip" style="border-color:{MOOD_COLORS[m]};color:{MOOD_COLORS[m]}">{_esc(t)}</span>' if m
             else f'<span class="chip ign">{_esc(t)}</span>')
            for t, m in v["per_tag"]) or '<span class="muted">no tags</span>'
        cells = [
            _esc(r.primary_artist), str(int(r.songs)), chips,
            " &middot; ".join(f"{k} {v['counts'][k]}" for k in MOODS),
            mood_badge(r.genre_mood), f'<span class="muted">{_esc(v["how"])}</span>',
        ]
        vrows.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    vhead = "".join(f"<th>{h}</th>" for h in ["Artist", "Songs here", "Last.fm tags (coloured = voted)", "Votes", "Label", "Decided by"])
    st.markdown(f'<table class="tt-table"><thead><tr>{vhead}</tr></thead><tbody>{"".join(vrows)}</tbody></table>',
                unsafe_allow_html=True)
    st.caption("A dashed grey tag has no mood in the seed list, so it casts no vote.")


with st.expander("ReccoBeats", expanded=False):
    st.markdown(
        "ReccoBeats gives every song nine numbers. The audio mood uses only **valence** and **energy**; "
        "the other seven are shown for context. The bars show where each 0-to-1 value sits."
    )
    UNIT = lambda label: st.column_config.ProgressColumn(label, min_value=0.0, max_value=1.0, format="%.2f")
    ratings = df[["track_name", "artist_names", "valence", "energy", "danceability", "acousticness",
                  "speechiness", "instrumentalness", "liveness", "loudness", "tempo", "audio_mood"]]
    st.dataframe(
        ratings, hide_index=True, width="stretch", height=520,
        column_config={
            "track_name": st.column_config.TextColumn("Song"),
            "artist_names": st.column_config.TextColumn("Artist"),
            "valence": UNIT("Valence"), "energy": UNIT("Energy"), "danceability": UNIT("Danceability"),
            "acousticness": UNIT("Acousticness"), "speechiness": UNIT("Speechiness"),
            "instrumentalness": UNIT("Instrumentalness"), "liveness": UNIT("Liveness"),
            "loudness": st.column_config.NumberColumn("Loudness (dB)", format="%.1f"),
            "tempo": st.column_config.NumberColumn("Tempo (BPM)", format="%.0f"),
            "audio_mood": st.column_config.TextColumn("Audio mood"),
        },
    )
    st.caption(f"{len(df)} songs. Click a column heading to sort, and scroll sideways for the rest.")
    st.markdown(
        "**What each rating means.** These are the usual meanings of the nine features, which ReccoBeats provides "
        "under the same names as Spotify's former audio-features. ReccoBeats' values are **estimates**.\n\n"
        "* **Valence** (0 to 1): musical positivity. Low sounds sad or angry, high sounds happy or cheerful.\n"
        "* **Energy** (0 to 1): intensity and activity. Fast, loud and noisy tracks score high.\n"
        "* **Danceability** (0 to 1): how suitable the song is for dancing, from tempo, rhythm stability and beat strength.\n"
        "* **Acousticness** (0 to 1): confidence that the song is acoustic.\n"
        "* **Speechiness** (0 to 1): how much of the song is spoken words, so rap scores higher than singing.\n"
        "* **Instrumentalness** (0 to 1): likelihood that there are no vocals.\n"
        "* **Liveness** (0 to 1): likelihood of a live audience in the recording.\n"
        "* **Loudness** (dB): average loudness. Values are negative, and closer to 0 means louder.\n"
        "* **Tempo** (BPM): beats per minute."
    )

with st.expander("The math", expanded=False):
    ROW_END = chr(92) * 2  # the LaTeX row separator

    st.markdown(r"**1. The audio mood.** Each song has a valence $v$ and an energy $e$, both between $0$ and $1$.")
    st.latex(
        r"\text{audio mood}(v,e)=\begin{cases}"
        r"\text{upbeat} & v\ge 0.5,\ e\ge 0.5" + ROW_END +
        r"\text{intense} & v< 0.5,\ e\ge 0.5" + ROW_END +
        r"\text{calm} & v\ge 0.5,\ e< 0.5" + ROW_END +
        r"\text{mellow} & v< 0.5,\ e< 0.5"
        r"\end{cases}"
    )

    st.markdown(
        r"**2. The Last.fm genre mood.** For an artist $a$, let $T_a$ be its top Last.fm tags (at most five, each with "
        r"a weight of at least $10$, where Last.fm scales the top tag to $100$). Let $s(t)$ be the mood that the "
        r"hand-made seed list gives tag $t$; tags marked unclassified give none. The artist's mood is the most frequent one:"
    )
    st.latex(
        r"g(a)=\operatorname*{arg\,max}_{k\,\in\,\{\text{calm},\,\text{mellow},\,\text{intense},\,\text{upbeat}\}}"
        r"\ \sum_{t\in T_a}\mathbb{1}\!\left[s(t)=k\right]"
    )
    st.caption("Ties are broken alphabetically. Every song by the same artist gets the same genre mood.")

    st.markdown(
        r"**2b. The votes.** For artist $a$ and mood $k$, let $c_k(a)$ be the number of the artist's tags that vote for $k$. "
        r"The label is the mood with the most votes. The margin $\Delta(a)$ says how decisive the vote was, where $c_{(1)}$ "
        r"and $c_{(2)}$ are the largest and second-largest vote counts:"
    )
    st.latex(
        r"c_k(a)=\sum_{t\in T_a}\mathbb{1}\left[s(t)=k\right],\qquad g(a)=\operatorname*{arg\,max}_{k}\,c_k(a),"
        r"\qquad \Delta(a)=c_{(1)}(a)-c_{(2)}(a)"
    )
    st.caption(r"$\Delta=0$ is a tie, settled alphabetically. $c_{(1)}=1$ with every other count $0$ means a single tag decided the label.")
    pick = st.selectbox("Work it out for an artist", list(artists["primary_artist"]), index=0)
    pr = artists[artists["primary_artist"] == pick].iloc[0]
    pv = voted[pr["primary_artist_id"]]
    st.dataframe(
        pd.DataFrame({"Tag": [t for t, _ in pv["per_tag"]],
                      "Mood from the seed list": [m or "none (ignored)" for _, m in pv["per_tag"]]}),
        hide_index=True, width="content",
    )
    st.latex(r",\ ".join(r"c_{\text{%s}}=%d" % (k, pv["counts"][k]) for k in MOODS))
    if pv["winner"]:
        st.latex(r"g(a)=\operatorname*{arg\,max}_{k}\,c_k(a)=\text{%s}\qquad \Delta=%d-%d=%d"
                 % (pv["winner"], pv["top"], pv["second"], pv["top"] - pv["second"]))
        st.caption(f"{pick}: {pv['how']}.")
    else:
        st.caption(f"{pick} has no tag that maps to a mood.")

    st.markdown(
        r"**3. Observed agreement.** Over the $N$ songs that have both labels, with $g_i$ the Last.fm label and "
        r"$r_i$ the ReccoBeats label of song $i$:"
    )
    st.latex(r"p_o=\frac{1}{N}\sum_{i=1}^{N}\mathbb{1}\left[g_i=r_i\right]")
    st.caption(r"The bracket symbol $\mathbb{1}[\cdot]$ equals $1$ when the statement inside it is true and $0$ otherwise, "
               r"so $p_o$ is simply the share of songs where both methods give the same label.")

    st.markdown(
        r"**4. Agreement expected by chance.** Let $n_{k\cdot}$ be the number of songs the Last.fm label puts in mood $k$ "
        r"and $n_{\cdot k}$ the number ReccoBeats puts there. If the two labellings were independent, they would "
        r"agree with probability:"
    )
    st.latex(r"p_e=\sum_{k}\frac{n_{k\cdot}}{N}\cdot\frac{n_{\cdot k}}{N}")

    g_counts = df["genre_mood"].value_counts().reindex(MOODS, fill_value=0)
    a_counts = df["audio_mood"].value_counts().reindex(MOODS, fill_value=0)
    marg = pd.DataFrame({
        "Mood": MOODS,
        "Last.fm count": g_counts.values,
        "ReccoBeats count": a_counts.values,
        "Chance term": [(g / n) * (a / n) for g, a in zip(g_counts.values, a_counts.values)],
    })
    st.dataframe(marg, hide_index=True, width="content",
                 column_config={"Chance term": st.column_config.NumberColumn("Chance term", format="%.4f")})

    st.markdown(r"**5. Cohen's kappa.** The agreement beyond chance, as a share of the most it could be:")
    st.latex(r"\kappa=\frac{p_o-p_e}{1-p_e}")

    n_same = int(df["match"].sum())
    p_o = n_same / n
    p_e = float(sum((g / n) * (a / n) for g, a in zip(g_counts.values, a_counts.values)))
    terms = " + ".join(r"\frac{%d}{%d}\cdot\frac{%d}{%d}" % (g, n, a, n)
                       for g, a in zip(g_counts.values, a_counts.values) if g and a) or "0"
    kappa_hand = (p_o - p_e) / (1 - p_e) if p_e < 1 else float("nan")

    st.markdown("**With your numbers:**")
    st.latex(r"p_o=\frac{%d}{%d}=%.3f" % (n_same, n, p_o))
    st.latex(r"p_e=" + terms + r"=%.3f" % p_e)
    if pd.isna(kappa_hand):
        st.latex(r"\kappa\ \text{is undefined here, because } p_e=1")
    else:
        st.latex(r"\kappa=\frac{%.3f-%.3f}{1-%.3f}=%.3f" % (p_o, p_e, p_e, kappa_hand))
        if kappa is not None and not pd.isna(kappa) and abs(kappa - kappa_hand) < 1e-9:
            st.caption("This hand calculation matches scikit-learn's `cohen_kappa_score`.")
    st.caption(
        "A common rule of thumb (Landis and Koch, 1977): 0 to 0.2 slight, 0.2 to 0.4 fair, 0.4 to 0.6 moderate, "
        "0.6 to 0.8 substantial, above 0.8 almost perfect. With this few songs, treat the value as rough."
    )
