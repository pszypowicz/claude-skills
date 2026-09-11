#!/usr/bin/env python3
"""PostToolUse hook: report house-style violations in a written file."""

import fnmatch
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rules as engine  # noqa: E402

NEW_TEXT_FIELDS = ("content", "new_string")


def introduced_text(tool_input):
    """Return the text fragments this edit adds, or None when the payload does not say.

    Write carries the whole new file in content and Edit carries only the
    replacement in new_string. A blank fragment is dropped, since every line
    contains it and keeping it would match the whole file.
    """
    for field in NEW_TEXT_FIELDS:
        value = tool_input.get(field)
        if isinstance(value, str):
            return {line for line in value.splitlines() if line.strip()}
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
    introduced = introduced_text(tool_input)
    if introduced is not None:
        # An edit can replace part of a line, so the new text is a fragment of
        # the line it lands in rather than the whole of it. The line counts as
        # touched when it contains one of the fragments.
        hits = [
            hit
            for hit in hits
            if any(fragment in hit[1] for fragment in introduced)
        ]
    if not hits:
        return 0
    for number, raw, message in hits[:engine.MAX_LINES]:
        print("{}:{}: {}".format(path, number, message), file=sys.stderr)
        print("  {}".format(raw.strip()[:120]), file=sys.stderr)
    if len(hits) > engine.MAX_LINES:
        print("... and {} more.".format(len(hits) - engine.MAX_LINES), file=sys.stderr)
    print(engine.REWRITE_NOTE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
