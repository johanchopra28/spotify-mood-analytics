"""Validation: does the genre-based mood agree with the audio-based mood?

Run `python analysis/export_mood_data.py` first, then:
    python analysis/validate_moods.py

Reports percent agreement, a confusion matrix (rows = genre mood, columns = audio mood)
and Cohen's kappa at track level and at artist level. Stata equivalent: validate_moods.do.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mood_stats import summarize  # noqa: E402

OUT = Path(__file__).resolve().parent / "output"


def interpret(k):
    if pd.isna(k):
        return "undefined (too few rows, or one method uses a single label)"
    for cut, text in [(0.8, "almost perfect"), (0.6, "substantial"), (0.4, "moderate"),
                      (0.2, "fair"), (0.0, "slight")]:
        if k > cut:
            return text
    return "no better than chance (or worse)"


def report(level, csv_name):
    path = OUT / csv_name
    df = pd.read_csv(path)
    res = summarize(df)
    print(f"\n=== {level} level ({csv_name}) ===")
    print(f"n = {res['n']}")
    print(f"percent agreement = {res['percent_agreement']:.1f}%")
    k = res["kappa"]
    print(f"Cohen's kappa = {'undefined' if pd.isna(k) else f'{k:.3f}'}  -> {interpret(k)}")
    print("confusion matrix (rows = genre mood, columns = audio mood):")
    print(res["confusion"].to_string())
    res["confusion"].to_csv(OUT / f"confusion_{level}.csv")
    return res


def main():
    for level, name in [("track", "mood_comparison_track.csv"),
                        ("artist", "mood_comparison_artist.csv")]:
        report(level, name)
    print("\nCaveats: small n makes kappa unstable; ReccoBeats coverage skews toward older "
          "tracks; audio features are ReccoBeats' estimates, not Spotify's.")


if __name__ == "__main__":
    main()
