#!/usr/bin/env python3
"""PostToolUse hook: report house-style violations in a written file."""

import fnmatch
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rules as engine  # noqa: E402

MAX_LINES = 20
NEW_TEXT_FIELDS = ("content", "new_string")


def introduced_lines(tool_input):
    """Return the lines this edit adds, or None when the payload does not say.

    Write carries the whole new file in content and Edit carries only the
    replacement in new_string.
    """
    for field in NEW_TEXT_FIELDS:
        value = tool_input.get(field)
        if isinstance(value, str):
            return set(value.splitlines())
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return 0
    path = tool_input.get("file_path")
    if not isinstance(path, str) or not path or not os.path.isfile(path):
        return 0
    loaded = engine.load_rules()
    if any(fnmatch.fnmatch(path, glob) for glob in loaded["skip"]):
        return 0
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (UnicodeDecodeError, OSError):
        return 0
    # Scan the whole file, then keep only the violations this edit introduced.
    # Editing one line of a legacy document otherwise hands back every old
    # violation in it, and exit code 2 turns each one into work. Scanning the
    # fragment on its own would number the lines from the fragment rather than
    # from the file.
    hits = engine.scan_file(text, loaded, path)
    introduced = introduced_lines(tool_input)
    if introduced is not None:
        hits = [hit for hit in hits if hit[1] in introduced]
    if not hits:
        return 0
    for number, raw, message in hits[:MAX_LINES]:
        print("{}:{}: {}".format(path, number, message), file=sys.stderr)
        print("  {}".format(raw.strip()[:120]), file=sys.stderr)
    if len(hits) > MAX_LINES:
        print("... and {} more.".format(len(hits) - MAX_LINES), file=sys.stderr)
    print(engine.REWRITE_NOTE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
