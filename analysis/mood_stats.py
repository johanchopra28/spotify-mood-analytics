"""Agreement statistics between two mood labellings (genre-based vs audio-based)."""
import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score

MOODS = ["calm", "mellow", "intense", "upbeat"]


def percent_agreement(a, b):
    a, b = pd.Series(a).reset_index(drop=True), pd.Series(b).reset_index(drop=True)
    return float((a == b).mean() * 100) if len(a) else float("nan")


def confusion(genre, audio, labels=MOODS):
    """Rows = genre-based mood, columns = audio-based mood, all four moods always shown."""
    return pd.crosstab(
        pd.Categorical(pd.Series(genre), categories=labels),
        pd.Categorical(pd.Series(audio), categories=labels),
        rownames=["genre_mood"], colnames=["audio_mood"], dropna=False,
    )


def kappa(genre, audio, labels=MOODS):
    """Cohen's kappa; NaN when undefined (fewer than 2 rows, or both raters constant)."""
    if len(genre) < 2:
        return float("nan")
    with np.errstate(all="ignore"):
        k = cohen_kappa_score(list(genre), list(audio), labels=labels)
    return float(k)


def summarize(df, genre_col="genre_mood", audio_col="audio_mood"):
    return {
        "n": int(len(df)),
        "percent_agreement": percent_agreement(df[genre_col], df[audio_col]),
        "kappa": kappa(df[genre_col], df[audio_col]),
        "confusion": confusion(df[genre_col], df[audio_col]),
    }
