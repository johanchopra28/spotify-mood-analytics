import os
import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

import html as _html

import cat_meme
import covers

load_dotenv()

MOOD_COLORS = {
    "calm": "#5B9BD5",
    "mellow": "#1DB954",
    "intense": "#E33A3A",
    "upbeat": "#FFC000",
}

SPOTIFY_GREEN = "#1DB954"

@st.cache_data(ttl=6 * 3600, show_spinner=False)
def weekly_cat(mood, week):
    """Cat meme for this week's dominant mood (None if CATAAS is unavailable)."""
    return cat_meme.get_cat_meme(mood, week)
SPOTIFY_TRACK_URL = "https://open.spotify.com/track/"

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
</style>"""

@st.cache_resource
def get_engine():
    conn_str = (
        f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    )
    return create_engine(conn_str)

@st.cache_data(ttl=300)
def load_data():
    engine = get_engine()
    daily_listening = pd.read_sql("SELECT * FROM dbt_dev.daily_listening_summary ORDER BY listen_date", engine)
    daily_mood = pd.read_sql("SELECT * FROM dbt_dev.daily_mood_summary ORDER BY listen_date", engine)
    dominant_mood = pd.read_sql("SELECT * FROM dbt_dev.daily_dominant_mood ORDER BY listen_date DESC", engine)
    daily_top_track = pd.read_sql("SELECT * FROM dbt_dev.daily_top_track ORDER BY listen_date DESC", engine)

    audio_mood = pd.read_sql("SELECT * FROM dbt_dev.daily_audio_mood_summary ORDER BY listen_date", engine)
    audio_coverage = pd.read_sql("""
        SELECT count(*) AS plays, count(a.track_id) AS plays_with_audio
        FROM dbt_dev.stg_recently_played p
        LEFT JOIN dbt_dev.stg_audio_features a USING (track_id)
    """, engine)

    mood_tracks = pd.read_sql("""
        SELECT date_trunc('day', p.played_at) AS listen_date, m.mood, p.track_id,
               max(p.track_name) AS track_name, max(p.artist_names) AS artist_names,
               count(*) AS plays, round(sum(p.duration_minutes)::numeric, 1) AS minutes,
               max(c.image_url) AS image_url
        FROM dbt_dev.stg_recently_played p
        JOIN dbt_dev.stg_artist_moods m ON m.artist_id = p.primary_artist_id
        LEFT JOIN dbt_dev.stg_track_covers c USING (track_id)
        GROUP BY 1, 2, 3
        ORDER BY 1, minutes DESC
    """, engine)

    track_meta = pd.read_sql("""
        SELECT DISTINCT ON (p.track_id) p.track_id, p.album_name, c.image_url
        FROM dbt_dev.stg_recently_played p
        LEFT JOIN dbt_dev.stg_track_covers c USING (track_id)
        ORDER BY p.track_id, p.played_at DESC
    """, engine)

    today_tracks = pd.read_sql("""
        SELECT played_at, track_id, track_name, artist_names
        FROM dbt_dev.stg_recently_played
        WHERE played_at::date = (SELECT max(played_at::date) FROM dbt_dev.stg_recently_played)
        ORDER BY played_at DESC
    """, engine)

    top_tracks_week = pd.read_sql("""
        SELECT track_id, track_name, artist_names, count(*) as plays
        FROM dbt_dev.stg_recently_played
        WHERE played_at >= now() - interval '7 days'
        GROUP BY track_id, track_name, artist_names
        ORDER BY plays DESC
        LIMIT 10
    """, engine)

    top_artists_week = pd.read_sql("""
        SELECT artist_names, count(*) as plays, round(sum(duration_minutes)::numeric, 1) as minutes
        FROM dbt_dev.stg_recently_played
        WHERE played_at >= now() - interval '7 days'
        GROUP BY artist_names
        ORDER BY minutes DESC
        LIMIT 10
    """, engine)

    discovered_recently = pd.read_sql("""
        SELECT track_id, track_name, artist_names, count(*) as plays, min(played_at) as first_played
        FROM dbt_dev.stg_recently_played
        GROUP BY track_id, track_name, artist_names
        HAVING count(*) > 1
           AND min(played_at) >= now() - interval '7 days'
        ORDER BY plays DESC, first_played DESC
    """, engine)

    liked_tracks = pd.read_sql("""
        SELECT track_id, track_name, artist_names, liked_at
        FROM liked_tracks
        ORDER BY liked_at DESC
    """, engine)

    # pandas converts timestamptz to UTC; day buckets are IST midnights, so convert back
    for frame in (daily_listening, daily_mood, dominant_mood, daily_top_track, audio_mood, mood_tracks):
        frame["listen_date"] = pd.to_datetime(frame["listen_date"], utc=True).dt.tz_convert("Asia/Kolkata")

    return (daily_listening, daily_mood, dominant_mood, daily_top_track,
            audio_mood, audio_coverage, track_meta, mood_tracks, today_tracks, top_tracks_week, top_artists_week,
            discovered_recently, liked_tracks)

def toggle_like(engine, track_id, track_name, artist_names):
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM liked_tracks WHERE track_id = :tid"),
            {"tid": track_id}
        ).fetchone()
        if exists:
            conn.execute(text("DELETE FROM liked_tracks WHERE track_id = :tid"), {"tid": track_id})
        else:
            conn.execute(
                text("""
                    INSERT INTO liked_tracks (track_id, track_name, artist_names)
                    VALUES (:tid, :tname, :aname)
                """),
                {"tid": track_id, "tname": track_name, "aname": artist_names}
            )
    st.cache_data.clear()

st.set_page_config(page_title="My Listening & Mood", page_icon="🎧", layout="wide")

st.markdown("""
<style>
    html { scroll-behavior: smooth; }
    .block-container { padding-top: 2rem; }
    h1, h2, h3 { font-weight: 700; }
    [data-testid="stMetricValue"] { color: #1DB954; }
</style>
""", unsafe_allow_html=True)
st.markdown(TRACK_CSS, unsafe_allow_html=True)

(daily_listening, daily_mood, dominant_mood, daily_top_track,
 audio_mood, audio_coverage, track_meta, mood_tracks, today_tracks, top_tracks_week, top_artists_week,
 discovered_recently, liked_tracks) = load_data()

title_col, cat_col = st.columns([4, 1])
with title_col:
    st.title("🎧 My Listening & Mood")
with cat_col:
    week_mood = cat_meme.weekly_dominant_mood(daily_mood)
    if week_mood and os.getenv("CAT_MEME", "on").lower() != "off":
        meme = weekly_cat(week_mood, cat_meme.week_key())
        color = MOOD_COLORS.get(week_mood, "#999999")
        if meme:
            visual = (
                '<div style="position:relative;display:inline-block;">'
                f'<img src="{meme["url"]}" alt="{meme["caption"]}" '
                f'style="width:100%;max-width:260px;border-radius:12px;border:3px solid {color};display:block;">'
                '<div style="position:absolute;left:6px;right:6px;bottom:8px;text-align:center;'
                'font:800 1.05rem Impact,Arial Black,sans-serif;color:#fff;text-transform:uppercase;'
                'text-shadow:-1px -1px 0 #000,1px -1px 0 #000,-1px 1px 0 #000,1px 1px 0 #000;">'
                f'{meme["caption"]}</div></div>'
            )
        else:
            visual = f'<div style="font-size:4rem;line-height:1;">{cat_meme.EMOJI[week_mood]}</div>'
        st.markdown(
            f'<div style="text-align:right;">{visual}'
            f'<div style="font-size:0.8rem;opacity:0.75;margin-top:4px;">'
            f'Your week: <b style="color:{color};">{week_mood.capitalize()}</b></div></div>',
            unsafe_allow_html=True,
        )

st.components.v1.html("""
<style>
    .nav-pill {
        background:#333; color:white; padding:6px 14px; border-radius:20px;
        margin-right:8px; font-size:0.85rem; cursor:pointer; display:inline-block;
        font-family:'Source Sans Pro', sans-serif; transition: background 0.2s ease, transform 0.15s ease;
    }
    .nav-pill:hover { background:#1DB954; transform: translateY(-1px); }
</style>
<div style="margin-bottom: 0.5rem;">
    <span class="nav-pill" onclick="smoothScrollTo('discovered-recently')">🔍 Discovered</span>
    <span class="nav-pill" onclick="smoothScrollTo('liked-songs')">❤️ Liked</span>
</div>
<script>
    function getScrollParent(el, doc) {
        while (el && el !== doc.body) {
            const style = window.parent.getComputedStyle(el);
            if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && el.scrollHeight > el.clientHeight) {
                return el;
            }
            el = el.parentElement;
        }
        return doc.scrollingElement || doc.documentElement;
    }

    function smoothScrollTo(id) {
        const doc = window.parent.document;
        const target = doc.getElementById(id);
        if (!target) return;

        const container = getScrollParent(target.parentElement, doc);
        const containerRect = container.getBoundingClientRect();
        const targetRect = target.getBoundingClientRect();
        const startY = container.scrollTop;
        const targetY = startY + (targetRect.top - containerRect.top) - 20;
        const distance = targetY - startY;
        const duration = 700;
        let startTime = null;

        function easeInOutCubic(t) {
            return t < 0.5 ? 4*t*t*t : 1 - Math.pow(-2*t+2, 3)/2;
        }

        function step(timestamp) {
            if (!startTime) startTime = timestamp;
            const elapsed = timestamp - startTime;
            const t = Math.min(elapsed / duration, 1);
            container.scrollTop = startY + distance * easeInOutCubic(t);
            if (t < 1) window.parent.requestAnimationFrame(step);
        }
        window.parent.requestAnimationFrame(step);
    }
</script>
""", height=45)

# --- Today's dominant mood banner ---
if not dominant_mood.empty:
    latest = dominant_mood.iloc[0]
    mood = latest["dominant_mood"]
    color = MOOD_COLORS.get(mood, "#999999")
    st.markdown(
        f"""
        <div style="background: linear-gradient(90deg, {color}33, {color}0D);
                    padding:24px 28px; border-radius:14px; border-left:6px solid {color};">
            <p style="margin:0; font-size:0.85rem; letter-spacing:1px; text-transform:uppercase; opacity:0.7;">
                Today's vibe
            </p>
            <h2 style="margin:4px 0 0 0; color:{color};">{mood.capitalize()} 🎵</h2>
            <p style="margin:6px 0 0 0; opacity:0.8;">{latest['dominant_mood_minutes']} minutes of {mood} listening today</p>
        </div>
        """,
        unsafe_allow_html=True
    )
else:
    st.info("No mood data yet — keep listening and check back soon.")

st.write("")

# --- Mood over time (animated, custom HTML/JS) ---
st.subheader("Mood over time")

if not daily_mood.empty:
    import json

    df = daily_mood.copy()
    df["Date"] = pd.to_datetime(df["listen_date"]).dt.strftime("%b %d")
    df["Mood"] = df["mood"].str.capitalize()

    df["day_total"] = df.groupby("listen_date")["minutes_listened"].transform("sum")
    df["Percent"] = round(100 * df["minutes_listened"] / df["day_total"], 1)

    dates = sorted(df["Date"].unique(), key=lambda d: pd.to_datetime(d + " 2026"))
    moods_present = [m for m in ["Calm", "Mellow", "Intense", "Upbeat"] if m in df["Mood"].unique()]
    color_map_cap = {k.capitalize(): v for k, v in MOOD_COLORS.items()}

    def build_traces(value_col):
        traces = []
        for mood in moods_present:
            sub = df[df["Mood"] == mood].set_index("Date")
            y_vals = [round(float(sub.loc[d, value_col]), 1) if d in sub.index else 0 for d in dates]
            traces.append({
                "x": dates, "y": y_vals, "name": mood,
                "type": "bar", "marker": {"color": color_map_cap[mood]}
            })
        return traces

    minutes_traces = build_traces("minutes_listened")
    percent_traces = build_traces("Percent")

    # songs behind each coloured block, keyed "Oct 11|Intense", embedded so a click needs no round trip
    mt = mood_tracks.copy()
    mt["Date"] = pd.to_datetime(mt["listen_date"]).dt.strftime("%b %d")
    mt["Mood"] = mt["mood"].str.capitalize()
    songs = {}
    for (d, m), g in mt.groupby(["Date", "Mood"]):
        songs[f"{d}|{m}"] = [
            {"id": r.track_id, "name": r.track_name, "artist": r.artist_names,
             "plays": int(r.plays), "min": float(r.minutes),
             "img": r.image_url if isinstance(r.image_url, str) and covers.is_spotify_image(r.image_url) else ""}
            for r in g.itertuples()
        ]
    # keep "</" out of the embedded JSON so it cannot close the script tag
    songs_json = json.dumps(songs).replace("</", "<" + chr(92) + "/")

    chart_html = f"""
    <style>
        .mood-btn {{
            background:#333; color:white; border:none; padding:6px 16px;
            border-radius:20px; margin-right:8px; cursor:pointer; font-family:sans-serif;
            transition: background 0.2s ease, transform 0.15s ease;
        }}
        .mood-btn:hover {{ background:#2a8a3f; transform: translateY(-1px); }}
        .mood-btn.active {{ background:#1DB954; }}
        .mood-btn.active:hover {{ background:#1DB954; }}
        #mood-chart .nsewdrag {{ cursor: pointer !important; }}
        #mood-hint {{ font:13px sans-serif; color:#9aa4ad; margin:4px 0 8px; }}
        #mood-songs {{ max-height:280px; overflow-y:auto; font-family:sans-serif; color:#e0e0e0; }}
        .songs-head {{ display:flex; align-items:center; gap:8px; font-weight:600; margin:6px 0; }}
        .songs-head .dot {{ width:10px; height:10px; border-radius:50%; }}
        .song-row {{ display:flex; align-items:center; gap:10px; padding:6px 0; border-top:1px solid #2a2f35; }}
        .song-row img, .song-row .ph {{ width:40px; height:40px; border-radius:4px; object-fit:cover; background:#2a2f35; flex:none; }}
        .song-row .txt {{ flex:1; min-width:0; }}
        .song-row .txt a {{ color:#e0e0e0; font-weight:600; text-decoration:none; }}
        .song-row .txt a:hover {{ text-decoration:underline; }}
        .song-row .txt span {{ display:block; font-size:12px; color:#9aa4ad; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
        .song-row .meta {{ font-size:12px; color:#9aa4ad; white-space:nowrap; }}
    </style>
    <div id="mood-toggle" style="margin-bottom:10px;">
        <button id="btn-minutes" class="mood-btn active" onclick="showView('minutes')">Minutes</button>
        <button id="btn-percent" class="mood-btn" onclick="showView('percent')">% of day</button>
    </div>
    <div id="mood-chart" style="width:100%;height:420px;"></div>
    <div id="mood-hint">Click a coloured block to see the songs behind it.</div>
    <div id="mood-songs"></div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.27.0/plotly.min.js"></script>
    <script>
        const minutesData = {json.dumps(minutes_traces)};
        const percentData = {json.dumps(percent_traces)};
        const songs = {songs_json};
        const moodColors = {json.dumps(color_map_cap)};
        let currentData = JSON.parse(JSON.stringify(minutesData));
        let currentMode = "minutes";
        let animating = false;

        const layout = {{
            barmode: "stack",
            margin: {{t: 10, b: 40}},
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
            font: {{color: "#e0e0e0"}},
            xaxis: {{gridcolor: "#333"}},
            yaxis: {{title: "Minutes", gridcolor: "#333"}},
            legend: {{orientation: "h", y: -0.2}}
        }};
        Plotly.newPlot("mood-chart", currentData, layout, {{responsive: true, displayModeBar: false}});

        function renderSongs(date, mood) {{
            const box = document.getElementById("mood-songs");
            const list = songs[date + "|" + mood] || [];
            box.textContent = "";
            document.getElementById("mood-hint").textContent = "";
            const head = document.createElement("div");
            head.className = "songs-head";
            const dot = document.createElement("span");
            dot.className = "dot";
            dot.style.background = moodColors[mood] || "#999";
            const total = list.reduce((a, s) => a + s.min, 0);
            head.appendChild(dot);
            head.appendChild(document.createTextNode(
                mood + " - " + date + " - " + list.length + (list.length === 1 ? " song" : " songs") + ", " + total.toFixed(1) + " min"));
            box.appendChild(head);
            list.forEach(s => {{
                const row = document.createElement("div");
                row.className = "song-row";
                if (s.img) {{
                    const im = document.createElement("img");
                    im.src = s.img; im.alt = "";
                    row.appendChild(im);
                }} else {{
                    const ph = document.createElement("div");
                    ph.className = "ph";
                    row.appendChild(ph);
                }}
                const txt = document.createElement("div");
                txt.className = "txt";
                const a = document.createElement("a");
                a.href = "https://open.spotify.com/track/" + encodeURIComponent(s.id);
                a.target = "_blank"; a.rel = "noopener"; a.textContent = s.name;
                const sub = document.createElement("span");
                sub.textContent = s.artist;
                txt.appendChild(a); txt.appendChild(sub);
                const meta = document.createElement("div");
                meta.className = "meta";
                meta.textContent = s.plays + (s.plays === 1 ? " play" : " plays") + ", " + s.min.toFixed(1) + " min";
                row.appendChild(txt); row.appendChild(meta);
                box.appendChild(row);
            }});
        }}
        document.getElementById("mood-chart").on("plotly_click", ev => {{
            const p = ev.points[0];
            renderSongs(p.x, p.data.name);
        }});

        function showView(mode) {{
            if (animating || mode === currentMode) return;
            animating = true;
            const targetData = mode === "minutes" ? minutesData : percentData;
            const startData = JSON.parse(JSON.stringify(currentData));
            const frames = 20;
            const durationMs = 450;
            let frame = 0;

            document.getElementById("btn-minutes").classList.toggle("active", mode === "minutes");
            document.getElementById("btn-percent").classList.toggle("active", mode === "percent");

            function easeInOutCubic(t) {{
                return t < 0.5 ? 4*t*t*t : 1 - Math.pow(-2*t+2, 3)/2;
            }}

            function step() {{
                frame++;
                const t = easeInOutCubic(frame / frames);
                const interpolated = startData.map((trace, i) => {{
                    return Object.assign({{}}, trace, {{
                        y: trace.y.map((v, j) => v + (targetData[i].y[j] - v) * t)
                    }});
                }});
                const newLayout = Object.assign({{}}, layout, {{
                    yaxis: {{title: mode === "minutes" ? "Minutes" : "Share of day (%)", gridcolor: "#333"}}
                }});
                Plotly.react("mood-chart", interpolated, newLayout, {{responsive: true, displayModeBar: false}});

                if (frame < frames) {{
                    setTimeout(step, durationMs / frames);
                }} else {{
                    currentData = targetData;
                    currentMode = mode;
                    animating = false;
                }}
            }}
            step();
        }}
    </script>
    """

    st.components.v1.html(chart_html, height=800)
else:
    st.info("No mood breakdown available yet.")

st.write("")
st.subheader("Audio mood (ReccoBeats)")
cov = audio_coverage.iloc[0]
st.caption(
    "Mood from ReccoBeats valence/energy estimates (not Spotify's own), "
    f"available for {int(cov['plays_with_audio'])} of {int(cov['plays'])} plays; "
    "tracks ReccoBeats doesn't know are left out."
)
if not audio_mood.empty:
    df = audio_mood.copy()
    df["Date"] = pd.to_datetime(df["listen_date"]).dt.strftime("%b %d")
    df["Mood"] = df["mood"].str.capitalize()
    fig_audio = px.bar(
        df, x="Date", y="minutes_listened", color="Mood",
        color_discrete_map={k.capitalize(): v for k, v in MOOD_COLORS.items()},
        labels={"minutes_listened": "Minutes", "Date": ""},
    )
    st.plotly_chart(fig_audio, width="stretch")
else:
    st.info("No audio-feature data yet.")

st.write("")
st.markdown("---")

# --- Overall listening activity ---
st.subheader("Listening activity")
if not daily_listening.empty:
    df = daily_listening.copy()
    df["Date"] = pd.to_datetime(df["listen_date"]).dt.strftime("%b %d")

    col1, col2 = st.columns(2)
    with col1:
        fig_minutes = px.line(
            df, x="Date", y="total_minutes_listened", markers=True,
            labels={"total_minutes_listened": "Minutes listened", "Date": ""},
            title="Minutes per day",
        )
        fig_minutes.update_traces(line_color=SPOTIFY_GREEN, marker_color=SPOTIFY_GREEN)
        st.plotly_chart(fig_minutes, width="stretch")
    with col2:
        df_variety = df.rename(columns={"distinct_tracks": "Tracks", "distinct_artists": "Artists"})
        fig_variety = px.line(
            df_variety, x="Date", y=["Tracks", "Artists"], markers=True,
            labels={"value": "Count", "Date": ""},
            title="Variety per day",
        )
        fig_variety.update_layout(legend_title_text="")
        st.plotly_chart(fig_variety, width="stretch")
else:
    st.info("No listening data yet.")

st.markdown("---")

# --- Top track per day ---
st.subheader("Song of the day")
if not daily_top_track.empty:
    df = daily_top_track.copy()
    df["Date"] = pd.to_datetime(df["listen_date"]).dt.strftime("%b %d")
    df = df.rename(columns={"play_count": "Plays"})
    st.markdown(tracks_table(df, [("Date", "Date"), ("Track", "__track__"), ("Artist", "artist_names"),
                                  ("Plays", "Plays")], track_meta), unsafe_allow_html=True)
else:
    st.info("No data yet.")

st.markdown("---")

# --- This week: top tracks & artists ---
st.subheader("This week's rotation")
col3, col4 = st.columns(2)
with col3:
    st.markdown("**🎵 Top tracks**")
    if not top_tracks_week.empty:
        df = top_tracks_week.rename(columns={"plays": "Plays"})
        st.markdown(tracks_table(df, [("Track", "__track__"), ("Artist", "artist_names"),
                                      ("Plays", "Plays")], track_meta), unsafe_allow_html=True)
    else:
        st.info("No data yet.")
with col4:
    st.markdown("**🎤 Top artists**")
    if not top_artists_week.empty:
        df = top_artists_week.rename(columns={"artist_names": "Artist", "plays": "Plays", "minutes": "Minutes"})
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info("No data yet.")

st.markdown("---")

# --- Today's actual tracks ---
with st.expander("🕒 Today's full play history"):
    if not today_tracks.empty:
        df = today_tracks.copy()
        df["Time"] = pd.to_datetime(df["played_at"], utc=True).dt.tz_convert("Asia/Kolkata").dt.strftime("%H:%M")
        st.markdown(tracks_table(df, [("Time", "Time"), ("Track", "__track__"), ("Artist", "artist_names")], track_meta), unsafe_allow_html=True)
    else:
        st.info("No plays recorded today yet.")

st.markdown("---")

# --- Discovered recently: new to your history, already played more than once ---
st.markdown('<div id="discovered-recently"></div>', unsafe_allow_html=True)
st.subheader("🔍 Discovered recently")
st.caption("New to your history in the last 7 days, and already played more than once.")
if not discovered_recently.empty:
    liked_ids = set(liked_tracks["track_id"]) if not liked_tracks.empty else set()
    meta_by_id = track_meta.set_index("track_id").to_dict("index")
    def discovered_row(row):
        col_a, col_b = st.columns([5, 1])
        with col_a:
            m = meta_by_id.get(row["track_id"], {})
            st.markdown(
                track_cell(row["track_id"], row["track_name"], row["artist_names"],
                           m.get("album_name"), m.get("image_url"), link=True)
                + f" &mdash; {_esc(row['artist_names'])} ({row['plays']} plays)",
                unsafe_allow_html=True,
            )
        with col_b:
            is_liked = row["track_id"] in liked_ids
            label = "❤️" if is_liked else "🤍"
            if st.button(label, key=f"like_{row['track_id']}"):
                toggle_like(get_engine(), row["track_id"], row["track_name"], row["artist_names"])
                st.rerun()

    # No scroll box here: a scrolling container would clip the hover cover card.
    SHOWN = 15
    for _, row in discovered_recently.head(SHOWN).iterrows():
        discovered_row(row)
    if len(discovered_recently) > SHOWN:
        with st.expander(f"Show {len(discovered_recently) - SHOWN} more"):
            for _, row in discovered_recently.iloc[SHOWN:].iterrows():
                discovered_row(row)
else:
    st.info("No repeated new discoveries in the last 7 days yet.")

st.markdown("---")

# --- Liked songs ---
st.markdown('<div id="liked-songs"></div>', unsafe_allow_html=True)
st.subheader("❤️ Liked songs")
if not liked_tracks.empty:
    df = liked_tracks.copy()
    df["Liked"] = pd.to_datetime(df["liked_at"], utc=True).dt.tz_convert("Asia/Kolkata").dt.strftime("%b %d")
    st.markdown(tracks_table(df, [("Track", "__track__"), ("Artist", "artist_names"),
                                  ("Liked", "Liked")], track_meta), unsafe_allow_html=True)
else:
    st.info("No liked songs yet — like something from 'Discovered recently' above.")