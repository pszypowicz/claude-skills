#!/usr/bin/env bash
#
# Validate plugin version consistency across plugin.json, marketplace.json,
# and existing git tags. Intended for PR CI.

set -euo pipefail
shopt -s nullglob

show_help() {
  cat <<'EOF'
check-plugin-versions.sh - validate plugin version consistency

Usage:
  check-plugin-versions.sh [options]

Options:
  --base-ref <ref>  Base git ref to compare against (default: origin/main).
                    Used to detect which plugins had their version bumped in
                    the PR.
  -h, --help        Show this help.

Checks (fails on any):
  1. Every plugins/*/.claude-plugin/plugin.json and its marketplace.json entry
     must agree on version.
  2. The README.md plugin table must list every plugin with the same version.
  3. For any plugin whose version differs from the base ref, the tag
     {name}--v{version} must not already exist.

Example:
  .github/scripts/check-plugin-versions.sh --base-ref origin/main

Exits 0 on success, 1 on any validation failure, 2 on argument errors.
EOF
}

base_ref="origin/main"
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) show_help; exit 0 ;;
    --base-ref)
      if [[ $# -lt 2 ]]; then
        echo "error: --base-ref requires a value" >&2
        exit 2
      fi
      base_ref="$2"
      shift 2
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      show_help >&2
      exit 2
      ;;
  esac
done

repo_root="$(git rev-parse --show-toplevel)"
marketplace="$repo_root/.claude-plugin/marketplace.json"
readme="$repo_root/README.md"

if [[ ! -f "$marketplace" ]]; then
  echo "error: marketplace.json not found at $marketplace" >&2
  exit 1
fi
if [[ ! -f "$readme" ]]; then
  echo "error: README.md not found at $readme" >&2
  exit 1
fi

# Version cell of the README plugin-table row for plugin $1, empty when the
# row is missing. Rows look like: | [`ado`](plugins/ado/...) | 2.0.1 | ... |
readme_version() {
  awk -F'|' -v name="$1" '$2 ~ "\\[`" name "`\\]" { gsub(/ /, "", $3); print $3; exit }' "$readme"
}

base_commit=""
if git rev-parse -q --verify "$base_ref" >/dev/null 2>&1; then
  base_commit="$(git rev-parse "$base_ref")"
else
  echo "warning: base ref '$base_ref' not resolvable; running consistency check only" >&2
fi

failures=0
plugin_jsons=("$repo_root"/plugins/*/.claude-plugin/plugin.json)
if [[ ${#plugin_jsons[@]} -eq 0 ]]; then
  echo "error: no plugins found under $repo_root/plugins/" >&2
  exit 1
fi

for plugin_json in "${plugin_jsons[@]}"; do
  rel_path="${plugin_json#"$repo_root"/}"
  name="$(jq -r '.name' "$plugin_json")"
  version="$(jq -r '.version' "$plugin_json")"

  marketplace_version="$(jq -r --arg n "$name" '.plugins[] | select(.name == $n) | .version' "$marketplace")"
  if [[ -z "$marketplace_version" || "$marketplace_version" == "null" ]]; then
    echo "FAIL: $name has no entry in marketplace.json"
    failures=$((failures + 1))
    continue
  fi
  if [[ "$marketplace_version" != "$version" ]]; then
    echo "FAIL: $name version mismatch - plugin.json=$version marketplace.json=$marketplace_version"
    failures=$((failures + 1))
    continue
  fi

  readme_ver="$(readme_version "$name")"
  if [[ -z "$readme_ver" ]]; then
    echo "FAIL: $name has no row in the README plugin table"
    failures=$((failures + 1))
    continue
  fi
  if [[ "$readme_ver" != "$version" ]]; then
    echo "FAIL: $name version mismatch - plugin.json=$version README.md=$readme_ver"
    failures=$((failures + 1))
    continue
  fi

  if [[ -z "$base_commit" ]]; then
    echo "ok:   $name $version (consistency only; base-ref check skipped)"
    continue
  fi

  base_version="$(git show "$base_commit:$rel_path" 2>/dev/null | jq -r '.version' 2>/dev/null || true)"
  if [[ -z "$base_version" || "$base_version" == "null" ]]; then
    tag="${name}--v${version}"
    if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
      echo "FAIL: new plugin $name version $version already has tag $tag"
      failures=$((failures + 1))
      continue
    fi
    echo "ok:   $name $version (new plugin; tag $tag will be created on merge)"
    continue
  fi

  if [[ "$base_version" == "$version" ]]; then
    echo "ok:   $name $version (unchanged)"
    continue
  fi

  tag="${name}--v${version}"
  if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    echo "FAIL: $name version $version already has tag $tag - pick a new version"
    failures=$((failures + 1))
    continue
  fi
  echo "ok:   $name $base_version -> $version (tag $tag will be created on merge)"
done

if [[ $failures -gt 0 ]]; then
  echo
  echo "$failures plugin(s) failed validation"
  exit 1
fi

echo
echo "all plugins ok"
