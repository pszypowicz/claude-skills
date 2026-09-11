#!/usr/bin/env python3
"""PreToolUse hook: deny a command whose message text breaks the house style."""

import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rules as engine  # noqa: E402

VALUE_FLAGS = {"-m", "--message", "--body", "--title", "--notes"}
FILE_FLAGS = {"-F", "--file", "--body-file"}
BREAKS = {"&&", "||", ";", "|", "&"}
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?")


def heredoc_bodies(command):
    """Return the text between each heredoc marker and its closing line."""
    bodies = []
    for match in HEREDOC.finditer(command):
        after = command[match.end():]
        closing = re.search(
            r"^\s*{}\s*$".format(re.escape(match.group(1))), after, re.MULTILINE
        )
        bodies.append(after[: closing.start()] if closing else after)
    return bodies


def messages(command):
    """Return every message string that the command hands to git or gh."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []
    found = []
    active = False
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in BREAKS:
            active = False
            index += 1
            continue
        if os.path.basename(token) in ("git", "gh"):
            active = True
            index += 1
            continue
        if active and token in VALUE_FLAGS and index + 1 < len(tokens):
            found.append(tokens[index + 1])
            index += 2
            continue
        if active and token in FILE_FLAGS and index + 1 < len(tokens):
            if tokens[index + 1] == "-":
                found.extend(heredoc_bodies(command))
            index += 2
            continue
        name, sign, inline = token.partition("=")
        if active and sign and name in VALUE_FLAGS:
            found.append(inline)
        index += 1
    return found


def decision(reason=None):
    output = {"hookEventName": "PreToolUse"}
    if reason:
        output["permissionDecision"] = "deny"
        output["permissionDecisionReason"] = reason
    else:
        output["permissionDecision"] = "allow"
    return {"hookSpecificOutput": output}


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        print(json.dumps(decision()))
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    loaded = engine.load_rules()
    lines = []
    for text in messages(command):
        for _, raw, message in engine.scan_message(text, loaded):
            lines.append("{} -> {}".format(raw.strip()[:80], message))
    if lines:
        reason = "House style: " + " | ".join(lines) + " " + engine.REWRITE_NOTE
        print(json.dumps(decision(reason)))
    else:
        print(json.dumps(decision()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
