import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import covers  # noqa: E402


def resp(status=200, payload=None):
    return mock.Mock(status_code=status, json=mock.Mock(return_value=payload or {}))


class CoverTests(unittest.TestCase):
    def test_only_spotify_https_hosts_are_accepted(self):
        self.assertTrue(covers.is_spotify_image("https://i.scdn.co/image/abc"))
        self.assertTrue(covers.is_spotify_image("https://image-cdn-ak.spotifycdn.com/image/abc"))
        self.assertFalse(covers.is_spotify_image("http://i.scdn.co/image/abc"))
        self.assertFalse(covers.is_spotify_image("https://evil.example.com/i.scdn.co"))
        self.assertFalse(covers.is_spotify_image("https://i.scdn.co.evil.com/x"))
        self.assertFalse(covers.is_spotify_image("javascript:alert(1)"))

    def test_pick_image_prefers_300px(self):
        imgs = [{"url": "https://i.scdn.co/image/big", "width": 640},
                {"url": "https://i.scdn.co/image/mid", "width": 300},
                {"url": "https://i.scdn.co/image/small", "width": 64}]
        self.assertEqual(covers.pick_image(imgs), "https://i.scdn.co/image/mid")
        self.assertIsNone(covers.pick_image([{"url": "https://evil.com/x", "width": 300}]))
        self.assertIsNone(covers.pick_image([]))

    def test_oembed_success_and_failures(self):
        ok = resp(200, {"thumbnail_url": "https://image-cdn-ak.spotifycdn.com/image/x"})
        self.assertEqual(covers.oembed_cover("t1", lambda *a, **k: ok), "https://image-cdn-ak.spotifycdn.com/image/x")
        self.assertIsNone(covers.oembed_cover("t1", lambda *a, **k: resp(404)))
        self.assertIsNone(covers.oembed_cover("t1", lambda *a, **k: resp(200, {"thumbnail_url": "https://evil.com/x"})))

        def boom(*a, **k):
            raise RuntimeError("offline")
        self.assertIsNone(covers.oembed_cover("t1", boom))

    def test_fetch_missing_uses_known_first(self):
        calls = []

        def http(url, params=None, timeout=None):
            calls.append(params["url"])
            return resp(200, {"thumbnail_url": "https://i.scdn.co/image/fetched"})
        out = covers.fetch_missing(["a", "b"], {"a": "https://i.scdn.co/image/known"}, http, pause=0)
        self.assertEqual(out["a"], "https://i.scdn.co/image/known")
        self.assertEqual(out["b"], "https://i.scdn.co/image/fetched")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
