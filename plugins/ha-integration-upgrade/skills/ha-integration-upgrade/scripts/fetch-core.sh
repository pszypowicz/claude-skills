#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: fetch-core.sh --from VERSION --to VERSION [--cache-dir DIR] [--remote URL] [--since DATE]

Fetch the Home Assistant core releases from --from to --to, the first beta of
each, and the commits between them into a blobless cache repository. When
--to is more than one minor after --from, every minor in between is fetched
too, so the chain can be processed one step at a time. Print the repository
path, each tag with its commit date, and for each step its commit count and a
date window for the developer blog.

A run only ever deepens the cache, so a later run never cuts history an
earlier run fetched.

VERSION is a minor release (2026.11) or an exact tag (2026.11.0, 2026.12.0b1).
A minor release resolves to its .0 tag. Pass a beta tag as --to to look at a
release before it ships.

Flags:
  --from VERSION   Release the integration pins now (required)
  --to VERSION     Release to move to (required)
  --cache-dir DIR  Cache repository
                   (default: ${XDG_CACHE_HOME:-~/.cache}/ha-integration-upgrade/core)
  --remote URL     Core repository to fetch from
                   (default: https://github.com/home-assistant/core.git)
  --since DATE     Fetch history from this date on, YYYY-MM-DD (default: a week
                   before the first day of the month the --from beta is cut in)
  -h, --help       Show this help

Example:
  fetch-core.sh --from 2026.9 --to 2026.11
  git -C ~/.cache/ha-integration-upgrade/core log --oneline 2026.10.0..2026.11.0 -- homeassistant/helpers
EOF
}

die() { echo "error: $*" >&2; exit 1; }
missing_value() { echo "error: $1 requires a value" >&2; usage >&2; exit 1; }

FROM="" TO="" SINCE="" REMOTE="https://github.com/home-assistant/core.git"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/ha-integration-upgrade/core"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)      [[ -n "${2-}" ]] || missing_value "$1"; FROM="$2"; shift 2 ;;
    --to)        [[ -n "${2-}" ]] || missing_value "$1"; TO="$2"; shift 2 ;;
    --cache-dir) [[ -n "${2-}" ]] || missing_value "$1"; CACHE_DIR="$2"; shift 2 ;;
    --remote)    [[ -n "${2-}" ]] || missing_value "$1"; REMOTE="$2"; shift 2 ;;
    --since)     [[ -n "${2-}" ]] || missing_value "$1"; SINCE="$2"; shift 2 ;;
    -h|--help)   usage; exit 0 ;;
    *)           echo "error: unknown flag: $1" >&2; usage >&2; exit 1 ;;
  esac
done

[[ -n "$FROM" ]] || { echo "error: --from is required" >&2; usage >&2; exit 1; }
[[ -n "$TO" ]] || { echo "error: --to is required" >&2; usage >&2; exit 1; }
[[ -z "$SINCE" || "$SINCE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || die "not a YYYY-MM-DD date: $SINCE"

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

FROM_TAG="$(release_tag "$FROM")"
TO_TAG="$(release_tag "$TO")"

# The chain as "tag beta" pairs, one per minor from --from to --to, plus the
# history date the --from beta implies. Home Assistant cuts the first beta of
# YYYY.M in the month before M, so a week before that month's first day
# reaches the point where the --from release branch left dev.
if ! plan="$(python3 -I - "$FROM_TAG" "$TO_TAG" 2>&1 <<'PY'
import datetime
import re
import sys

def minor(tag):
    year, month = map(int, re.match(r"(\d{4})\.(\d{1,2})", tag).groups())
    return year, month

first, last = minor(sys.argv[1]), minor(sys.argv[2])
if last <= first:
    sys.exit(f"--to {sys.argv[2]} is not after --from {sys.argv[1]}")

chain = []
year, month = first
while (year, month) <= last:
    chain.append((year, month))
    year, month = (year + 1, 1) if month == 12 else (year, month + 1)

for i, (year, month) in enumerate(chain):
    tag = sys.argv[1] if i == 0 else sys.argv[2] if i == len(chain) - 1 else f"{year}.{month}.0"
    print(f"{tag} {year}.{month}.0b0")

year, month = first
cut_year, cut_month = (year - 1, 12) if month == 1 else (year, month - 1)
print(datetime.date(cut_year, cut_month, 1) - datetime.timedelta(days=7))
PY
)"; then
  die "$plan"
fi

TAGS=() BETAS=()
while read -r tag beta; do
  [[ -n "$beta" ]] || { [[ -n "$SINCE" ]] || SINCE="$tag"; continue; }
  TAGS+=("$tag"); BETAS+=("$beta")
done <<<"$plan"

if [[ ! -d "$CACHE_DIR/.git" ]]; then
  mkdir -p "$CACHE_DIR"
  git init -q "$CACHE_DIR"
  git -C "$CACHE_DIR" remote add origin "$REMOTE"
fi
cd "$CACHE_DIR"

# --shallow-since can shorten history as well as deepen it, so the cache
# remembers the oldest date it holds and never fetches to a later one.
held="$(git config --get ha-integration-upgrade.since || true)"
if [[ -n "$held" && "$held" < "$SINCE" ]]; then
  SINCE="$held"
fi

refspecs=()
for i in "${!TAGS[@]}"; do
  refspecs+=("+refs/tags/${BETAS[$i]}:refs/tags/${BETAS[$i]}" "+refs/tags/${TAGS[$i]}:refs/tags/${TAGS[$i]}")
done

if ! git fetch -q --no-tags --filter=blob:none --shallow-since="$SINCE" origin "${refspecs[@]}"; then
  die "could not fetch ${TAGS[*]} and their first betas from $REMOTE (is $TO_TAG released?)"
fi
git config ha-integration-upgrade.since "$SINCE"

for (( i = 1; i < ${#TAGS[@]}; i++ )); do
  git merge-base "${TAGS[$i-1]}" "${TAGS[$i]}" >/dev/null 2>&1 \
    || die "no merge base of ${TAGS[$i-1]} and ${TAGS[$i]} in history since $SINCE; rerun with an earlier --since"
done

commit_date() { git log -1 --format=%cs "$1"; }
shift_date() { python3 -I -c 'import datetime, sys; print(datetime.date.fromisoformat(sys.argv[1]) + datetime.timedelta(days=int(sys.argv[2])))' "$1" "$2"; }

echo "repo: $CACHE_DIR"
for i in "${!TAGS[@]}"; do
  for tag in "${BETAS[$i]}" "${TAGS[$i]}"; do
    printf 'tag: %-14s %s %s\n' "$tag" "$(git rev-parse --short "$tag^{commit}")" "$(commit_date "$tag")"
  done
done
for (( i = 1; i < ${#TAGS[@]}; i++ )); do
  from="${TAGS[$i-1]}" to="${TAGS[$i]}"
  since="$(shift_date "$(commit_date "${BETAS[$i-1]}")" -7)"
  until="$(shift_date "$(commit_date "$to")" 14)"
  echo "step: $from..$to commits: $(git rev-list --count "$from..$to") blog-window: $since $until"
done
