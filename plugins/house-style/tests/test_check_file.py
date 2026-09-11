"""End-to-end tests for the written-file hook."""

import json
import os
import subprocess
import sys
import tempfile
import unittest

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(PLUGIN, "hooks", "check_file.py")
EM_DASH = chr(0x2014)


def run(path):
    payload = json.dumps({"tool_input": {"file_path": path}})
    return subprocess.run(
        [sys.executable, HOOK],
        input=payload,
        capture_output=True,
        text=True,
    )


def written(name, body):
    handle = tempfile.NamedTemporaryFile("w", suffix=name, delete=False, encoding="utf-8")
    handle.write(body)
    handle.close()
    return handle.name


def written_bytes(name, body):
    handle = tempfile.NamedTemporaryFile("wb", suffix=name, delete=False)
    handle.write(body)
    handle.close()
    return handle.name


class TestCheckFile(unittest.TestCase):
    def setUp(self):
        self.paths = []

    def tearDown(self):
        for path in self.paths:
            os.unlink(path)

    def make(self, name, body):
        path = written(name, body)
        self.paths.append(path)
        return path

    def make_bytes(self, name, body):
        path = written_bytes(name, body)
        self.paths.append(path)
        return path

    def test_clean_markdown_passes(self):
        result = run(self.make(".md", "A plain sentence.\n"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")

    def test_em_dash_in_markdown_fails(self):
        result = run(self.make(".md", "a " + EM_DASH + " b\n"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("Em dash", result.stderr)

    def test_em_dash_in_source_fails(self):
        result = run(self.make(".go", "// a " + EM_DASH + " b\n"))
        self.assertEqual(result.returncode, 2)

    def test_word_in_markdown_fails(self):
        result = run(self.make(".md", "a load-bearing claim\n"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("Buzzword", result.stderr)

    def test_word_in_source_passes(self):
        result = run(self.make(".go", "var loadBearing = true // load-bearing\n"))
        self.assertEqual(result.returncode, 0)

    def test_non_ascii_in_powershell_fails(self):
        result = run(self.make(".ps1", "# café\n"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("Non-ASCII", result.stderr)

    def test_non_ascii_in_markdown_passes(self):
        result = run(self.make(".md", "café\n"))
        self.assertEqual(result.returncode, 0)

    def test_output_ends_with_the_rewrite_note(self):
        result = run(self.make(".md", "a load-bearing claim\n"))
        self.assertTrue(result.stderr.strip().endswith("disguise the word."))

    def test_missing_file_passes(self):
        result = run("/tmp/does-not-exist-9d2f.md")
        self.assertEqual(result.returncode, 0)

    def test_empty_payload_passes(self):
        result = subprocess.run(
            [sys.executable, HOOK], input="{}", capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_broken_payload_passes(self):
        result = subprocess.run(
            [sys.executable, HOOK], input="not json", capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)

    def test_skip_glob_passes(self):
        result = run(self.make("CLAUDE.md", "a " + EM_DASH + " b\n"))
        self.assertEqual(result.returncode, 0)

    def test_binary_file_passes(self):
        result = run(self.make_bytes(".md", b"\xff\xfe\x00\x01binary"))
        self.assertEqual(result.returncode, 0)

    def test_tool_input_wrong_shape_passes(self):
        result = subprocess.run(
            [sys.executable, HOOK],
            input=json.dumps({"tool_input": "x"}),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)

    def test_top_level_list_passes(self):
        result = subprocess.run(
            [sys.executable, HOOK], input="[]", capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")

    def test_top_level_null_passes(self):
        result = subprocess.run(
            [sys.executable, HOOK], input="null", capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")

    def test_output_pins_the_exact_shape(self):
        path = self.make(".md", "A clean line.\nThis is a load-bearing claim.\n")
        result = run(path)
        self.assertEqual(result.returncode, 2)
        expected = (
            "{}:2: Buzzword. Name the dependency.\n"
            "  This is a load-bearing claim.\n"
            "Rewrite the sentence. Do not split, hyphenate, or otherwise disguise the word.\n"
        ).format(path)
        self.assertEqual(result.stderr, expected)


if __name__ == "__main__":
    unittest.main()
