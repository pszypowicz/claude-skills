"""Tests for the house-style rule engine."""

import json
import os
import sys
import tempfile
import unittest

HOOKS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks")
sys.path.insert(0, HOOKS)

import rules as engine  # noqa: E402

EM_DASH = "\u2014"


def small_rules():
    return {
        "skip": [],
        "characters": [{"match": EM_DASH, "message": "Em dash.", "files": "*"}],
        "words": [
            {"match": r"\bload-bearing\b", "message": "Buzzword."},
            {"match": r"\bthe team\b", "message": "Write you.", "surface": "message"},
        ],
    }


class TestNormalize(unittest.TestCase):
    def test_collapses_a_hyphen_run(self):
        self.assertEqual(engine.normalize("load--bearing"), "load-bearing")

    def test_drops_a_zero_width_space(self):
        self.assertEqual(engine.normalize("load\u200b-bearing"), "load-bearing")

    def test_lowercases(self):
        self.assertEqual(engine.normalize("Delve"), "delve")


class TestMerge(unittest.TestCase):
    def test_appends_a_user_word(self):
        merged = engine.merge_rules(small_rules(), {"words": [{"match": "moo", "message": "No."}]})
        self.assertEqual(len(merged["words"]), 3)

    def test_remove_drops_a_shipped_rule(self):
        merged = engine.merge_rules(small_rules(), {"remove": [r"\bload-bearing\b"]})
        self.assertEqual([rule["match"] for rule in merged["words"]], [r"\bthe team\b"])

    def test_load_rules_reads_a_user_file(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"words": [{"match": "moo", "message": "No."}]}, handle)
            path = handle.name
        try:
            loaded = engine.load_rules(user_path=path)
            self.assertIn("moo", [rule["match"] for rule in loaded["words"]])
        finally:
            os.unlink(path)


class TestScanFile(unittest.TestCase):
    def test_finds_a_word_in_markdown(self):
        hits = engine.scan_file("a load-bearing claim\n", small_rules(), "/tmp/a.md")
        self.assertEqual(len(hits), 1)

    def test_ignores_a_word_in_source_code(self):
        hits = engine.scan_file("a load-bearing claim\n", small_rules(), "/tmp/a.go")
        self.assertEqual(hits, [])

    def test_ignores_a_word_in_a_fenced_block(self):
        text = "intro\n```\nload-bearing\n```\ntail\n"
        self.assertEqual(engine.scan_file(text, small_rules(), "/tmp/a.md"), [])

    def test_ignores_a_word_in_an_inline_span(self):
        text = "the `load-bearing` flag\n"
        self.assertEqual(engine.scan_file(text, small_rules(), "/tmp/a.md"), [])

    def test_finds_a_character_inside_a_fenced_block(self):
        text = "intro\n```\na " + EM_DASH + " b\n```\n"
        self.assertEqual(len(engine.scan_file(text, small_rules(), "/tmp/a.md")), 1)

    def test_finds_a_disguised_word(self):
        hits = engine.scan_file("a load--bearing claim\n", small_rules(), "/tmp/a.md")
        self.assertEqual(len(hits), 1)

    def test_skips_a_message_only_rule(self):
        hits = engine.scan_file("ask the team\n", small_rules(), "/tmp/a.md")
        self.assertEqual(hits, [])

    def test_reports_the_raw_line_and_number(self):
        hits = engine.scan_file("one\ntwo load-bearing\n", small_rules(), "/tmp/a.md")
        self.assertEqual(hits[0][0], 2)
        self.assertEqual(hits[0][1], "two load-bearing")


class TestScanMessage(unittest.TestCase):
    def test_applies_a_message_only_rule(self):
        hits = engine.scan_message("ask the team", small_rules())
        self.assertEqual(len(hits), 1)

    def test_applies_a_shared_rule(self):
        hits = engine.scan_message("a load-bearing claim", small_rules())
        self.assertEqual(len(hits), 1)


class TestDefaultRules(unittest.TestCase):
    def test_the_shipped_file_parses(self):
        loaded = engine.load_rules(user_path="")
        self.assertTrue(loaded["words"])
        self.assertTrue(loaded["characters"])

    def test_no_shipped_pattern_holds_a_literal_em_dash_outside_an_escape(self):
        path = os.path.join(engine.plugin_root(), "rules", "default.json")
        with open(path, "rb") as handle:
            self.assertNotIn(EM_DASH.encode("utf-8"), handle.read())


if __name__ == "__main__":
    unittest.main()
