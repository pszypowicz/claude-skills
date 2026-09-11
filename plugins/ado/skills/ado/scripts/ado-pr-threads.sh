#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/ado-client.sh
source "$SCRIPT_DIR/lib/ado-client.sh"

usage() {
  cat <<EOF
Usage: ado-pr-threads.sh --pr-id ID --repo REPO [--status STATUS] [--file PATH] [--json]

List PR comment threads with optional filtering.

Flags:
  --pr-id ID        Pull request ID (required)
  --repo REPO       Repository name (required)
  --status STATUS   Filter by status: active, fixed, wontFix, closed, byDesign, pending, all (default: all)
  --file PATH       Filter by file path (e.g. "/src/main.tf")
  --json            Output raw JSON (filtered threads array)
EOF
}

PR_ID="" REPO="" STATUS="all" FILE_FILTER="" JSON=false

missing_value() { log_error "$1 requires a value"; usage >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pr-id)  [[ -n "${2-}" ]] || missing_value "$1"; PR_ID="$2"; shift 2 ;;
    --repo)   [[ -n "${2-}" ]] || missing_value "$1"; REPO="$2"; shift 2 ;;
    --status) [[ -n "${2-}" ]] || missing_value "$1"; STATUS="$2"; shift 2 ;;
    --file)   [[ -n "${2-}" ]] || missing_value "$1"; FILE_FILTER="$2"; shift 2 ;;
    --json)   JSON=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *)         log_error "Unknown flag: $1"; usage >&2; exit 1 ;;
  esac
done

[[ -z "$PR_ID" ]] && { log_error "--pr-id is required"; usage >&2; exit 1; }
[[ -z "$REPO" ]] && { log_error "--repo is required"; usage >&2; exit 1; }

ado_require_env

log_info "Fetching threads for PR #${PR_ID} in ${REPO}..."

threads_json=$(ado_api GET "git/repositories/${REPO}/pullRequests/${PR_ID}/threads")

python3 -c "
import sys, json

data = json.loads(sys.argv[1])
status_filter = sys.argv[2]
file_filter = sys.argv[3]
output_json = sys.argv[4] == 'true'

threads = data.get('value', [])

# Exclude system threads
threads = [t for t in threads if not any(
    c.get('commentType') == 'system' for c in t.get('comments', [])
)]

# Filter by status
if status_filter != 'all':
    threads = [t for t in threads if t.get('status') == status_filter]

# Filter by file path
if file_filter:
    threads = [t for t in threads
               if t.get('threadContext', {}).get('filePath', '') == file_filter]

if output_json:
    print(json.dumps(threads, indent=2))
    sys.exit(0)

if not threads:
    print('No threads found.')
    sys.exit(0)

# Human-readable table
header = f\"{'ID':<10} {'Status':<10} {'File:Line':<35} {'Author':<25} {'Replies':<8} Comment\"
print(header)
print('-' * len(header))

for t in threads:
    tid = t.get('id', '?')
    status = t.get('status', '-')
    ctx = t.get('threadContext') or {}
    file_path = ctx.get('filePath', '-')
    line = ctx.get('rightFileStart', {}).get('line', '')
    file_line = f'{file_path}:{line}' if line else file_path

    comments = t.get('comments', [])
    first = comments[0] if comments else {}
    author = first.get('author', {}).get('displayName', '?')
    content = first.get('content', '')
    # Truncate for display
    snippet = content[:60].replace('\n', ' ')
    if len(content) > 60:
        snippet += '...'
    reply_count = len(comments) - 1

    print(f'{tid:<10} {status:<10} {file_line:<35} {author:<25} {reply_count:<8} {snippet}')
" "$threads_json" "$STATUS" "$FILE_FILTER" "$JSON"
