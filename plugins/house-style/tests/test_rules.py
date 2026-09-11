"""Tests for the house-style rule engine."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

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


def small_rules_with_raw_double_dash():
    rules = small_rules()
    rules["words"] = list(rules["words"]) + [
        {"match": r"\w--\w|\s--\s", "message": "Double dash.", "raw": True}
    ]
    return rules


class TestRawWordRules(unittest.TestCase):
    def test_trips_the_double_dash_rule_on_the_raw_line(self):
        hits = engine.scan_file(
            "a well--known fact\n", small_rules_with_raw_double_dash(), "/tmp/a.md"
        )
        self.assertEqual(len(hits), 1)

    def test_does_not_trip_the_double_dash_rule_on_a_cli_flag(self):
        hits = engine.scan_file(
            "gh pr create --draft\n", small_rules_with_raw_double_dash(), "/tmp/a.md"
        )
        self.assertEqual(hits, [])

    def test_normalization_still_applies_to_a_rule_without_the_flag(self):
        hits = engine.scan_file("a load--bearing claim\n", small_rules(), "/tmp/a.md")
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


DOUBLE_DASH = r"(?:^|(?<=[\s(\[]))(?<!\]\()[^\s#/()\[\]]*\w--\w|\s--\s(?!\s*-)"

# The must-match and must-not-match strings for each shipped word rule, keyed
# by the rule's own pattern so the table stays tied to the rule it describes
# rather than to its position in the list.
WORD_RULE_CASES = {
    r"\bload-bearing\b": (["a load-bearing claim"], ["load bearing wall"]),
    r"\bsmoking gun\b": (
        ["found the smoking gun in the drawer"],
        ["smoking a cigarette outdoors"],
    ),
    r"\bstated fairly\b": (
        ["it can be stated fairly that this works"],
        ["a fair statement of the facts"],
    ),
    r"\bleverage[sd]?\b": (["we leveraged the connections"], ["pull the lever again"]),
    r"\butiliz(e|es|ed)\b": (["we utilized the resources"], ["run the utility script"]),
    r"\bin order to\b": (["in order to finish"], ["in order for this to work"]),
    r"\bprior to\b": (["prior to the meeting"], ["the prior year"]),
    r"\bin the event that\b": (["in the event that it fails"], ["in the event of rain"]),
    r"\bdelve[sd]?\b": (["let's delve into the details"], ["twelve open items"]),
    r"\bseamless(ly)?\b": (["a seamless integration"], ["a seamed edge"]),
    r"\b(colour|initialise|licence|cancelled)\b": (
        ["check the colour scheme"],
        ["check the color scheme"],
    ),
    DOUBLE_DASH: (
        ["a well--known fact", "The build failed -- the cache was stale."],
        [
            "gh pr create --draft",
            "[@MainActor](#global-actors--mainactor)",
            "Run npm test -- --coverage first.",
        ],
    ),
    r"\b(a|the) (maintainer|reviewer|maintainers|reviewers)\b|\bthe team\b": (
        ["ask the maintainer for advice"],
        ["ask a colleague for advice"],
    ),
}


class TestShippedWordRules(unittest.TestCase):
    def test_every_shipped_word_rule_has_a_case(self):
        shipped = [rule["match"] for rule in engine.load_rules(user_path="")["words"]]
        self.assertEqual(set(shipped), set(WORD_RULE_CASES))

    def test_each_shipped_word_rule_matches_and_rejects_as_intended(self):
        for rule in engine.load_rules(user_path="")["words"]:
            should_match, should_not_match = WORD_RULE_CASES[rule["match"]]
            single = {"skip": [], "characters": [], "words": [rule]}
            for text in should_match:
                with self.subTest(pattern=rule["match"], text=text):
                    self.assertTrue(
                        engine.scan_message(text, single),
                        "expected a match for {!r}".format(text),
                    )
            for text in should_not_match:
                with self.subTest(pattern=rule["match"], text=text):
                    self.assertEqual(
                        engine.scan_message(text, single),
                        [],
                        "expected no match for {!r}".format(text),
                    )


class TestUserRulesPath(unittest.TestCase):
    def test_expands_a_tilde_in_claude_config_dir(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": "~/some-config-dir"}):
            path = engine.user_rules_path()
        expected = os.path.join(os.path.expanduser("~/some-config-dir"), "house-style.json")
        self.assertEqual(path, expected)


if __name__ == "__main__":
    unittest.main()
