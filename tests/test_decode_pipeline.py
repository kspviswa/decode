"""Tests for scripts/decode_pipeline.py --weekly mode and core collection."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
sys.path.insert(0, SCRIPTS)
import decode_pipeline as dp  # noqa: E402


def iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


class PipelineMainMixin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="decode_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def run_main(self, argv):
        args = ["decode_pipeline.py"] + argv
        with mock.patch.object(dp, "OUT", self.tmp), \
             mock.patch.object(sys, "argv", args):
            dp.main()
        return (json.load(open(os.path.join(self.tmp, "candidates.json"))),
                json.load(open(os.path.join(self.tmp, "shortlist.json"))),
                json.load(open(os.path.join(self.tmp, "seen.json"))))


class TestWeeklyFreshnessWindow(PipelineMainMixin):
    def fixtures(self):
        return {
            "arxiv_recent": {"title": "llm telecom paper today", "link": "https://a.example/0",
                             "date": iso(0), "source": "arXiv"},
            "arxiv_1d": {"title": "llm agent paper yesterday", "link": "https://a.example/1",
                         "date": iso(1), "source": "arXiv"},
            "arxiv_5d": {"title": "llm agents paper five days ago", "link": "https://a.example/5",
                         "date": iso(5), "source": "arXiv"},
            "arxiv_10d": {"title": "llm old paper ten days ago", "link": "https://a.example/10",
                          "date": iso(10), "source": "arXiv"},
            "hn_front": {"title": "hacker news llm item", "link": "https://news.ycombinator.com/1",
                         "date": iso(0), "source": "HN", "points": 777},
            "hn_algolia_6d": {"title": "hn weekly llm gem", "link": "https://news.ycombinator.com/2",
                              "date": iso(6), "source": "HN", "points": 55, "algolia": True},
        }

    def write_extra(self, items):
        path = os.path.join(self.tmp, "fixtures.json")
        with open(path, "w") as f:
            json.dump(items, f)
        return path

    def patch_collectors(self):
        fix = self.fixtures()
        paths = [
            mock.patch.object(dp, "collect_hn", return_value=[fix["hn_front"]]),
            mock.patch.object(dp, "collect_hn_algolia", return_value=[fix["hn_algolia_6d"]]),
            mock.patch.object(dp, "collect_reddit", return_value=[]),
            mock.patch.object(dp, "collect_mcp", return_value=[]),
            mock.patch.object(dp, "collect_mcp_general", return_value=[]),
        ]
        for p in paths:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in paths])
        arxiv_items = [fix["arxiv_recent"], fix["arxiv_1d"],
                       fix["arxiv_5d"], fix["arxiv_10d"]]
        return self.write_extra(arxiv_items), arxiv_items

    def test_weekly_keeps_full_past_week_and_calls_algolia(self):
        extra, arxiv_items = self.patch_collectors()
        candidates, shortlist, _ = self.run_main(["--weekly", "--extra", extra])
        titles = {c["title"] for c in candidates}
        # past-7-days items (injected arXiv + HN always kept) survive
        self.assertIn(arxiv_items[0]["title"], titles)
        self.assertIn(arxiv_items[1]["title"], titles)
        self.assertIn(arxiv_items[2]["title"], titles)   # 5 days ago -> weekly keeps
        self.assertIn("hacker news llm item", titles)
        self.assertIn("hn weekly llm gem", titles)
        self.assertNotIn(arxiv_items[3]["title"], titles)  # 10 days ago -> dropped

    def test_daily_drops_items_older_than_48h(self):
        extra, arxiv_items = self.patch_collectors()
        candidates, shortlist, _ = self.run_main(["--extra", extra])
        titles = {c["title"] for c in candidates}
        self.assertIn(arxiv_items[0]["title"], titles)
        self.assertIn(arxiv_items[1]["title"], titles)
        self.assertNotIn(arxiv_items[2]["title"], titles)  # 5 days ago -> daily drops
        self.assertNotIn(arxiv_items[3]["title"], titles)


class TestWeeklyShortlistTop8(PipelineMainMixin):
    def make_items(self):
        hn = []
        for i in range(10):
            hn.append({"title": f"llm agent infrastructure story number {i}",
                       "link": f"https://news.ycombinator.com/story/{i}",
                       "date": iso(0), "source": "HN", "points": 100 - i})
        linkedin = {"title": "A vendor marketing post without lane keywords",
                    "link": "https://www.linkedin.com/pulse/a",
                    "date": iso(1), "source": "LinkedIn", "content": ""}
        x = {"title": "A random x post with no keywords",
             "link": "https://x.com/user/status/1",
             "date": iso(1), "source": "X", "content": ""}
        return hn, linkedin, x

    def run_with_items(self, argv):
        hn, linkedin, x = self.make_items()
        patches = [
            mock.patch.object(dp, "collect_hn", return_value=hn),
            mock.patch.object(dp, "collect_hn_algolia", return_value=[]),
            mock.patch.object(dp, "collect_reddit", return_value=[]),
            mock.patch.object(dp, "collect_mcp", return_value=[linkedin, x]),
            mock.patch.object(dp, "collect_mcp_general", return_value=[]),
            mock.patch.object(dp, "collect_arxiv", return_value=[]),
        ]
        for p in patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patches])
        return self.run_main(argv)

    def test_weekly_per_lane_capacity_is_top_8(self):
        _, shortlist, _ = self.run_with_items(["--weekly"])
        self.assertEqual(len(shortlist["ai"]), 8)

    def test_daily_per_lane_capacity_stays_top_6(self):
        _, shortlist, _ = self.run_with_items([])
        self.assertEqual(len(shortlist["ai"]), 6)

    def test_reserved_sources_survive_into_shortlist(self):
        _, shortlist, _ = self.run_with_items(["--weekly"])
        all_links = []
        for lane_items in shortlist.values():
            all_links += [i["link"] for i in lane_items]
        self.assertTrue(any("linkedin.com" in l for l in all_links))
        self.assertTrue(any("x.com" in l for l in all_links))
        hn_titles = [i["title"] for lane_items in shortlist.values()
                     for i in lane_items if i["source"] == "HN"]
        self.assertGreaterEqual(len(hn_titles), 1)

    def test_shortlist_items_are_deduplicated(self):
        _, shortlist, _ = self.run_with_items(["--weekly"])
        all_links = [i["link"] for lane_items in shortlist.values() for i in lane_items]
        self.assertEqual(len(all_links), len(set(all_links)))


class TestRedditWindow(unittest.TestCase):
    def test_weekly_uses_week_rss_window(self):
        captured = {}

        def fake_http_get(url):
            captured["url"] = url
            return ("<rss><item><title>t</title><link>https://e.example/r</link>"
                    "<pubDate>Mon, 01 Sep 2026 00:00:00 GMT</pubDate></item></rss>")

        with mock.patch.object(dp, "http_get", fake_http_get):
            items = dp.collect_reddit(subs=("LocalLLaMA",), hours=168)
        self.assertIn("t=week", captured["url"])
        self.assertEqual(len(items), 1)

    def test_daily_uses_day_rss_window(self):
        captured = {}

        def fake_http_get(url):
            captured["url"] = url
            return "<rss></rss>"

        with mock.patch.object(dp, "http_get", fake_http_get):
            dp.collect_reddit(subs=("LocalLLaMA",), hours=48)
        self.assertIn("t=day", captured["url"])


class TestHnAlgoliaCollector(unittest.TestCase):
    def test_search_by_date_url_and_parse(self):
        hits = {
            "hits": [
                {"title": "A weekly telecom AI story", "url": "https://e.example/1",
                 "created_at": iso(3), "points": 42, "objectID": "98765"},
                {"title": "How to do structured retrieval", "url": "",
                 "created_at": iso(2), "points": 9, "objectID": "54321"},
            ]
        }

        captured = {}

        def fake_http_get(url):
            captured["url"] = url
            return json.dumps(hits)

        with mock.patch.object(dp, "http_get", fake_http_get):
            items = dp.collect_hn_algolia(hours=168, keywords=["telecom AI"], max_per_query=5)

        u = captured["url"]
        self.assertIn("search_by_date", u)
        self.assertIn("numericFilters=created_at_i%3E", u)
        self.assertIn("hitsPerPage=5", u)
        self.assertIn("telecom%20AI", u)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "A weekly telecom AI story")
        self.assertEqual(items[0]["source"], "HN")
        self.assertEqual(items[0]["points"], 42)
        self.assertEqual(items[1]["link"],
                         "https://news.ycombinator.com/item?id=54321")

    def test_algolia_cutoff_uses_hour_window(self):
        captured = {}

        def fake_http_get(url):
            captured["url"] = url
            return json.dumps({"hits": []})

        with mock.patch.object(dp, "http_get", fake_http_get):
            dp.collect_hn_algolia(hours=24, keywords=["k"])
        import time
        expected_min = str(int(time.time()) - 24 * 3600 - 60)
        extracted = captured["url"].split("created_at_i%3E")[1].split("&")[0]
        self.assertGreaterEqual(extracted, expected_min)


if __name__ == "__main__":
    unittest.main()