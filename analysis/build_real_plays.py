"""Build Stata-ready tables from the Spotify Extended Streaming History.

Usage (from the repo root):
    python -I analysis/build_real_plays.py "C:/Users/DELL/Downloads/my_spotify_data.zip"

Reads the audio files straight from the zip. A "real play" is a music play that lasted at least
30 seconds, which is Spotify's own threshold and the one the pipeline uses.
Writes, into analysis/output/ (gitignored, because it is personal data):
    real_plays.dta / .csv   one row per real play
    real_songs.dta / .csv   one row per song with at least one real play
The IP address and country in the export are NOT copied.
"""
import json
import sys
import zipfile
from pathlib import Path

import pandas as pd

zip_path = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\DELL\Downloads\my_spotify_data.zip")
out = Path(__file__).resolve().parent / "output"
out.mkdir(exist_ok=True)
REAL_MS = 30_000

rows = []
with zipfile.ZipFile(zip_path) as z:
    for name in sorted(z.namelist()):
        base = name.rsplit("/", 1)[-1]
        if base.startswith("Streaming_History_Audio_") and base.endswith(".json"):
            rows.extend(json.loads(z.read(name).decode("utf-8")))

df = pd.DataFrame(rows)
n_all_rows = len(df)
df = df[df["spotify_track_uri"].notna()].copy()           # music only (drops podcasts and other audio)
n_music = len(df)

df["track_id"] = df["spotify_track_uri"].str.split(":").str[-1]
df["ts_utc"] = pd.to_datetime(df["ts"], utc=True)
df["ts_ist"] = df["ts_utc"].dt.tz_convert("Asia/Kolkata")
df["seconds_played"] = (df["ms_played"].fillna(0) / 1000.0).round(1)
df["real_play"] = df["ms_played"].fillna(0) >= REAL_MS

play = pd.DataFrame({
    "ts_utc": df["ts_utc"].dt.tz_localize(None),
    "ts_ist": df["ts_ist"].dt.tz_localize(None),
    "year": df["ts_ist"].dt.year.astype("int16"),
    "month": df["ts_ist"].dt.month.astype("int8"),
    "hour_ist": df["ts_ist"].dt.hour.astype("int8"),
    "track_id": df["track_id"],
    "track": df["master_metadata_track_name"],
    "artist": df["master_metadata_album_artist_name"],
    "album": df["master_metadata_album_album_name"],
    "seconds_played": df["seconds_played"],
    "skipped": df["skipped"].fillna(False).astype(bool).astype("int8"),
    "shuffle": df["shuffle"].fillna(False).astype(bool).astype("int8"),
    "reason_start": df["reason_start"],
    "reason_end": df["reason_end"],
    "platform": df["platform"].fillna("unknown").str.split(" ").str[0].str.lower(),
    "real_play": df["real_play"].astype("int8"),
}).sort_values("ts_utc").reset_index(drop=True)

real = play[play["real_play"] == 1].drop(columns="real_play").reset_index(drop=True)

# one row per song with at least one real play
g_all = play.groupby("track_id").size().rename("n_all_plays")
g = real.groupby("track_id")
latest = real.sort_values("ts_utc").groupby("track_id").tail(1).set_index("track_id")[["track", "artist", "album"]]
songs = latest.join(pd.DataFrame({
    "n_real_plays": g.size(),
    "hours_real": (g["seconds_played"].sum() / 3600).round(2),
    "first_real_play": g["ts_ist"].min(),
    "last_real_play": g["ts_ist"].max(),
    "n_skipped_real": g["skipped"].sum(),
})).join(g_all)
songs["n_short_plays"] = songs["n_all_plays"] - songs["n_real_plays"]
songs = songs.reset_index().sort_values(["n_real_plays", "hours_real"], ascending=False).reset_index(drop=True)
songs["n_real_plays"] = songs["n_real_plays"].astype("int32")
songs["n_all_plays"] = songs["n_all_plays"].astype("int32")
songs["n_short_plays"] = songs["n_short_plays"].astype("int32")
songs["n_skipped_real"] = songs["n_skipped_real"].astype("int32")

play_labels = {
    "ts_utc": "Time the play ended (UTC)", "ts_ist": "Time the play ended (IST)", "year": "Year (IST)",
    "month": "Month (IST)", "hour_ist": "Hour of day (IST)", "track_id": "Spotify track id", "track": "Track name",
    "artist": "Artist (album artist)", "album": "Album", "seconds_played": "Seconds played", "skipped": "Spotify skipped flag",
    "shuffle": "Shuffle on", "reason_start": "How the play started", "reason_end": "How the play ended",
    "platform": "Device family", "real_play": "Played 30 seconds or more",
}
song_labels = {
    "track_id": "Spotify track id", "track": "Track name", "artist": "Artist (album artist)", "album": "Album",
    "n_real_plays": "Real plays (30s or more)", "hours_real": "Hours in real plays", "first_real_play": "First real play (IST)",
    "last_real_play": "Last real play (IST)", "n_skipped_real": "Real plays flagged skipped",
    "n_all_plays": "All plays incl. under 30s", "n_short_plays": "Plays under 30 seconds",
}


def save(frame, name, labels, dates):
    frame.to_csv(out / f"{name}.csv", index=False, encoding="utf-8")
    frame.to_stata(out / f"{name}.dta", write_index=False, version=118,
                   variable_labels={k: v for k, v in labels.items() if k in frame.columns},
                   convert_dates={c: "tc" for c in dates})


save(real, "real_plays", play_labels, ["ts_utc", "ts_ist"])
save(songs, "real_songs", song_labels, ["first_real_play", "last_real_play"])

print(f"rows in the audio files:            {n_all_rows:,}")
print(f"music plays (all songs played):     {n_music:,}   distinct songs: {play['track_id'].nunique():,}")
print(f"real plays (30 seconds or more):    {len(real):,}   distinct songs: {real['track_id'].nunique():,}")
print(f"shorter than 30 seconds:            {n_music - len(real):,}")
print(f"written to {out}:")
for f in sorted(out.glob("real_*")):
    print(f"   {f.name}  {f.stat().st_size / 1e6:.1f} MB")
