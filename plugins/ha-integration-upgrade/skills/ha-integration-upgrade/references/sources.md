# Sources for one release step

How to query each source, what it is good for, and where it misleads. The
locations below held for the 2026.11 cycle. Home Assistant moves things
between releases, so when a path or URL stops answering, find its new home
(an archived repository's README, an HTTP redirect, `git ls-tree` at the new
tag) before concluding the source is gone.

`$FROM` and `$TO` stand for the two release tags (`2026.10.0`, `2026.11.0`),
and `$CORE` for the cache repository `scripts/fetch-core.sh` prints. Write a
tag in front of a path as `"${TO}:<path>"`. zsh reads `$TO:h...` as the `:h`
modifier of `$TO`, so `$TO:homeassistant/...` silently names the wrong
object.

## Developer blog

One post per change, written for integration authors. The site is
`contributors.home-assistant.io`. The older `developers.home-assistant.io`
redirects there, and its repository `home-assistant/developers.home-assistant`
is archived. The posts live as dated Markdown files under `src/content/blog/`
of `home-assistant/contributors.home-assistant.io`, with `title`,
`description`, `date` and `areas` in the frontmatter.

- `scripts/blog-posts.sh --since <date> --until <date>` reads the `core` and
  `marketplace` area feeds (`/blog/<area>/rss.xml`) and prints one line per
  post, with the post URL to cite. Add `--area frontend` (and repeat the
  defaults) for an integration that ships a card. For a chain of steps, one
  query over the union of the step windows is enough, because every post is
  verified at a tag anyway.
- Read a post in full from its Markdown source, which is shorter than the
  page: `gh api repos/home-assistant/contributors.home-assistant.io/contents/src/content/blog/<date>-<slug>.md -H 'Accept: application/vnd.github.raw'`.
  Build the file name from the URL path, `/blog/2026/10/13/device-info-class/`
  becoming `2026-10-13-device-info-class.md`. The date in the feed can differ
  from the one in the path. The title
  often hides the helper. "Config entry functions now return None" is
  where `async_unload_platforms_or_raise` is introduced, and no title names it.
- A post that introduces a library or a feature set names many new things at
  once. List each new public name it shows and check the integration for the
  pattern each one replaces, not only for the change the post leads with.
- The date does not decide the release. A change merged to `dev` after the
  first beta of `$FROM` ships in `$TO`. A post dated on that beta's cut day
  can belong to either release, and a post dated after the first beta of
  `$TO` usually describes the release after it. Check every post against the
  tag: `git -C "$CORE" grep -n <symbol> "$TO"` must hit, and the same grep at
  `$FROM` must not (or must show the old shape).

## Core source between the tags

The authority. Everything else only points at candidates.

- `git -C "$CORE" log --format='%h %s' "$FROM..$TO" -- <paths>` gives a cheap
  index: core squash-merges each PR into one commit whose subject ends in
  `(#NNNNN)`. Read a PR with
  `gh pr view NNNNN --repo home-assistant/core --json title,body,labels`.
- `git -C "$CORE" diff "$FROM" "$TO" -- <path>` for the detail, one file at a time.
  The diff of `homeassistant/helpers/` alone runs to thousands of lines, so
  start from the log.
- `git -C "$CORE" show "${TO}:<path>"` to read a file at the tag, and cite it
  as `core $TO <path> <symbol>`.
- The cache is a blobless clone of tens of megabytes. Unpacking the
  `homeassistant` wheel of each release to diff them costs gigabytes and gives
  no PR numbers to cite.

Paths worth indexing:

| Path                                                                                                                     | Why                                                                                                                                                                |
| ------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `homeassistant/helpers/`, `config_entries.py`, `core.py`, `data_entry_flow.py`, `exceptions.py`, `const.py`, `loader.py` | The framework every integration calls.                                                                                                                             |
| `homeassistant/components/<platform>/` for each platform the integration implements                                      | Entity base classes, their properties and deprecations.                                                                                                            |
| `homeassistant/components/<component>/` for each core component it imports or lists in `dependencies`                    | `repairs`, `diagnostics`, `mqtt` and the like.                                                                                                                     |
| The hassfest manifest schema (`git -C "$CORE" ls-tree -r --name-only "$TO" \| grep 'hassfest/manifest.py'`)              | New and required `manifest.json` keys.                                                                                                                             |
| The scaffold templates (`script/scaffold/templates/`)                                                                    | The shape core considers current for a new integration.                                                                                                            |
| The type-hint checker of core's pylint plugin (`git -C "$CORE" ls-tree -r --name-only "$TO" \| grep -i 'type_hints'`)    | Expected signatures. A return type that changes, such as setup returning `None`, shows up here. The package moved between 2026.10 and 2026.11, so find it by name. |
| Core's test package (`packages/pytest-homeassistant/` in 2026.11)                                                        | Fixtures and helpers the integration's tests use.                                                                                                                  |

## Deprecations

- New removal dates: grep each tag over the surface paths and diff the two
  outputs. Each hit names the removal release.

  ```sh
  paths=(homeassistant/helpers homeassistant/config_entries.py homeassistant/components/climate)
  removals() { git -C "$CORE" grep -B3 breaks_in_ha_version "$1" -- "${paths[@]}" | sed "s/^$1://"; }
  diff <(removals "$FROM") <(removals "$TO")
  ```

  Over the whole tree, `git diff -G` or `git log -G` makes the blobless
  cache fetch most of core's blobs and can run for minutes. The helpers that
  carry removal dates are in `homeassistant/helpers/deprecation.py` and
  `homeassistant/helpers/frame.py` (`report_usage`).

- The integration's own test run on the new pin is the precise list: core
  logs a warning for each deprecated call it reaches. pytest prints captured
  logs only for failing tests, so run the same command on both pins with a
  log file, and diff the two after removing what differs between any two
  runs (line numbers, task numbers, addresses, durations, and the clone
  path):

  ```sh
  python -m pytest -q -p no:cacheprovider --log-file="$LOG" --log-file-level=WARNING
  norm() {
    grep -E '^(WARNING|ERROR|CRITICAL) ' "$1" | sed -E \
      -e "s#$2#CLONE#g" -e 's/:[0-9]+ /:N /' -e 's/Task-[0-9]+/Task-N/g' \
      -e 's/0x[0-9a-f]+/0xN/g' -e 's/[0-9.]+ seconds/N seconds/g' | sort -u
  }
  diff <(norm "$FROM_LOG" "$FROM_CLONE") <(norm "$TO_LOG" "$TO_CLONE")
  ```

  Grep the difference for `deprecated` and "will stop working", and read the
  pytest warnings summary too.
- A deprecation from an earlier release that the integration never moved off
  shows up the same way. Report it with the release that introduced it.

## Labels on core PRs

`gh api -X GET search/issues -f q='repo:home-assistant/core is:pr is:merged label:"breaking-change" merged:<from-b0-date>..<to-b0-date>'`

- `breaking-change` and `deprecation` are narrow enough to read in full
  (dozens of PRs per cycle).
- `core` and `new-feature` are too broad (hundreds per cycle): `core` lands
  on any PR that touches a core-owned integration.
- Milestones only collect the PRs cherry-picked into a beta or a patch
  release, so they do not list a cycle's work.

## Reference integrations

When core adds a helper, it usually migrates its own integrations in a run of
PRs, and a sweep turns one feature of a post into the idiom. The 2026.10
probatio post lists `Secret` as one marker among several, and in 2026.11
"Mark CONF_PASSWORD as secret in config schemas" moved every password field
in core to it. A reader who takes the post for the typing break it explains
misses that. Diffing a core integration of the same shape between the tags
shows the idiom in use:

```sh
git -C "$CORE" log --format='%h %s' "$FROM..$TO" -- homeassistant/components/<reference>/
git -C "$CORE" diff "$FROM" "$TO" -- homeassistant/components/<reference>/
```

Skip the commits that only bump the integration's own library or fix its
devices. What is left is the sweep PRs, and their titles name the idiom.

To catch a sweep the references missed, count how many core integrations use
a name at each tag. A jump from tens to hundreds marks an idiom core moved to:

```sh
git -C "$CORE" grep -l 'Secret(' "$FROM" -- homeassistant/components | wc -l
git -C "$CORE" grep -l 'Secret(' "$TO" -- homeassistant/components | wc -l
```

Use the references the target repository names. When it names none, pick two
or three with the same `integration_type`, `iot_class`, platforms and
connection style (local push hub, cloud poll, and so on), and say in the
report which ones were used.

## Packages and pins

- `homeassistant` and the test package move together. In 2026.11 the test
  package is core's own `pytest-homeassistant`, released for each core release
  and pinning it exactly. It needs `-p no:respx` in pytest `addopts` (its
  README has the full configuration). `pytest-homeassistant-custom-component`
  stopped at 2026.10, and the two must not be installed together.
- For any test package, find the release whose metadata pins the target core
  (`Requires-Dist: homeassistant==<version>`). When none exists, read the
  package's README or changelog for a successor before concluding the release
  is missing.
- Diff the `Requires-Dist` of the old and new test package. A pytest plugin
  the old package pulled in (`pytest-timeout`, `pytest-cov`,
  `pytest-unordered`) may be gone from the new one, and a test that uses its
  marker then fails or warns with `PytestUnknownMarkWarning`.
- For an intermediate step of a chain, pin the test package release that
  pins that step's `.0` tag, not its latest patch, so the gate runs the code
  the tag diff describes.
- PyPI's JSON API can lag the simple index. Check
  `https://pypi.org/simple/<package>/` (or `uv pip install --dry-run`) before
  deciding a release is not out.
- A new core release can raise its minimum Python. Read `requires-python` of
  the target release.
- Core's non-English translations are built into the wheel and are not in
  git. Read them from the venv, such as
  `homeassistant/components/homeassistant/translations/pl.json` under its
  `site-packages`.

## Frontend

An integration that ships a card or a panel depends on the frontend as much
as on core, and core pins one frontend build per release in
`homeassistant/components/frontend/manifest.json`
(`home-assistant-frontend==20261028.4` at 2026.11.0).
`scripts/frontend-releases.sh --from "$FROM" --to "$TO"` reads both pins from
the cache and prints the notes of every frontend release in between, one
line per note, prefixed with the release tag.

- The notes run to hundreds of lines per cycle, and frontend PRs seldom carry
  a label worth searching. Grep them for what the card touches: `custom card`,
  `custom element`, `extra module`, `polyfill`, the frontend helpers the card
  imports, and the names of the internal elements it reuses.
- In 2026.11, "Load custom modules after the scoped registry polyfill" let a
  card define its elements when its module loads, and a workaround that
  waited for `home-assistant` became dead code. No core source shows it.
- Read a PR it names with `gh pr view <number> --repo home-assistant/frontend`.

## Changes with no post

Some changes a user sees have no post and carry only a `new-feature` or
`bugfix` label. In 2026.10, new entity ids on a child device without an area
of its own started with the parent device's name, and the only trace was the
integration's snapshots. When a snapshot or a literal id moves, read the
core code that builds the field (for entity ids, the name parts in
`homeassistant/helpers/entity_registry.py` and `next_name_part` in
`device_registry.py`) and its log between the tags.

## Low value for this purpose

The user-facing release notes on `home-assistant.io` cover integrations and
features, not helpers. Their "Backward-incompatible changes" section is worth
one skim for anything that names a base platform the integration implements.
