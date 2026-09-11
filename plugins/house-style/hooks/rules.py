"""Load, merge, and apply the house-style rules."""

import fnmatch
import json
import os
import re
import sys

PROSE_SUFFIXES = (".md", ".txt", ".mdx")
MARKDOWN_SUFFIXES = (".md", ".mdx")
ZERO_WIDTH = dict.fromkeys([0x200B, 0x200C, 0x200D, 0xFEFF])
HYPHEN_RUN = re.compile(r"-{2,}")
INLINE_CODE = re.compile(r"`[^`]*`")
FENCE = re.compile(r"^\s*(?:```|~~~)")
REWRITE_NOTE = "Rewrite the sentence. Do not split, hyphenate, or otherwise disguise the word."
RULE_KEYS = ("skip", "characters", "words")
# Both hooks feed their report straight into the model's context, so the
# number of violations either one reports is capped.
MAX_LINES = 20


def plugin_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def user_rules_path():
    config = os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude")
    return os.path.join(config, "house-style.json")


def warn(path, problem):
    """Report a problem with the user rules file on stderr."""
    print("house-style: {}: {}".format(path, problem), file=sys.stderr)


def load_rules(user_path=None):
    """Return the shipped rules, merged with the user file when one exists.

    A broken user file is reported and then ignored. Both hooks run on every
    write and every command, so raising here would block all of them until
    someone repaired a file the hook cannot ask about.
    """
    shipped = os.path.join(plugin_root(), "rules", "default.json")
    with open(shipped, encoding="utf-8") as handle:
        loaded = json.load(handle)
    for key in RULE_KEYS:
        loaded.setdefault(key, [])
    path = user_rules_path() if user_path is None else user_path
    if not path or not os.path.exists(path):
        return loaded
    try:
        with open(path, encoding="utf-8") as handle:
            extra = json.load(handle)
    except (OSError, ValueError) as error:
        warn(path, "unreadable, using the shipped rules ({})".format(error))
        return loaded
    if not isinstance(extra, dict):
        warn(path, "expected a JSON object, using the shipped rules")
        return loaded
    return merge_rules(loaded, extra, path)


def _user_list(extra, key, path):
    """Return one list-valued key of the user file, or an empty list."""
    value = extra.get(key, [])
    if isinstance(value, list):
        return value
    warn(path, '"{}" must be a list, ignoring it'.format(key))
    return []


def _user_rules(extra, key, path):
    """Return the usable rules under one key of the user file.

    A rule with no pattern, or with one the regex engine rejects, is dropped
    on its own so the rest of the file still applies.
    """
    kept = []
    for rule in _user_list(extra, key, path):
        if not isinstance(rule, dict) or not isinstance(rule.get("match"), str):
            warn(path, 'skipping a "{}" entry with no "match" string'.format(key))
            continue
        try:
            re.compile(rule["match"])
        except re.error as error:
            warn(path, "skipping {!r} ({})".format(rule["match"], error))
            continue
        usable = dict(rule)
        usable.setdefault("message", "Breaks a house-style rule.")
        kept.append(usable)
    return kept


def merge_rules(base, extra, path="the user rules file"):
    merged = {"skip": list(base["skip"])}
    merged["skip"].extend(
        glob for glob in _user_list(extra, "skip", path) if isinstance(glob, str)
    )
    for key in ("characters", "words"):
        merged[key] = list(base[key]) + _user_rules(extra, key, path)
    drop = {
        match for match in _user_list(extra, "remove", path) if isinstance(match, str)
    }
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
            selected.append(
                (re.compile(rule["match"], re.IGNORECASE), rule["message"], rule.get("raw", False))
            )
    return selected


def _file_globs(rule):
    """Return the globs a character rule applies to, from either spelling.

    `files` takes a comma-joined string or a list of globs. Every other
    collection in the rules file is a JSON array, so both turn up.
    """
    globs = rule.get("files", "*")
    if isinstance(globs, str):
        globs = globs.split(",")
    if not isinstance(globs, (list, tuple)):
        return ["*"]
    return [str(glob).strip() for glob in globs]


def _character_rules(rules, path):
    selected = []
    for rule in rules["characters"]:
        globs = _file_globs(rule)
        if any(fnmatch.fnmatch(path, glob) for glob in globs):
            selected.append((re.compile(rule["match"]), rule["message"]))
    return selected


def _scan(text, rules, path, surface, check_words, markdown):
    characters = _character_rules(rules, path)
    words = _word_rules(rules, surface) if check_words else []
    hits = []
    in_fence = False
    for number, raw_line in enumerate(text.splitlines(), start=1):
        for pattern, message in characters:
            if pattern.search(raw_line):
                hits.append((number, raw_line, message))
        if markdown and FENCE.match(raw_line):
            in_fence = not in_fence
            continue
        if markdown and in_fence:
            continue
        testable = INLINE_CODE.sub(" ", raw_line) if markdown else raw_line
        normalized = normalize(testable)
        for pattern, message, is_raw in words:
            haystack = testable if is_raw else normalized
            if pattern.search(haystack):
                hits.append((number, raw_line, message))
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
