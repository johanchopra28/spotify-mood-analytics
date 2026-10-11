import math
import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis"))
import mood_stats  # noqa: E402


def frame(pairs):
    return pd.DataFrame(pairs, columns=["genre_mood", "audio_mood"])


class MoodStatsTests(unittest.TestCase):
    def test_perfect_agreement(self):
        df = frame([("calm", "calm"), ("upbeat", "upbeat"), ("intense", "intense"), ("mellow", "mellow")])
        r = mood_stats.summarize(df)
        self.assertEqual(r["percent_agreement"], 100.0)
        self.assertAlmostEqual(r["kappa"], 1.0)

    def test_kappa_matches_hand_calculation(self):
        # 2x2 textbook case: 20 both-A, 5 A/B, 10 B/A, 15 both-B -> po = 0.7, pe = 0.5, kappa = 0.4
        pairs = ([("calm", "calm")] * 20 + [("calm", "upbeat")] * 5 +
                 [("upbeat", "calm")] * 10 + [("upbeat", "upbeat")] * 15)
        r = mood_stats.summarize(frame(pairs))
        self.assertAlmostEqual(r["percent_agreement"], 70.0)
        self.assertAlmostEqual(r["kappa"], 0.4)

    def test_confusion_always_shows_all_four_moods(self):
        r = mood_stats.summarize(frame([("intense", "intense"), ("intense", "calm")]))
        cm = r["confusion"]
        self.assertEqual(list(cm.index), mood_stats.MOODS)
        self.assertEqual(list(cm.columns), mood_stats.MOODS)
        self.assertEqual(int(cm.loc["intense", "intense"]), 1)
        self.assertEqual(int(cm.loc["intense", "calm"]), 1)
        self.assertEqual(int(cm.values.sum()), 2)

    def test_kappa_undefined_for_tiny_or_constant_data(self):
        self.assertTrue(math.isnan(mood_stats.kappa(["calm"], ["calm"])))
        self.assertTrue(math.isnan(mood_stats.kappa(["calm", "calm"], ["calm", "calm"])))

    def test_systematic_disagreement_gives_negative_kappa(self):
        pairs = [("calm", "upbeat"), ("upbeat", "calm")] * 5
        self.assertLess(mood_stats.summarize(frame(pairs))["kappa"], 0)


if __name__ == "__main__":
    unittest.main()
