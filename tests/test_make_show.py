import json
import os
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "scripts")
import sys

sys.path.insert(0, SCRIPTS)
import make_show as ms  # noqa: E402


def make_story(title, cat, day, link, source="APocrypha"):
    return {
        "title": title,
        "date": day,
        "categories": cat if isinstance(cat, list) else [cat],
        "tags": list(cat) if isinstance(cat, list) else [cat],
        "source": source,
        "domain": "example.com",
        "link": link,
        "tldr": ["A short tldr."],
        "why": "Why read it.",
    }


def write_stories(day_dir, stories):
    import yaml
    os.makedirs(day_dir, exist_ok=True)
    with open(os.path.join(day_dir, "stories.yml"), "w") as f:
        yaml.safe_dump(stories, f, default_flow_style=False)


class MakeShowBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="make_show_test_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.posts = os.path.join(self.tmp, "posts")
        self.work = os.path.join(self.tmp, "work")
        os.makedirs(self.posts, exist_ok=True)
        os.makedirs(self.work, exist_ok=True)

    def marker_path(self):
        return os.path.join(self.work, "last_show.json")

    def script_path(self):
        return os.path.join(self.work, "show_script.json")


class TestAggregation(MakeShowBase):
    def test_aggregates_stories_since_last_show_sorted(self):
        # two weekly editions after last show + one BEFORE it (excluded)
        write_stories(os.path.join(self.posts, "2026-08-15"),
                      [make_story("older era story", "ai-infra", "2026-08-15", "https://old.example/1")])
        write_stories(os.path.join(self.posts, "2026-08-29"),
                      [make_story("week1 story", "llm-agents", "2026-08-29", "https://w1.example/1")])
        write_stories(os.path.join(self.posts, "2026-09-05"),
                      [make_story("week2 story a", "security", "2026-09-05", "https://w2.example/a"),
                       make_story("week2 story b", "ai-ran", "2026-09-05", "https://w2.example/b")])
        # non-date dir must be ignored
        os.makedirs(os.path.join(self.posts, "not-a-date"), exist_ok=True)

        dirs = ms.digest_dirs_since("2026-08-20", self.posts)
        self.assertEqual([os.path.basename(d) for d in dirs],
                         ["2026-08-29", "2026-09-05"])

        stories = ms.aggregate_stories(dirs)
        self.assertEqual(len(stories), 3)
        self.assertEqual(stories[0]["day"], "2026-08-29")
        self.assertEqual(stories[1]["day"], "2026-09-05")
        self.assertEqual(stories[2]["day"], "2026-09-05")
        self.assertEqual(
            {s["title"] for s in stories},
            {"week1 story", "week2 story a", "week2 story b"})

    def test_load_stories_handles_missing_or_bad_yaml(self):
        self.assertEqual(ms.load_stories(self.posts), [])
        os.makedirs(os.path.join(self.posts, "2026-09-01"), exist_ok=True)
        self.assertEqual(ms.load_stories(os.path.join(self.posts, "2026-09-01")), [])

    def test_marker_defaults_to_epoch_when_missing(self):
        self.assertEqual(ms.read_marker(self.marker_path()), "1970-01-01")


class TestSectionGrouping(MakeShowBase):
    def test_section_for_maps_categories(self):
        cases = {
            "ai-ran": "Networks · 5G & 6G",
            "slicing": "Networks · 5G & 6G",
            "security": "Security",
            "llm-agents": "AI & Models",
            "edge-inference": "AI & Models",
            "m-and-a": "Business & Funding",
            "digital-twin": "Research & World Models",
            "world-models": "Research & World Models",
        }
        for cat, expected in cases.items():
            self.assertEqual(ms.section_for([cat]), expected, cat)

    def test_section_for_falls_back_to_research(self):
        self.assertEqual(ms.section_for(["unordered-unknown-thing"]),
                         "Research & World Models")

    def test_group_by_section_keeps_all_sections_and_counts(self):
        stories = [
            make_story("n1", "ai-ran", "2026-09-05", "https://e/1"),
            make_story("s1", "security", "2026-09-05", "https://e/2"),
            make_story("a1", "llm-agents", "2026-09-05", "https://e/3"),
            make_story("a2", "local-llm", "2026-09-05", "https://e/4"),
            make_story("u1", "mystery-cat", "2026-09-05", "https://e/5"),
        ]
        groups = ms.group_by_section(stories)
        self.assertEqual(set(groups.keys()), set(ms.SECTION_ORDER))
        self.assertEqual(len(groups["Networks · 5G & 6G"]), 1)
        self.assertEqual(len(groups["Security"]), 1)
        self.assertEqual(len(groups["AI & Models"]), 2)
        self.assertEqual(len(groups["Business & Funding"]), 0)
        self.assertEqual(len(groups["Research & World Models"]), 1)


class TestWordCountValidation(MakeShowBase):
    def build_script(self, words_per_line, n_lines, in_target=True):
        _ = in_target
        lines = [{"speaker": "avery" if i % 2 == 0 else "jordan",
                  "text": ("word " * words_per_line).strip(), "gap_after": 0.5}
                 for i in range(n_lines)]
        return {"title": "Decode Show — X to Y", "lines": lines}

    def test_count_words(self):
        script = {"lines": [
            {"text": "one two three"},
            {"text": "four five"},
        ]}
        self.assertEqual(ms.count_words(script), 5)

    def test_validate_script_within_target(self):
        script = self.build_script(1100, 4)  # ~4400 words
        ok, errors, n = ms.validate_script(script)
        self.assertTrue(ok, errors)
        self.assertGreaterEqual(n, ms.WORD_TARGET_MIN)
        self.assertLessEqual(n, ms.WORD_TARGET_MAX)

    def test_validate_script_word_count_outside_target(self):
        script = {"title": "t", "lines": [{"speaker": "avery", "text": "short"}]}
        ok, errors, n = ms.validate_script(script)
        self.assertFalse(ok)
        self.assertEqual(n, 1)
        self.assertIn(f"word count 1 outside target", errors[0])

    def test_validate_script_schema_errors(self):
        bad = {"lines": [{"speaker": "neerja", "text": "who?"},
                         {"speaker": "jordan", "text": ""},
                         {"text": "no speaker"}]}
        ok, errors, n = ms.validate_script(bad)
        self.assertFalse(ok)
        self.assertTrue(any("neerja" in e for e in errors))
        self.assertTrue(any("empty 'text'" in e for e in errors))


class TestScaffoldAndIdempotency(MakeShowBase):
    def build_day(self):
        write_stories(os.path.join(self.posts, "2026-08-29"),
                      [make_story("w1", "llm-agents", "2026-08-29", "https://w1/1")])
        write_stories(os.path.join(self.posts, "2026-09-05"),
                      [make_story("w2", "ai-ran", "2026-09-05", "https://w2/1")])

    def test_build_scaffold_meta(self):
        self.build_day()
        rep = ms.assemble(posts_dir=self.posts, marker=self.marker_path(),
                          script_path=self.script_path(), today="2026-09-05")
        self.assertEqual(rep["status"], "assembled")
        self.assertEqual(rep["story_count"], 2)
        self.assertEqual(rep["first_day"], "2026-08-29")
        self.assertEqual(rep["last_day"], "2026-09-05")
        script = json.load(open(self.script_path()))
        self.assertEqual(script["title"], "Decode Show — 2026-08-29 to 2026-09-05")
        self.assertEqual(script["lines"], [])
        self.assertEqual(script["_meta"]["word_target_min"], 4300)
        self.assertEqual(script["_meta"]["word_target_max"], 5200)
        self.assertEqual(script["_meta"]["covered_days"],
                         ["2026-08-29", "2026-09-05"])
        self.assertEqual(script["_meta"]["sections"]["AI & Models"], 1)
        self.assertEqual(script["_meta"]["sections"]["Networks · 5G & 6G"], 1)

    def test_does_not_clobber_existing_dialogue(self):
        self.build_day()
        ms.assemble(posts_dir=self.posts, marker=self.marker_path(),
                    script_path=self.script_path(), today="2026-09-05")
        with open(self.script_path()) as f:
            script = json.load(f)
        script["lines"] = [{"speaker": "avery", "text": "real dialogue", "gap_after": 0.5}]
        with open(self.script_path(), "w") as f:
            json.dump(script, f)
        rep = ms.assemble(posts_dir=self.posts, marker=self.marker_path(),
                          script_path=self.script_path(), today="2026-09-05")
        self.assertFalse(rep["wrote"])
        with open(self.script_path()) as f:
            script2 = json.load(f)
        self.assertEqual(script2["lines"][0]["text"], "real dialogue")

    def test_already_built_today_exits(self):
        ms.write_marker(self.marker_path(), when="2026-09-05")
        self.build_day()
        rep = ms.assemble(posts_dir=self.posts, marker=self.marker_path(),
                          script_path=self.script_path(), today="2026-09-05")
        self.assertEqual(rep["status"], "already-built")
        self.assertFalse(os.path.exists(self.script_path()))

    def test_nothing_new_when_no_digests(self):
        rep = ms.assemble(posts_dir=self.posts, marker=self.marker_path(),
                          script_path=self.script_path(), today="2026-09-05")
        self.assertEqual(rep["status"], "nothing-new")


class TestMarkerAndPushFlow(MakeShowBase):
    def test_write_then_read_marker(self):
        ms.write_marker(self.marker_path(), when="2026-09-05")
        self.assertEqual(ms.read_marker(self.marker_path()), "2026-09-05")

    def test_push_and_mark_success_writes_marker(self):
        with mock.patch.object(ms, "push_mp3",
                                        return_value=(201, {"id": "book9", "duplicate": False})), \
             mock.patch.object(ms, "verify_complete",
                                        return_value=(True, {"id": "book9", "state": "complete"})), \
             mock.patch.object(ms, "write_marker", wraps=ms.write_marker) as wm:
            rep = ms.push_and_mark("/tmp/x.mp3", "2026-08-29", "2026-09-05", self.marker_path())
        self.assertEqual(rep["status"], "pushed")
        self.assertEqual(rep["shravana_book_id"], "book9")
        wm.assert_called_once_with(self.marker_path())
        self.assertEqual(ms.read_marker(self.marker_path()), date.today().isoformat())

    def test_push_and_mark_duplicate_also_writes_marker(self):
        with mock.patch.object(ms, "push_mp3",
                                        return_value=(200, {"id": "book9", "duplicate": True})) as pm, \
             mock.patch.object(ms, "verify_complete") as vc:
            rep = ms.push_and_mark("/tmp/x.mp3", "2026-08-29", "2026-09-05", self.marker_path())
        pm.assert_called_once()
        vc.assert_not_called()
        self.assertEqual(rep["shravana_book_id"], "book9")
        self.assertEqual(ms.read_marker(self.marker_path()), date.today().isoformat())

    def test_push_and_mark_failure_does_not_write_marker(self):
        with mock.patch.object(ms, "push_mp3",
                                        return_value=(500, {"error": "boom"})):
            with self.assertRaises(RuntimeError):
                ms.push_and_mark("/tmp/x.mp3", "2026-08-29", "2026-09-05", self.marker_path())
        self.assertFalse(os.path.exists(self.marker_path()))


class TestPushVerify(unittest.TestCase):
    def setUp(self):
        self.url_requests = []
        self.tmp = tempfile.mkdtemp(prefix="push_verify_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.mp3 = os.path.join(self.tmp, "fake.mp3")
        with open(self.mp3, "wb") as f:
            f.write(b"FakeMp3Bytes")

    def fake_urlopen(self, req, timeout=None):
        self.url_requests.append(req)
        class Resp:
            status = 201

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"id": "b123", "duplicate": false}'
        return Resp()

    def test_push_mp3_builds_correct_request(self):
        with mock.patch.object(ms.urllib.request, "urlopen", self.fake_urlopen):
            status, body = ms.push_mp3(self.mp3, "2026-08-29", "2026-09-05")
        self.assertEqual(status, 201)
        self.assertEqual(body["id"], "b123")
        req = self.url_requests[0]
        self.assertEqual(req.get_method(), "POST")
        self.assertIn("filename=Decode+Show+-+2026-08-29+to+2026-09-05.mp3", req.full_url)
        self.assertIn("category=podcast", req.full_url)
        self.assertIn("application/octet-stream", req.headers.get("Content-type", ""))
        self.assertEqual(req.data, b"FakeMp3Bytes")

    def test_verify_complete_polls(self):
        with mock.patch.object(ms, "fetch_book", return_value={"state": "complete"}), \
             mock.patch.object(ms.time, "sleep", return_value=None):
            ok, book = ms.verify_complete("b123", sleep=0.0)
        self.assertTrue(ok)
        self.assertEqual(book["state"], "complete")


if __name__ == "__main__":
    unittest.main()