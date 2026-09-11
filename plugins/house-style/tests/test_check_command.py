"""End-to-end tests for the bash-command hook."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(PLUGIN, "hooks", "check_command.py")
CONFIG = tempfile.mkdtemp(prefix="house-style-config-")


def tearDownModule():
    shutil.rmtree(CONFIG, ignore_errors=True)


def invoke(payload, config_dir=None):
    """Run the hook with a config directory the test owns.

    The hook reads its optional user rules from CLAUDE_CONFIG_DIR. Inheriting
    the ambient one makes the outcome depend on whatever file the developer
    happens to have there.
    """
    env = dict(os.environ)
    env["CLAUDE_CONFIG_DIR"] = config_dir or CONFIG
    return subprocess.run(
        [sys.executable, HOOK], input=payload, capture_output=True, text=True, env=env
    )


def decide(command, config_dir=None):
    return decide_raw(json.dumps({"tool_input": {"command": command}}), config_dir)


def decide_raw(payload, config_dir=None):
    result = invoke(payload, config_dir)
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

    def test_no_verify_short_flag_does_not_swallow_the_message(self):
        out = decide('git commit -n -m "a load-bearing claim"')
        self.assertEqual(out["permissionDecision"], "deny")

    def test_no_verify_long_flag_still_denies(self):
        out = decide('git commit --no-verify -m "a load-bearing claim"')
        self.assertEqual(out["permissionDecision"], "deny")

    def test_gh_short_notes_flag_still_works_alongside_the_git_fix(self):
        out = decide('gh pr create -n "we delve into it"')
        self.assertEqual(out["permissionDecision"], "deny")

    def test_body_value_starting_with_a_dash_still_denies(self):
        out = decide('gh pr create --title "Fix" --body "- we delve into it"')
        self.assertEqual(out["permissionDecision"], "deny")

    def test_short_body_value_starting_with_a_dash_still_denies(self):
        out = decide('gh pr create --title "Fix" -b "- we delve into it"')
        self.assertEqual(out["permissionDecision"], "deny")

    def test_commit_message_starting_with_a_dash_still_denies(self):
        out = decide('git commit -m "-a load-bearing claim"')
        self.assertEqual(out["permissionDecision"], "deny")

    def test_body_from_a_command_substitution_heredoc(self):
        command = 'gh pr create --body "$(cat <<\'EOF\'\nwe delve into it\nEOF\n)"'
        self.assertEqual(decide(command)["permissionDecision"], "deny")

    def test_commit_message_from_a_command_substitution_heredoc(self):
        command = 'git commit -m "$(cat <<\'EOF\'\na load-bearing claim\nEOF\n)"'
        self.assertEqual(decide(command)["permissionDecision"], "deny")

    def test_clustered_short_flags(self):
        out = decide('git commit -am "a load-bearing claim"')
        self.assertEqual(out["permissionDecision"], "deny")

    def test_clustered_sign_off_flags(self):
        out = decide('git commit -sm "a load-bearing claim"')
        self.assertEqual(out["permissionDecision"], "deny")

    def test_clustered_quiet_flags(self):
        out = decide('git commit -aqm "a load-bearing claim"')
        self.assertEqual(out["permissionDecision"], "deny")

    def test_short_flag_with_an_attached_value(self):
        out = decide("git commit -m'a load-bearing claim'")
        self.assertEqual(out["permissionDecision"], "deny")

    def test_clustered_short_flag_with_an_attached_value(self):
        out = decide("git commit -am'a load-bearing claim'")
        self.assertEqual(out["permissionDecision"], "deny")

    def test_spaced_and_equals_forms_agree_on_a_dash_prefixed_value(self):
        spaced = decide('gh pr create --body "- we delve into it"')
        equals = decide('gh pr create --body="- we delve into it"')
        self.assertEqual(spaced["permissionDecision"], "deny")
        self.assertEqual(equals["permissionDecision"], "deny")


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
        out = decide('docker run -m "we delve into it" && git status')
        self.assertEqual(out["permissionDecision"], "allow")

    def test_gh_only_flag_is_inert_under_git(self):
        out = decide('git commit -b "we delve into it"')
        self.assertEqual(out["permissionDecision"], "allow")

    def test_git_only_flag_is_inert_under_gh(self):
        out = decide('gh pr create -m "we delve into it"')
        self.assertEqual(out["permissionDecision"], "allow")

    def test_segment_reset_is_checked(self):
        out = decide('git status && docker run -m "we delve into it"')
        self.assertEqual(out["permissionDecision"], "allow")

    def test_heredoc_without_git_or_gh(self):
        command = "cat <<EOF > notes.md\nwe delve into it\nEOF"
        self.assertEqual(decide(command)["permissionDecision"], "allow")

    def test_clustered_short_flags_without_a_message_flag(self):
        out = decide('git log -np "we delve into it"')
        self.assertEqual(out["permissionDecision"], "allow")


class TestReason(unittest.TestCase):
    def test_it_names_the_line(self):
        command = "git commit -F - <<EOF\nA clean line.\na load-bearing claim\nEOF"
        reason = decide(command)["permissionDecisionReason"]
        self.assertIn("line 2:", reason)

    def test_it_is_capped(self):
        body = "\n".join(["a load-bearing claim"] * 60)
        command = "git commit -F - <<EOF\n{}\nEOF".format(body)
        reason = decide(command)["permissionDecisionReason"]
        self.assertIn("... and 40 more.", reason)
        self.assertEqual(reason.count(" -> "), 20)
        self.assertLess(len(reason), 2000)


class TestBrokenUserRulesFile(unittest.TestCase):
    def setUp(self):
        self.config = tempfile.mkdtemp(prefix="house-style-broken-")
        path = os.path.join(self.config, "house-style.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{")

    def tearDown(self):
        shutil.rmtree(self.config, ignore_errors=True)

    def test_the_shipped_rules_still_deny(self):
        out = decide('git commit -m "a load-bearing claim"', config_dir=self.config)
        self.assertEqual(out["permissionDecision"], "deny")

    def test_a_clean_command_is_still_allowed(self):
        out = decide('git commit -m "Add the cache eviction path"', config_dir=self.config)
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
