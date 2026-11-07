#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: blog-posts.sh --since DATE --until DATE [--area AREA]... [--feed-base URL]

List the Home Assistant developer blog posts of a date window, one per line:
date, area, title, URL and the post's one-line description, separated by tabs.
Reads the per-area RSS feeds of the blog, oldest post first.

Flags:
  --since DATE      First day of the window, YYYY-MM-DD (required)
  --until DATE      Last day of the window, YYYY-MM-DD (required)
  --area AREA       Blog area to read, repeatable (default: core and marketplace)
  --feed-base URL   Blog root the feeds hang off
                    (default: https://contributors.home-assistant.io/blog)
  -h, --help        Show this help

Example:
  blog-posts.sh --since 2026-09-23 --until 2026-11-18
EOF
}

missing_value() { echo "error: $1 requires a value" >&2; usage >&2; exit 1; }

SINCE="" UNTIL="" FEED_BASE="https://contributors.home-assistant.io/blog"
AREAS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --since)     [[ -n "${2-}" ]] || missing_value "$1"; SINCE="$2"; shift 2 ;;
    --until)     [[ -n "${2-}" ]] || missing_value "$1"; UNTIL="$2"; shift 2 ;;
    --area)      [[ -n "${2-}" ]] || missing_value "$1"; AREAS+=("$2"); shift 2 ;;
    --feed-base) [[ -n "${2-}" ]] || missing_value "$1"; FEED_BASE="${2%/}"; shift 2 ;;
    -h|--help)   usage; exit 0 ;;
    *)           echo "error: unknown flag: $1" >&2; usage >&2; exit 1 ;;
  esac
done

[[ -n "$SINCE" ]] || { echo "error: --since is required" >&2; usage >&2; exit 1; }
[[ -n "$UNTIL" ]] || { echo "error: --until is required" >&2; usage >&2; exit 1; }
for d in "$SINCE" "$UNTIL"; do
  [[ "$d" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || { echo "error: not a YYYY-MM-DD date: $d" >&2; exit 1; }
done
[[ ${#AREAS[@]} -gt 0 ]] || AREAS=(core marketplace)

# Every feed is read before any line prints, so a failed feed prints nothing.
# Each goes to python on stdin as area and document, NUL-terminated. A post can
# list several areas, so the same link can arrive from two feeds.
feeds="$(mktemp)"
trap 'rm -f "$feeds"' EXIT
for area in "${AREAS[@]}"; do
  url="$FEED_BASE/$area/rss.xml"
  if ! feed="$(curl -fsSL "$url")"; then
    echo "error: could not read $url" >&2
    exit 1
  fi
  printf '%s\0%s\0' "$area" "$feed" >>"$feeds"
done

python3 -I -c '
import sys
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

since, until = sys.argv[1], sys.argv[2]
parts = sys.stdin.buffer.read().split(b"\0")
posts = {}
for area, feed in zip(parts[0::2], parts[1::2]):
    if not feed.strip():
        continue
    for item in ET.fromstring(feed).iter("item"):
        link = (item.findtext("link") or "").strip()
        date = parsedate_to_datetime(item.findtext("pubDate")).date().isoformat()
        if not since <= date <= until:
            continue
        post = posts.setdefault(link, {
            "date": date,
            "areas": [],
            "title": " ".join((item.findtext("title") or "").split()),
            "description": " ".join((item.findtext("description") or "").split()),
        })
        name = area.decode()
        if name not in post["areas"]:
            post["areas"].append(name)
for link, post in sorted(posts.items(), key=lambda kv: (kv[1]["date"], kv[0])):
    print("\t".join([post["date"], ",".join(post["areas"]), post["title"], link, post["description"]]))
' "$SINCE" "$UNTIL" <"$feeds"
