#!/usr/bin/env python3
"""PostToolUse hook: report house-style violations in a written file."""

import fnmatch
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rules as engine  # noqa: E402

MAX_LINES = 20


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not path or not os.path.isfile(path):
        return 0
    loaded = engine.load_rules()
    if any(fnmatch.fnmatch(path, glob) for glob in loaded["skip"]):
        return 0
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (UnicodeDecodeError, OSError):
        return 0
    hits = engine.scan_file(text, loaded, path)
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
