#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: frontend-releases.sh --from TAG --to TAG [--cache-dir DIR] [--repo OWNER/NAME]

Print the release notes of every Home Assistant frontend release that a core
step brings in: the releases after the frontend version core pins at --from,
up to and including the one it pins at --to. Each line starts with its
release tag and a tab, oldest release first.

The pins come from homeassistant/components/frontend/manifest.json in the
cache repository fetch-core.sh fills, and the notes come through the gh CLI.

Flags:
  --from TAG       Core release tag of the step's start, such as 2026.10.0 (required)
  --to TAG         Core release tag of the step's end, such as 2026.11.0 (required)
  --cache-dir DIR  Cache repository that holds both tags
                   (default: ${XDG_CACHE_HOME:-~/.cache}/ha-integration-upgrade/core)
  --repo NAME      Frontend repository (default: home-assistant/frontend)
  -h, --help       Show this help

Example:
  frontend-releases.sh --from 2026.10.0 --to 2026.11.0 \
    | grep -i -E 'custom (card|element|module)|extra module|polyfill'
EOF
}

die() { echo "error: $*" >&2; exit 1; }
missing_value() { echo "error: $1 requires a value" >&2; usage >&2; exit 1; }

FROM="" TO="" REPO="home-assistant/frontend"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/.cache}/ha-integration-upgrade/core"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)      [[ -n "${2-}" ]] || missing_value "$1"; FROM="$2"; shift 2 ;;
    --to)        [[ -n "${2-}" ]] || missing_value "$1"; TO="$2"; shift 2 ;;
    --cache-dir) [[ -n "${2-}" ]] || missing_value "$1"; CACHE_DIR="$2"; shift 2 ;;
    --repo)      [[ -n "${2-}" ]] || missing_value "$1"; REPO="$2"; shift 2 ;;
    -h|--help)   usage; exit 0 ;;
    *)           echo "error: unknown flag: $1" >&2; usage >&2; exit 1 ;;
  esac
done

[[ -n "$FROM" ]] || { echo "error: --from is required" >&2; usage >&2; exit 1; }
[[ -n "$TO" ]] || { echo "error: --to is required" >&2; usage >&2; exit 1; }
command -v gh >/dev/null || die "the gh CLI is required"
[[ -d "$CACHE_DIR/.git" ]] || die "no cache repository at $CACHE_DIR; run fetch-core.sh first"

# The frontend version core pins at a tag, such as 20261028.4.
frontend_pin() {
  local manifest
  manifest="$(git -C "$CACHE_DIR" show "${1}:homeassistant/components/frontend/manifest.json" 2>/dev/null)" \
    || die "the cache holds no frontend manifest at $1; run fetch-core.sh for it first"
  printf '%s' "$manifest" | python3 -I -c '
import json, sys
for requirement in json.load(sys.stdin)["requirements"]:
    name, _, version = requirement.partition("==")
    if name == "home-assistant-frontend":
        print(version)
        break
else:
    sys.exit("no home-assistant-frontend requirement")
'
}

from_pin="$(frontend_pin "$FROM")"
to_pin="$(frontend_pin "$TO")"
if [[ "$from_pin" == "$to_pin" ]]; then
  echo "core pins home-assistant-frontend $from_pin at both tags" >&2
  exit 0
fi

# Release tags are YYYYMMDD.N. They compare as numbers, because 20261028.10
# follows 20261028.9.
releases="$(gh release list --repo "$REPO" --limit 300 --exclude-drafts --json tagName --jq '.[].tagName' \
  | python3 -I -c '
import sys
key = lambda tag: tuple(int(part) for part in tag.split("."))
low, high = key(sys.argv[1]), key(sys.argv[2])
tags = [line.strip() for line in sys.stdin if line.strip()]
for tag in sorted((t for t in tags if low < key(t) <= high), key=key):
    print(tag)
' "$from_pin" "$to_pin")"

[[ -n "$releases" ]] || die "no $REPO release found after $from_pin up to $to_pin"

while read -r tag; do
  gh release view "$tag" --repo "$REPO" --json body --jq .body | sed "s/^/$tag	/"
done <<<"$releases"
