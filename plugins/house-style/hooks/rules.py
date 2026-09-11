"""Load, merge, and apply the house-style rules."""

import fnmatch
import json
import os
import re

PROSE_SUFFIXES = (".md", ".txt", ".mdx")
MARKDOWN_SUFFIXES = (".md", ".mdx")
ZERO_WIDTH = dict.fromkeys([0x200B, 0x200C, 0x200D, 0xFEFF])
HYPHEN_RUN = re.compile(r"-{2,}")
INLINE_CODE = re.compile(r"`[^`]*`")
FENCE = re.compile(r"^\s*(?:```|~~~)")
REWRITE_NOTE = "Rewrite the sentence. Do not split, hyphenate, or otherwise disguise the word."


def plugin_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def user_rules_path():
    config = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    return os.path.join(config, "house-style.json")


def load_rules(user_path=None):
    """Return the shipped rules, merged with the user file when one exists."""
    shipped = os.path.join(plugin_root(), "rules", "default.json")
    with open(shipped, encoding="utf-8") as handle:
        loaded = json.load(handle)
    for key in ("skip", "characters", "words"):
        loaded.setdefault(key, [])
    path = user_rules_path() if user_path is None else user_path
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            return merge_rules(loaded, json.load(handle))
    return loaded


def merge_rules(base, extra):
    merged = {
        key: list(base[key]) + list(extra.get(key, []))
        for key in ("skip", "characters", "words")
    }
    drop = set(extra.get("remove", []))
    for key in ("characters", "words"):
        merged[key] = [rule for rule in merged[key] if rule["match"] not in drop]
    return merged


def normalize(line):
    """Fold the tricks a writer can use to slip a banned word past a pattern."""
    return HYPHEN_RUN.sub("-", line.translate(ZERO_WIDTH)).lower()


def _word_rules(rules, surface):
    selected = []
    for rule in rules["words"]:
        if rule.get("surface", "both") in ("both", surface):
            selected.append((re.compile(rule["match"], re.IGNORECASE), rule["message"]))
    return selected


def _character_rules(rules, path):
    selected = []
    for rule in rules["characters"]:
        globs = [glob.strip() for glob in rule.get("files", "*").split(",")]
        if any(fnmatch.fnmatch(path, glob) for glob in globs):
            selected.append((re.compile(rule["match"]), rule["message"]))
    return selected


def _scan(text, rules, path, surface, check_words, markdown):
    characters = _character_rules(rules, path)
    words = _word_rules(rules, surface) if check_words else []
    hits = []
    in_fence = False
    for number, raw in enumerate(text.splitlines(), start=1):
        for pattern, message in characters:
            if pattern.search(raw):
                hits.append((number, raw, message))
        if markdown and FENCE.match(raw):
            in_fence = not in_fence
            continue
        if markdown and in_fence:
            continue
        testable = INLINE_CODE.sub(" ", raw) if markdown else raw
        normalized = normalize(testable)
        for pattern, message in words:
            if pattern.search(normalized):
                hits.append((number, raw, message))
    return hits


def scan_file(text, rules, path):
    """Return (line number, raw line, message) for each violation in a file."""
    return _scan(
        text,
        rules,
        path,
        surface="file",
        check_words=path.endswith(PROSE_SUFFIXES),
        markdown=path.endswith(MARKDOWN_SUFFIXES),
    )


def scan_message(text, rules):
    """Return the violations in a commit message, a PR body, or a comment."""
    return _scan(text, rules, "", surface="message", check_words=True, markdown=True)
