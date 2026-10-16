import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import lookup  # noqa: E402

ID = "4UKxN05yigVjLcwnhcbQRK"


def resp(status=200, payload=None):
    return mock.Mock(status_code=status, json=mock.Mock(return_value=payload or {}))


class ParseTests(unittest.TestCase):
    def test_accepts_links_uris_and_bare_ids(self):
        for text in [f"https://open.spotify.com/track/{ID}", f"https://open.spotify.com/track/{ID}?si=abc123",
                     f"https://open.spotify.com/intl-de/track/{ID}", f"spotify:track:{ID}", ID, f"  {ID}  "]:
            self.assertEqual(lookup.parse_track_id(text), ID, text)

    def test_rejects_everything_else(self):
        for text in ["", None, "hello", "https://open.spotify.com/album/" + ID, "https://evil.com/track/" + ID,
                     "spotify:album:" + ID, ID + "x", "https://open.spotify.com/track/short"]:
            self.assertIsNone(lookup.parse_track_id(text), text)


class AudioMoodTests(unittest.TestCase):
    def test_quadrants_and_cutoff(self):
        self.assertEqual(lookup.audio_mood(0.7, 0.8), "upbeat")
        self.assertEqual(lookup.audio_mood(0.3, 0.8), "intense")
        self.assertEqual(lookup.audio_mood(0.7, 0.2), "calm")
        self.assertEqual(lookup.audio_mood(0.3, 0.2), "mellow")
        self.assertEqual(lookup.audio_mood(0.5, 0.5), "upbeat")   # the cut-off belongs to the high side
        self.assertIsNone(lookup.audio_mood(None, 0.5))


class VoteTests(unittest.TestCase):
    seed = {"hip hop": "intense", "bhangra": "upbeat", "punjabi": "upbeat", "folk": "mellow"}

    def test_majority_and_case_insensitive(self):
        v = lookup.vote([("Bhangra", 100), ("hip hop", 25), ("Hip Hop", 20), ("desi", 17)], self.seed)
        self.assertEqual(v["counts"]["intense"], 2)
        self.assertEqual(v["counts"]["upbeat"], 1)
        self.assertEqual(v["winner"], "intense")
        self.assertEqual(v["how"], "clear majority")

    def test_low_weight_tags_and_the_top_five_limit(self):
        tags = [("bhangra", 100), ("x1", 90), ("x2", 80), ("x3", 70), ("x4", 60), ("hip hop", 50), ("hip hop", 40)]
        v = lookup.vote(tags, self.seed)           # only the first five are used, so hip hop never votes
        self.assertEqual(v["winner"], "upbeat")
        self.assertFalse(v["per_tag"][-1]["used"])
        v = lookup.vote([("hip hop", 9), ("folk", 5)], self.seed)   # below weight 10, nothing votes
        self.assertIsNone(v["winner"])
        self.assertEqual(v["how"], "no tag maps to a mood")

    def test_tie_goes_to_the_alphabetically_earlier_mood(self):
        v = lookup.vote([("hip hop", 50), ("bhangra", 40)], self.seed)
        self.assertEqual((v["winner"], v["how"]), ("intense", "tie, broken alphabetically"))

    def test_single_tag(self):
        self.assertEqual(lookup.vote([("folk", 30)], self.seed)["how"], "one tag decided it")


class FetchTests(unittest.TestCase):
    def test_reccobeats_found_missing_and_errors(self):
        row = {"href": f"https://open.spotify.com/track/{ID}", "valence": 0.35, "energy": 0.67}
        self.assertEqual(lookup.fetch_reccobeats(ID, lambda *a, **k: resp(200, {"content": [row]})), row)
        self.assertIsNone(lookup.fetch_reccobeats(ID, lambda *a, **k: resp(200, {"content": []})))
        other = {"href": "https://open.spotify.com/track/ZZZZZZZZZZZZZZZZZZZZZZ"}
        self.assertIsNone(lookup.fetch_reccobeats(ID, lambda *a, **k: resp(200, {"content": [other]})))
        with self.assertRaises(lookup.LookupFailed):
            lookup.fetch_reccobeats(ID, lambda *a, **k: resp(500))

        def boom(*a, **k):
            raise RuntimeError("offline")
        with self.assertRaises(lookup.LookupFailed):
            lookup.fetch_reccobeats(ID, boom)

    def test_lastfm_artist_parses_weights_and_stats(self):
        def get(url, params=None, timeout=None):
            if params["method"] == "artist.gettoptags":
                return resp(200, {"toptags": {"tag": [{"name": "Bhangra", "count": 100}, {"name": "hip hop", "count": "25"}]}})
            return resp(200, {"artist": {"name": "Karan Aujla", "stats": {"listeners": "126476", "playcount": "9822643"},
                                         "similar": {"artist": [{"name": "Diljit Dosanjh"}]}}})
        a = lookup.lastfm_artist("karan aujla", "key", get)
        self.assertEqual(a["tags"], [("Bhangra", 100), ("hip hop", 25)])
        self.assertEqual((a["listeners"], a["playcount"], a["similar"]), (126476, 9822643, ["Diljit Dosanjh"]))

    def test_lastfm_needs_a_key(self):
        with self.assertRaises(lookup.LookupFailed):
            lookup.lastfm_artist("x", None, lambda *a, **k: resp())

    def test_spotify_track_details_and_not_found(self):
        client = mock.Mock()
        client.track.return_value = {
            "id": ID, "name": "Taaj", "artists": [{"name": "tricksingh", "id": "a1"}, {"name": "Eyepatch", "id": "a2"}],
            "album": {"name": "Taaj", "release_date": "2025-07-29",
                      "images": [{"url": "https://i.scdn.co/image/x", "width": 300}]},
            "duration_ms": 182400, "external_ids": {"isrc": "INUM72500764"}, "explicit": False}
        t = lookup.fetch_spotify_track(ID, client)
        self.assertEqual((t["name"], [a["name"] for a in t["artists"]], t["isrc"]), ("Taaj", ["tricksingh", "Eyepatch"], "INUM72500764"))
        self.assertEqual(t["image"], "https://i.scdn.co/image/x")
        err = Exception("nope")
        err.http_status = 404
        client.track.side_effect = err
        with self.assertRaises(lookup.LookupFailed):
            lookup.fetch_spotify_track(ID, client)


if __name__ == "__main__":
    unittest.main()
