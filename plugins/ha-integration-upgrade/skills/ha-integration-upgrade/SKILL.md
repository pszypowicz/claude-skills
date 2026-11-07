---
name: ha-integration-upgrade
description: Use when moving a Home Assistant custom integration to a newer core release (for example 2026.10 to 2026.11), bumping its homeassistant or pytest-homeassistant pin, raising the hacs.json minimum, or asking which breaking changes, deprecations, or new core helpers of a Home Assistant release affect a custom component.
---

# Upgrading a Home Assistant custom integration

## Overview

Every monthly core release can break a custom integration, deprecate what it
calls, and add helpers that make some of its own code redundant. This skill
turns one release step into a report with evidence for each finding, and then,
once the user approves, into themed PRs with the repo's own gate green.

Discovery runs against live sources every time, and the skill carries no list
of helpers. The core source at the release tag is the authority. Blog posts,
PR titles and labels only nominate candidates. The integration's own gate,
run on the new pin, is the fastest detector of what breaks.

## Inputs

- **The step.** The release the repo pins now and the one it moves to. Read
  the current pin from the repo (the test requirements, the `homeassistant`
  key of `hacs.json`, the CI matrix) and say so when it differs from what the
  user named. When the pin is more than one minor behind the target, process
  one minor at a time: 2026.9 to 2026.10, then 2026.10 to 2026.11. Each step
  gets its own report section, and a finding carries the release that
  introduced it.
- **The repo's policy.** Read `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md` and
  the gate configuration (`.pre-commit-config.yaml`, CI workflows,
  `pyproject.toml`). Note what they say about migration and compatibility
  code, how far the minimum Home Assistant version may move, the type
  checkers, test conventions such as snapshots, the branch and PR rules,
  versioning and release notes, and any reference integrations they name. The
  policy decides between fixes. This skill never overrides it.

## One step

`$FROM` and `$TO` are the two release tags. `references/sources.md` has the
query for every source below, and where each one misleads.

1. **Map the surface.** List the platforms the integration implements, every
   `homeassistant.*` name it imports or calls, the core components in its
   `dependencies` or imports, its `manifest.json` keys, and the test package
   and fixtures its tests use. Note whether it ships frontend code: a card or
   panel built from a `frontend/` folder, `add_extra_js_url`, or `frontend` in
   `dependencies` or `after_dependencies`. List its local workarounds of core
   or frontend behavior too: comments that describe how upstream behaves,
   references to upstream issues or PRs, version checks, polyfills and
   monkeypatches. Every candidate is checked against this list. Every
   workaround is checked at `$TO`, because a release that fixes the upstream
   behavior turns it into dead code.
2. **Fetch core** once for the whole chain:
   `scripts/fetch-core.sh --from <pin> --to <target>`. It prints the cache
   repository, the tag dates, and one line per step with its commit count and
   blog window.
3. **Collect candidates** from the cheap indexes, not from whole diffs:
   - `scripts/blog-posts.sh --since <a> --until <b>` with the printed window.
     Read in full every post whose title or description comes near the
     surface.
   - The commit subjects between the tags for the framework paths, the
     integration's platforms, and the core components it uses.
   - New `breaks_in_ha_version` lines, and the PRs labeled `breaking-change`
     or `deprecation`.
   - The reference integrations' commits between the tags, plus a usage count
     for any new name that looks like an idiom core swept its own code onto.
   - The diffs of the hassfest manifest schema, the scaffold templates, and
     the type-hint checker of core's pylint plugin.
   - When the integration ships frontend code, the notes of every frontend
     release the step brings in (`scripts/frontend-releases.sh --from "$FROM"
     --to "$TO"`), grepped for the frontend APIs and elements the code uses,
     and the blog's `frontend` area. Frontend PRs rarely carry a label a
     search would find.
   - Marketplace-area posts that change how users install or update an
     integration. Check the README's install section against them (the
     button, the add-from-link path, prerequisites, whether a restart is
     needed). A stale install section is a finding a user sees.
4. **Run the gate on both pins.** Leave the repo's working tree alone during
   the report phase. Work in a clone (`git clone <checkout> <tmp-dir>`), not a
   worktree, which writes into the checkout's `.git`.
   - Run the type checkers and the test suite on `$FROM` first, in the repo's
     venv or one built for it. That baseline tells a failure of this step
     apart from one the repo already had.
   - Build a venv at `$TO` with its matching test package, the release that
     pins the step's tag exactly. When the test package changed (see
     sources.md), port the clone to it first, or the suite fails at plugin
     load and shows nothing else. Diff the `Requires-Dist` of the old and new
     test package, because a pytest plugin the old one pulled in may now need
     a pin of its own.
   - Run the same pytest command on both pins, writing warnings to a file,
     because pytest prints captured logs only for failing tests. Diff the two
     files after normalizing them. sources.md has the command and the
     normalizer.
   - One break can hide the rest. A single `AttributeError` can fail most of
     the suite, so apply the smallest fix in the clone and run again, until
     every remaining failure has a cause.
   - A failure or a type error nominates group 1. A new warning or logged
     deprecation nominates group 2. A snapshot or literal id that moved is a
     group 1 finding even with no post behind it. Trace the moved field to the
     core code that builds it, such as the name parts in `entity_registry.py`.
   - The gate cannot see translations. When core moves a string to a shared
     domain (abort reasons, entity names), check that core ships it in every
     language the repo translates, or the repo's own translation stops showing.
     Core's non-English translations ship in the wheel and not in git, so read
     them from the `$TO` venv.
   - Some compatibility paths log nothing, such as the re-add of an entity
     class that has not opted in to in-place entity id changes. Read the
     deprecation posts against the surface even when the gate is quiet.
   - When the repo has no type checker, run `mypy` over the integration once on
     each pin anyway and diff the two outputs. Removed names and changed
     signatures show up even in untyped code.
5. **Verify each candidate.** It holds at `$TO` and not at `$FROM`
   (`git -C "$CORE" grep -n <symbol> "$TO" -- <path>`), and the integration
   uses what it changes. Name our file and symbol. A candidate that does not
   touch the integration goes to "Checked and not affected".
6. **Write the report** (format below), then stop. Nothing is applied before
   the user approves.

## Groups

| Group             | Belongs here when                                                                                                                                                                                    | Also give                                                                                                                        |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| 1. Breaks us      | It fails, raises, or fails the type gate on `$TO`, or behavior a user sees changes (entity ids, names, translations). A type-gate failure counts here even when the runtime only logs a deprecation. | The failing test or error.                                                                                                       |
| 2. Deprecated     | It still works on `$TO` but declares, logs, or announces a removal.                                                                                                                                  | The removal release, or "not scheduled" for an announced removal with no release and no log, and the release that deprecated it. |
| 3. Simplifies     | A new helper or idiom lets the integration delete or shorten its own code, or replaces a hand-rolled or older pattern with the one core moved to.                                                    | What gets deleted or replaced.                                                                                                   |
| 4. New capability | A feature the integration could add. Report only.                                                                                                                                                    | Who would notice.                                                                                                                |

Every finding says whether adopting it raises the minimum Home Assistant
version, and to which release. When the integration ships through a store
that enforces a minimum (the Marketplace reads `homeassistant` from
`hacs.json`), a raised floor belongs in the release notes, so say so.

A raised floor needs a runtime reason: an API the code calls that is missing
before that release, or a behavior the code relies on. "The gate tests only
`$TO`" is a choice of test pin, and the code may still run on older cores.
When it does, say so and let the policy decide.

When a break has two fixes, one that keeps the old floor and one in the target
release's idiom, the policy picks. If it lets the floor move, use the target
idiom (`dataclasses.replace` over a version-agnostic copy) and name the new
floor. If it asks for compatibility, name what the floor-keeping fix costs.

A release can also set two of the repo's rules against each other, when one
says to follow core's behavior and another promises something that core's new
behavior breaks. Do not pick a side. Put the conflict to the user as a
decision, with the options and what each one changes for the people running
the integration.

## Report

One section per step: a heading `$FROM -> $TO`, one line on what was consulted
(posts read, commits indexed, the gate result on `$TO`), the four groups,
"Checked and not affected", "Proposed PRs", and "Open questions" for the
decisions only the user can make, each with its options. Do not settle such a
decision with a default. Each finding:

```markdown
### 1.1 ChildDeviceInfo no longer has copy()

- Ours: `custom_components/<domain>/entity.py` `<Domain>Entity.device_info`
- Evidence: <post URL>; core 2026.11.0 `homeassistant/helpers/device_registry.py` `ChildDeviceInfo`; core PR #NNNNN
- Change: build the info with `dataclasses.replace(...)`
- Floor: raises to 2026.11.0
```

Group 2 findings add `Removal: <release>`. Present the report in the
conversation. Do not commit it to the target repo.

## Applying, after approval

- **Themed PRs, in order.** First the pin, the test package and every break,
  together, because the old pin cannot run the new code and the new pin
  cannot run the old. This is the PR that raises the floor. Then the
  deprecations, then the simplifications one theme per PR, then capabilities
  only when asked.
- **The repo's gate goes green on every PR.** Never skip a hook. Follow the
  repo's branch, commit and PR rules, and bump the integration's version when
  the repo bumps it per change.
- **Each PR body states the floor change** and whether the release notes must
  mention it.
- **Multiple steps:** each step's PRs land green on that step's pin before the
  next step starts, unless the user asks to land the steps together.
- **No compatibility or migration code** the policy forbids, however natural
  it looks.
- **A deprecation guard.** When the test suite has no fixture that fails a
  test on a deprecated call core reports, propose one, so the next release's
  deprecations fail the gate and do not pass quietly.

## Cost

- The core cache is a blobless clone of tens of megabytes. Do not unpack the
  `homeassistant` wheel of each release to diff them.
- One venv per release in the chain: `$FROM` (the repo's own when it has
  one) and the `$TO` of each step. uv builds them in a minute or two from its
  cache. Delete them when the report is done.
- Scope expensive git queries to the surface. A diff or `log -G` over the
  whole tree makes the blobless cache fetch most of core's blobs. `git grep`
  at each tag over the surface paths, then a diff of the two outputs, is
  fast.
- Read the diffs one file at a time, starting from the commit log. The
  `helpers/` diff of one release runs to thousands of lines.
- Skip heavy tooling, such as a container image run under emulation, unless a
  finding depends on it. Say in the report what was not run.

## Common mistakes

| Mistake                                       | What to do instead                                                                                                                                                                                                                                      |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Taking a post's date as its release           | Verify at the tag. A post dated after the first beta of `$TO` often describes the release after it.                                                                                                                                                     |
| Reading only titles                           | Read the full post. Helpers hide inside posts about something else.                                                                                                                                                                                     |
| Taking a post for its headline change         | List every new name the post shows, and check the pattern each one replaces.                                                                                                                                                                            |
| Stopping at the blog                          | Diff the reference integrations. Core's sweeps of its own code show which feature became the idiom.                                                                                                                                                     |
| Reporting what does not touch the integration | Every group 1-3 finding names our file and symbol. The rest goes to "Checked and not affected".                                                                                                                                                         |
| Hardcoding a core path                        | Find it by name at the tag (`git ls-tree -r --name-only`). Core moves packages between releases.                                                                                                                                                        |
| Mixing two steps in one list                  | One section per minor step, each finding tagged with its release.                                                                                                                                                                                       |
| Writing `$TO:path` in zsh                     | Write `"${TO}:path"`. zsh reads `$TO:h` as a modifier.                                                                                                                                                                                                  |
| Keeping a pathspec list in one zsh string     | Use an array (`paths=(a b); git log -- "${paths[@]}"`). zsh does not split `$paths`, so the query silently matches nothing.                                                                                                                             |
| Reading the gate's output only for failures   | Log warnings to a file on both pins and diff them. Passing tests log deprecations too.                                                                                                                                                                  |
| Removing a guard because one run passes       | Find what the guard protects against. When that varies between environments (plugin load order, platform, Python version), a green run proves nothing. Cite the core code that makes the guard redundant, or mark the finding as needing a closer look. |
| Raising the floor because the gate tests only `$TO` | Name the runtime reason, or say that the code still runs on older cores. |
| Reading only core for an integration with a card | The card follows the frontend's releases. Read the notes `frontend-releases.sh` prints. |
| Applying before approval                      | Stop after the report and wait for the user's approval.                                                                                                                                                                                                 |
