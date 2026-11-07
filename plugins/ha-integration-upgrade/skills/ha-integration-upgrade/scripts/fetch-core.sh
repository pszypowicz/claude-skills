#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: fetch-core.sh --from VERSION --to VERSION [--cache-dir DIR] [--remote URL]

Fetch two Home Assistant core releases, the first beta of each, and the
commits between them into a blobless cache repository. Print the repository
path, each tag with its commit date, and a date window for the developer blog.

VERSION is a minor release (2026.11) or an exact tag (2026.11.0, 2026.12.0b1).
A minor release resolves to its .0 tag. Pass a beta tag as --to to look at a
release before it ships.

Flags:
  --from VERSION   Release the integration pins now (required)
  --to VERSION     Release to move to, one minor after --from (required)
  --cache-dir DIR  Cache repository
                   (default: ${XDG_CACHE_HOME:-~/.cache}/ha-integration-upgrade/core)
  --remote URL     Core repository to fetch from
                   (default: https://github.com/home-assistant/core.git)
  -h, --help       Show this help

Example:
  fetch-core.sh --from 2026.10 --to 2026.11
  git -C "$(fetch-core.sh --from 2026.10 --to 2026.11 | sed -n 's/^repo: //p')" \
    log --oneline 2026.10.0..2026.11.0 -- homeassistant/helpers
EOF
}

die() { echo "error: $*" >&2; exit 1; }
missing_value() { echo "error: $1 requires a value" >&2; usage >&2; exit 1; }

FROM="" TO="" REMOTE="https://github.com/home-assistant/core.git"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/ha-integration-upgrade/core"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)      [[ -n "${2-}" ]] || missing_value "$1"; FROM="$2"; shift 2 ;;
    --to)        [[ -n "${2-}" ]] || missing_value "$1"; TO="$2"; shift 2 ;;
    --cache-dir) [[ -n "${2-}" ]] || missing_value "$1"; CACHE_DIR="$2"; shift 2 ;;
    --remote)    [[ -n "${2-}" ]] || missing_value "$1"; REMOTE="$2"; shift 2 ;;
    -h|--help)   usage; exit 0 ;;
    *)           echo "error: unknown flag: $1" >&2; usage >&2; exit 1 ;;
  esac
done

[[ -n "$FROM" ]] || { echo "error: --from is required" >&2; usage >&2; exit 1; }
[[ -n "$TO" ]] || { echo "error: --to is required" >&2; usage >&2; exit 1; }

# 2026.11 -> 2026.11.0. A full tag passes through unchanged.
release_tag() {
  if [[ "$1" =~ ^[0-9]{4}\.[0-9]{1,2}$ ]]; then
    echo "$1.0"
  elif [[ "$1" =~ ^[0-9]{4}\.[0-9]{1,2}\.[0-9]+((b|rc)[0-9]+)?$ ]]; then
    echo "$1"
  else
    die "not a Home Assistant version: $1"
  fi
}

# The first beta of the minor a tag belongs to: 2026.11.0 -> 2026.11.0b0.
first_beta() {
  [[ "$1" =~ ^([0-9]{4}\.[0-9]{1,2}) ]] || die "not a Home Assistant version: $1"
  echo "${BASH_REMATCH[1]}.0b0"
}

FROM_TAG="$(release_tag "$FROM")"
TO_TAG="$(release_tag "$TO")"
FROM_B0="$(first_beta "$FROM_TAG")"
TO_B0="$(first_beta "$TO_TAG")"

if [[ ! -d "$CACHE_DIR/.git" ]]; then
  mkdir -p "$CACHE_DIR"
  git init -q "$CACHE_DIR"
  git -C "$CACHE_DIR" remote add origin "$REMOTE"
fi
cd "$CACHE_DIR"

refspecs=()
for tag in "$FROM_B0" "$FROM_TAG" "$TO_B0" "$TO_TAG"; do
  refspecs+=("+refs/tags/$tag:refs/tags/$tag")
done

# Tips first, so the beta of --from dates the history to deepen to.
if ! git fetch -q --no-tags --filter=blob:none --depth=1 origin "${refspecs[@]}"; then
  die "could not fetch $FROM_B0, $FROM_TAG, $TO_B0 and $TO_TAG from $REMOTE (is $TO_TAG released?)"
fi

commit_date() { git log -1 --format=%cs "$1"; }
since="$(commit_date "$FROM_B0")"

# A release branch forks from dev at its first beta, so history from a few
# weeks before the --from beta reaches the merge base of the two releases.
deepen_since="$(python3 -c 'import datetime, sys; print(datetime.date.fromisoformat(sys.argv[1]) - datetime.timedelta(days=21))' "$since")"
git fetch -q --no-tags --filter=blob:none --shallow-since="$deepen_since" origin "${refspecs[@]}"

base="$(git merge-base "$FROM_TAG" "$TO_TAG" 2>/dev/null || true)"
[[ -n "$base" ]] || die "no merge base of $FROM_TAG and $TO_TAG within the fetched history; is --to one minor after --from?"

blog_since="$(python3 -c 'import datetime, sys; print(datetime.date.fromisoformat(sys.argv[1]) - datetime.timedelta(days=7))' "$since")"
blog_until="$(python3 -c 'import datetime, sys; print(datetime.date.fromisoformat(sys.argv[1]) + datetime.timedelta(days=14))' "$(commit_date "$TO_TAG")")"

echo "repo: $CACHE_DIR"
for tag in "$FROM_B0" "$FROM_TAG" "$TO_B0" "$TO_TAG"; do
  printf 'tag: %-14s %s %s\n' "$tag" "$(git rev-parse --short "$tag^{commit}")" "$(commit_date "$tag")"
done
echo "commits: $(git rev-list --count "$FROM_TAG..$TO_TAG") in $FROM_TAG..$TO_TAG"
echo "blog-window: $blog_since $blog_until"
