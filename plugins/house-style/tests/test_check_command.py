"""End-to-end tests for the bash-command hook."""

import json
import os
import subprocess
import sys
import unittest

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(PLUGIN, "hooks", "check_command.py")


def decide(command):
    payload = json.dumps({"tool_input": {"command": command}})
    result = subprocess.run(
        [sys.executable, HOOK], input=payload, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["hookSpecificOutput"]


def decide_raw(payload):
    result = subprocess.run(
        [sys.executable, HOOK], input=payload, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)["hookSpecificOutput"]


class TestDeny(unittest.TestCase):
    def test_commit_message(self):
        out = decide('git commit -m "a load-bearing claim"')
        self.assertEqual(out["permissionDecision"], "deny")
        self.assertIn("Buzzword", out["permissionDecisionReason"])

    def test_commit_inside_a_compound_command(self):
        out = decide('git add a.py && git commit -m "a load-bearing claim"')
        self.assertEqual(out["permissionDecision"], "deny")

    def test_pr_body(self):
        out = decide('gh pr create --title "Fix" --body "we delve into it"')
        self.assertEqual(out["permissionDecision"], "deny")

    def test_pr_body_with_an_equals_sign(self):
        out = decide('gh pr create --body="we delve into it"')
        self.assertEqual(out["permissionDecision"], "deny")

    def test_message_only_rule_applies(self):
        out = decide('git commit -m "ask the team about it"')
        self.assertEqual(out["permissionDecision"], "deny")

    def test_disguised_word(self):
        out = decide('git commit -m "a load--bearing claim"')
        self.assertEqual(out["permissionDecision"], "deny")

    def test_heredoc_body(self):
        command = 'git commit -F - <<EOF\na load-bearing claim\nEOF'
        self.assertEqual(decide(command)["permissionDecision"], "deny")

    def test_apostrophe_in_a_quoted_tag_heredoc(self):
        command = "git commit -F - <<'EOF'\ndon't ship a load-bearing claim\nEOF"
        self.assertEqual(decide(command)["permissionDecision"], "deny")

    def test_apostrophe_in_an_unquoted_tag_heredoc(self):
        command = "git commit -F - <<EOF\nit is the codebase's load-bearing part\nEOF"
        self.assertEqual(decide(command)["permissionDecision"], "deny")

    def test_gh_short_title_and_body_flags(self):
        out = decide('gh pr create -t "Fix" -b "we delve into it"')
        self.assertEqual(out["permissionDecision"], "deny")

    def test_gh_short_notes_flag(self):
        out = decide('gh release create v1 -n "we delve into it"')
        self.assertEqual(out["permissionDecision"], "deny")

    def test_body_file_equals_sign_heredoc(self):
        command = 'gh pr create --body-file=- <<EOF\na load-bearing claim\nEOF'
        self.assertEqual(decide(command)["permissionDecision"], "deny")


class TestAllow(unittest.TestCase):
    def test_grep_for_a_banned_word(self):
        out = decide('grep -rn "load-bearing" .')
        self.assertEqual(out["permissionDecision"], "allow")

    def test_clean_commit(self):
        out = decide('git commit -m "Add the cache eviction path"')
        self.assertEqual(out["permissionDecision"], "allow")

    def test_unrelated_command(self):
        out = decide("ls -la")
        self.assertEqual(out["permissionDecision"], "allow")

    def test_word_in_a_path_argument(self):
        out = decide("git add docs/load-bearing.md")
        self.assertEqual(out["permissionDecision"], "allow")

    def test_backticked_word_in_a_message(self):
        out = decide('git commit -m "Rename `load-bearing` in the rule text"')
        self.assertEqual(out["permissionDecision"], "allow")

    def test_unparsable_command(self):
        out = decide('git commit -m "unbalanced')
        self.assertEqual(out["permissionDecision"], "allow")

    def test_body_file_is_not_read(self):
        out = decide("gh pr create --body-file notes.md")
        self.assertEqual(out["permissionDecision"], "allow")

    def test_newline_before_an_unrelated_flag(self):
        command = 'git add .\ndocker run -m "we delve into it"'
        self.assertEqual(decide(command)["permissionDecision"], "allow")

    def test_newline_before_an_unrelated_double_dash_flag(self):
        command = 'git add .\nnpm run build -- --title "we delve into it"'
        self.assertEqual(decide(command)["permissionDecision"], "allow")

    def test_semicolon_attached_to_the_prior_word(self):
        command = 'git status; docker run -m "we delve into it"'
        self.assertEqual(decide(command)["permissionDecision"], "allow")

    def test_activation_gate_is_checked(self):
        out = decide('docker run -m 512m && git status')
        self.assertEqual(out["permissionDecision"], "allow")

    def test_segment_reset_is_checked(self):
        out = decide('git status && docker run -m "we delve into it"')
        self.assertEqual(out["permissionDecision"], "allow")


class TestMalformedPayload(unittest.TestCase):
    def test_top_level_list_allows(self):
        out = decide_raw("[]")
        self.assertEqual(out["permissionDecision"], "allow")

    def test_top_level_null_allows(self):
        out = decide_raw("null")
        self.assertEqual(out["permissionDecision"], "allow")

    def test_tool_input_not_a_dict_allows(self):
        out = decide_raw('{"tool_input": "oops"}')
        self.assertEqual(out["permissionDecision"], "allow")

    def test_command_not_a_string_allows(self):
        out = decide_raw('{"tool_input": {"command": ["git", "commit"]}}')
        self.assertEqual(out["permissionDecision"], "allow")


if __name__ == "__main__":
    unittest.main()
