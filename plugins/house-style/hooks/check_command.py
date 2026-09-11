#!/usr/bin/env python3
"""PreToolUse hook: deny a command whose message text breaks the house style."""

import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rules as engine  # noqa: E402

VALUE_FLAGS = {
    "git": {"-m", "--message"},
    "gh": {"-b", "-t", "-n", "--body", "--title", "--notes"},
}
# Flags whose value names a file rather than a message, so the value is
# stepped over instead of scanned.
FILE_FLAGS = {"-F", "--file", "--body-file"}
BREAKS = {"&&", "||", ";", "|", "&"}
BREAK_CHARS = "".join(sorted({char for token in BREAKS for char in token}))
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?")
# Stands in for a heredoc body that was cut out, so the command that owned the
# body can still be identified once the line is tokenized.
BODY_MARK = "__HS_BODY_{}__"
BODY_PATTERN = re.compile(BODY_MARK.format(r"(\d+)"))


def strip_heredocs(command):
    """Return the command with each heredoc body cut out, and the extracted bodies.

    A heredoc body is not shell syntax. It can hold an unbalanced quote (an
    apostrophe in prose) that would otherwise make shlex.split raise on the
    whole command. Removing the bodies before tokenizing keeps the outer
    command parseable, and the bodies are scanned separately as raw text. Each
    body leaves a BODY_MARK placeholder behind, which keeps its position in the
    command available to the tokenized pass.
    """
    bodies = []
    out = []
    pos = 0
    for match in HEREDOC.finditer(command):
        if match.start() < pos:
            continue
        out.append(command[pos:match.start()])
        after = command[match.end():]
        closing = re.search(
            r"^\s*{}\s*$".format(re.escape(match.group(1))), after, re.MULTILINE
        )
        if closing:
            body = after[:closing.start()]
            # The newline after the terminator line stays in the command, so
            # normalize_breaks can turn it into the command break it is. The
            # next command then starts with no tool active.
            end = match.end() + closing.end()
        else:
            body = after
            end = len(command)
        out.append(" {} ".format(BODY_MARK.format(len(bodies))))
        # The body starts at the newline that ends the opener line, so drop
        # that newline to keep the reported line numbers those of the text.
        bodies.append(body[1:] if body.startswith("\n") else body)
        pos = end
    out.append(command[pos:])
    return "".join(out), bodies


def normalize_breaks(text):
    """Turn an unquoted newline into a semicolon so it acts as a command break.

    shlex treats a literal newline as ordinary whitespace, so a compound
    command spread across lines never resets the active git/gh state. A
    newline inside a quoted argument is left alone, since it is part of the
    argument's text, not a separator between commands.
    """
    out = []
    quote = None
    escaped = False
    for char in text:
        if escaped:
            out.append(char)
            escaped = False
            continue
        if quote:
            if char == "\\" and quote == '"':
                out.append(char)
                escaped = True
                continue
            if char == quote:
                quote = None
            out.append(char)
            continue
        if char == "\\":
            out.append(char)
            escaped = True
            continue
        if char in ("'", '"'):
            quote = char
            out.append(char)
            continue
        out.append(";" if char == "\n" else char)
    return "".join(out)


def tokenize(command):
    """Split a command into words, treating a run of BREAK_CHARS as its own token.

    Plain shlex.split leaves an operator glued to an adjacent word (`status;`
    stays one token), so a break right after a subcommand name is missed.
    punctuation_chars makes shlex peel operators off on either side while
    still honoring quotes.
    """
    lex = shlex.shlex(command, posix=True, punctuation_chars=BREAK_CHARS)
    lex.whitespace_split = True
    return list(lex)


def split_short_option(token, flags):
    """Return (flag, attached value) when a short-option token carries a known flag.

    Short options cluster, so `git commit -am "..."` passes -m inside the
    token -am, and a short option can hold its value with no separator, so
    `git commit -m'...'` arrives as the single token -m followed by the text.
    The attached value is None when the flag ends the token, which means its
    value is the next token.
    """
    if not token.startswith("-") or token.startswith("--") or len(token) < 3:
        return None
    for position, letter in enumerate(token[1:], start=1):
        flag = "-" + letter
        if flag in flags:
            return flag, token[position + 1:] or None
    return None


def owned_bodies(tokens, bodies):
    """Return the heredoc bodies that belong to a git or gh command.

    A heredoc body counts as a message wherever it appears under git or gh,
    rather than only as the value of a file flag. The usual way to pass a
    multi-line message is `--body "$(cat <<'EOF' ... EOF)"`, where the flag's
    own value tokenizes to the command substitution rather than to the text.
    Matching on the placeholder inside the token covers that form and still
    leaves a heredoc that another command owns, such as a `cat` writing a
    source file next to a `git add`, out of the messages.
    """
    found = []
    active = None
    for token in tokens:
        if token in BREAKS:
            active = None
            continue
        basename = os.path.basename(token)
        if basename in ("git", "gh"):
            active = basename
            continue
        if not active:
            continue
        for match in BODY_PATTERN.finditer(token):
            position = int(match.group(1))
            if position < len(bodies):
                found.append(bodies[position])
    return found


def messages(command):
    """Return every message string that the command hands to git or gh.

    The value flags are keyed by tool, not merged into one flat set: -m
    means something to git and nothing to gh, -b/-t/-n mean something to gh
    and nothing to git, so the active tool decides which set applies.
    """
    stripped, bodies = strip_heredocs(command)
    try:
        tokens = tokenize(normalize_breaks(stripped))
    except ValueError:
        return []
    found = []
    active = None
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in BREAKS:
            active = None
            index += 1
            continue
        basename = os.path.basename(token)
        if basename in ("git", "gh"):
            active = basename
            index += 1
            continue
        value_flags = VALUE_FLAGS.get(active, set())
        flag, attached = token, None
        if active:
            split = split_short_option(token, value_flags | FILE_FLAGS)
            if split is not None:
                flag, attached = split
        if flag in value_flags:
            if attached is not None:
                found.append(attached)
                index += 1
                continue
            if index + 1 < len(tokens):
                found.append(tokens[index + 1])
                index += 2
                continue
        if active and flag in FILE_FLAGS:
            index += 1 if attached is not None else 2
            continue
        name, sign, inline = token.partition("=")
        if active and sign and name in value_flags:
            found.append(inline)
        index += 1
    found.extend(owned_bodies(tokens, bodies))
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
    if not isinstance(payload, dict):
        print(json.dumps(decision()))
        return 0
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        print(json.dumps(decision()))
        return 0
    command = tool_input.get("command")
    if not isinstance(command, str):
        print(json.dumps(decision()))
        return 0
    loaded = engine.load_rules()
    lines = []
    for text in messages(command):
        for number, raw, message in engine.scan_message(text, loaded):
            lines.append("line {}: {} -> {}".format(number, raw.strip()[:80], message))
    if lines:
        shown = lines[:engine.MAX_LINES]
        if len(lines) > engine.MAX_LINES:
            shown.append("... and {} more.".format(len(lines) - engine.MAX_LINES))
        reason = "House style: " + " | ".join(shown) + " " + engine.REWRITE_NOTE
        print(json.dumps(decision(reason)))
    else:
        print(json.dumps(decision()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
