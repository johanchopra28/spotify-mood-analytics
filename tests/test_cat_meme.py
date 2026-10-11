import os
import sys
import unittest

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import cat_meme  # noqa: E402


class FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def fake_get_factory(cats_by_tag):
    def fake_get(url, params=None, timeout=None):
        return FakeResp(cats_by_tag.get(params["tags"], []))
    return fake_get


def cat(cid, tags, mime="image/jpeg"):
    return {"id": cid, "tags": tags, "mimetype": mime}


class WeeklyMoodTests(unittest.TestCase):
    def setUp(self):
        self.now = pd.Timestamp("2026-10-11 20:00", tz="Asia/Kolkata")

    def frame(self, rows):
        df = pd.DataFrame(rows, columns=["listen_date", "mood", "minutes_listened"])
        df["listen_date"] = pd.to_datetime(df["listen_date"]).dt.tz_localize("Asia/Kolkata")
        return df

    def test_picks_most_minutes_in_window(self):
        df = self.frame([("2026-10-11", "calm", 10), ("2026-10-10", "intense", 30),
                         ("2026-10-09", "calm", 15)])
        self.assertEqual(cat_meme.weekly_dominant_mood(df, self.now), "intense")

    def test_ignores_days_older_than_a_week(self):
        df = self.frame([("2026-10-01", "intense", 999), ("2026-10-11", "calm", 5)])
        self.assertEqual(cat_meme.weekly_dominant_mood(df, self.now), "calm")

    def test_tie_is_deterministic(self):
        df = self.frame([("2026-10-11", "upbeat", 10), ("2026-10-11", "calm", 10)])
        self.assertEqual(cat_meme.weekly_dominant_mood(df, self.now), "calm")

    def test_empty_returns_none(self):
        self.assertIsNone(cat_meme.weekly_dominant_mood(pd.DataFrame(), self.now))


class CatPickTests(unittest.TestCase):
    def test_blocked_tags_and_types_are_filtered(self):
        data = {"Angry": [cat("good", ["Angry"]), cat("bad", ["Angry", "NSFW"]),
                          cat("gif", ["Angry"], "image/gif")]}
        ids = cat_meme.candidate_cat_ids("intense", fake_get_factory(data))
        self.assertEqual(ids, ["good"])

    def test_pick_is_stable_within_a_week_and_valid(self):
        data = {"Happy": [cat(f"c{i}", ["Happy"]) for i in range(10)]}
        get = fake_get_factory(data)
        a = cat_meme.get_cat_meme("upbeat", "2026-W41", get)
        b = cat_meme.get_cat_meme("upbeat", "2026-W41", get)
        self.assertEqual(a, b)
        self.assertRegex(a["url"], r"/cat/c\d+\?width=\d+$")
        self.assertIn(a["caption"], cat_meme.CAPTIONS["upbeat"])

    def test_returns_none_when_service_fails_or_empty(self):
        def boom(*args, **kwargs):
            raise RuntimeError("down")
        self.assertIsNone(cat_meme.get_cat_meme("calm", "2026-W41", boom))
        self.assertIsNone(cat_meme.get_cat_meme("calm", "2026-W41", fake_get_factory({})))

    def test_unknown_mood_returns_none(self):
        self.assertIsNone(cat_meme.get_cat_meme("angsty", "2026-W41", fake_get_factory({})))


if __name__ == "__main__":
    unittest.main()
