# house-style

Two hooks that hold written prose to one set of conventions, plus a skill for
the sentence shapes a pattern cannot judge.

- On `PostToolUse` for Write and Edit, `hooks/check_file.py` reports the
  violations the edit introduced and exits 2, so the agent sees them and can
  rewrite. Only the lines the edit added are reported; the rest of the file is
  left alone.
- On `PreToolUse` for Bash, `hooks/check_command.py` denies a `git` or `gh`
  command whose message text breaks a rule. It reads `-m`, `--message`, `-b`,
  `--body`, `-t`, `--title`, `-n`, `--notes`, and any heredoc body the command
  carries.

Word rules apply to `.md`, `.mdx` and `.txt` files and to command messages.
Character rules apply to every file. In markdown, fenced blocks and inline
code spans are exempt from word rules.

The plugin needs `python3` on `PATH` and uses the standard library only.

## Overriding the rules

The shipped rules live in `rules/default.json`. An optional user file adds to
them and drops the ones you do not want:

```
$CLAUDE_CONFIG_DIR/house-style.json
```

When `CLAUDE_CONFIG_DIR` is unset, the path falls back to
`~/.claude/house-style.json`. A leading `~` is expanded either way. The file is
optional, and a broken one is reported on stderr and then ignored rather than
failing the hook.

```json
{
  "skip": ["*/fixtures/*"],
  "words": [{ "match": "\\bsynergy\\b", "message": "Name the benefit." }],
  "characters": [
    {
      "match": "\\t",
      "message": "Tab. Use spaces.",
      "files": ["*.md", "*.txt"]
    }
  ],
  "remove": ["\\bprior to\\b"]
}
```

### Keys

- `skip` - globs of file paths the file hook ignores entirely.
- `words` - rules matched against prose, case-insensitively, after hyphen runs
  and zero-width characters are folded away.
- `characters` - rules matched against the line exactly as written, in every
  file, including fenced blocks.
- `remove` - shipped rules to drop.

### Rule fields

- `match` - the regular expression. Required. A rule without one, or with one
  the regex engine rejects, is skipped and reported.
- `message` - what to print when it fires.
- `surface` - `both` (the default), `file`, or `message`. Limits a word rule to
  written files or to commit messages and bodies.
- `raw` - when true, the pattern sees the line as written instead of the folded
  form. Use it for a pattern about punctuation.
- `files` - which paths a character rule applies to. A comma-joined string
  (`"*.ps1,*.psm1"`) or a list (`["*.ps1", "*.psm1"]`). Defaults to `*`.

### Removing a shipped rule

`remove` matches a shipped rule by its `match` string, character for character.
To stop the plugin from flagging `prior to`, copy that rule's pattern out of the
list below and put it in `remove`:

```json
{ "remove": ["\\bprior to\\b"] }
```

Note the JSON escaping: `\b` in a pattern is written `\\b` in the file.

## The shipped rules

Characters:

- The em dash character itself, U+2014. Every file.
- `[^\x00-\x7F]` - a non-ASCII byte in a PowerShell file. `*.ps1,*.psm1`.

Words:

- `\bload-bearing\b` - buzzword. Name the dependency.
- `\bsmoking gun\b` - buzzword. State the evidence.
- `\bstated fairly\b` - buzzword. Delete it.
- `\bleverag(e[sd]?|ing)\b` - write "use".
- `\butiliz(e|es|ed|ing)\b` - write "use".
- `\bin order to\b` - write "to".
- `\bprior to\b` - write "before".
- `\bin the event that\b` - write "if".
- `\bdelv(e[sd]?|ing)\b` - write "read" or "examine".
- `\bseamless(ly)?\b` - carries no fact. Delete it.
- `\b(colour|initialise|licence|cancelled)\b` - British spelling. Use American
  English.
- `(?:^|(?<=[\s(\[]))(?<!\]\()[^\s#/()\[\]]*\w--\w|\s--\s(?!\s*-)` - a double
  dash used as prose punctuation. Skips command flags, a flag separator, and a
  markdown link target.
- `\b(a|the) (maintainer|reviewer|maintainers|reviewers)\b|\bthe team\b` - the
  reader is that person. Write "you". Messages only.

## Tests

```
cd plugins/house-style && python3 -m unittest discover -s tests -t .
```
