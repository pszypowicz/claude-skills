#!/usr/bin/env bash
#
# Create (and optionally push) {name}--v{version} tags for every plugin whose
# current version in plugin.json does not already have a matching tag.
# Idempotent: plugins already tagged at their current version are skipped.

set -euo pipefail
shopt -s nullglob

show_help() {
  cat <<'EOF'
tag-plugins.sh - create and push missing plugin release tags

Usage:
  tag-plugins.sh [options]

Options:
  --dry-run    Print what would be tagged without creating anything.
  --no-push    Create tags locally but do not push to origin.
  -h, --help   Show this help.

For every plugins/*/.claude-plugin/plugin.json this creates an annotated tag
{name}--v{version} at HEAD if one does not already exist, then pushes it to
origin (unless --no-push is given). Existing tags are skipped silently.

Requires jq and git. Assumes the working tree is clean.

Examples:
  tag-plugins.sh --dry-run
  tag-plugins.sh --no-push
  tag-plugins.sh

Exits 0 on success, 1 on runtime errors, 2 on argument errors.
EOF
}

dry_run=0
do_push=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) show_help; exit 0 ;;
    --dry-run) dry_run=1; shift ;;
    --no-push) do_push=0; shift ;;
    *)
      echo "error: unknown argument: $1" >&2
      show_help >&2
      exit 2
      ;;
  esac
done

repo_root="$(git rev-parse --show-toplevel)"

plugin_jsons=("$repo_root"/plugins/*/.claude-plugin/plugin.json)
if [[ ${#plugin_jsons[@]} -eq 0 ]]; then
  echo "error: no plugins found under $repo_root/plugins/" >&2
  exit 1
fi

created_count=0
for plugin_json in "${plugin_jsons[@]}"; do
  name="$(jq -r '.name' "$plugin_json")"
  version="$(jq -r '.version' "$plugin_json")"
  tag="${name}--v${version}"

  if git -C "$repo_root" rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    echo "skip:   $tag (already exists)"
    continue
  fi

  if [[ $dry_run -eq 1 ]]; then
    echo "would:  create $tag at HEAD"
    continue
  fi

  echo "create: $tag"
  git -C "$repo_root" tag -a "$tag" -m "$name $version"
  created_count=$((created_count + 1))

  if [[ $do_push -eq 1 ]]; then
    echo "push:   $tag -> origin"
    git -C "$repo_root" push origin "refs/tags/$tag"
  fi
done

if [[ $dry_run -eq 0 && $created_count -eq 0 ]]; then
  echo "no new tags created"
fi
