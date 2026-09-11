#!/usr/bin/env python3
"""PreToolUse hook: deny a command whose message text breaks the house style."""

import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rules as engine  # noqa: E402

VALUE_FLAGS = {"-m", "--message", "--body", "--title", "--notes", "-b", "-t", "-n"}
FILE_FLAGS = {"-F", "--file", "--body-file"}
BREAKS = {"&&", "||", ";", "|", "&"}
BREAK_CHARS = "".join(sorted({char for token in BREAKS for char in token}))
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?")


def strip_heredocs(command):
    """Return the command with each heredoc body cut out, and the extracted bodies.

    A heredoc body is not shell syntax: it can hold an unbalanced quote (an
    apostrophe in prose) that would otherwise make shlex.split raise on the
    whole command. Removing the bodies before tokenizing keeps the outer
    command parseable; the bodies are scanned separately as raw text.
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
            bodies.append(after[:closing.start()])
            end = match.end() + closing.end()
            if end < len(command) and command[end] == "\n":
                end += 1
        else:
            bodies.append(after)
            end = len(command)
        out.append(" ")
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


def messages(command):
    """Return every message string that the command hands to git or gh."""
    stripped, bodies = strip_heredocs(command)
    try:
        tokens = tokenize(normalize_breaks(stripped))
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
                found.extend(bodies)
            index += 2
            continue
        name, sign, inline = token.partition("=")
        if active and sign:
            if name in VALUE_FLAGS:
                found.append(inline)
            elif name in FILE_FLAGS and inline == "-":
                found.extend(bodies)
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
