#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/ado-client.sh
source "$SCRIPT_DIR/lib/ado-client.sh"

usage() {
  cat <<EOF
Usage: ado-get-logs.sh --run-id ID [--failed-only] [--task NAME] [--tail N] [--json]

Fetch task log output from a pipeline run, with filtering.

Flags:
  --run-id ID       Build/run ID (required)
  --failed-only     Only show tasks with result 'failed'
  --task NAME       Filter by task name (case-insensitive substring match)
  --tail N          Show only last N lines per task log (default: 50)
  --json            Output JSON array of {task, result, log_id, lines[]}
EOF
}

RUN_ID="" FAILED_ONLY=false TASK_FILTER="" TAIL=50 JSON=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id)      RUN_ID="$2"; shift 2 ;;
    --failed-only) FAILED_ONLY=true; shift ;;
    --task)        TASK_FILTER="$2"; shift 2 ;;
    --tail)        TAIL="$2"; shift 2 ;;
    --json)        JSON=true; shift ;;
    -h|--help)     usage; exit 0 ;;
    *)             log_error "Unknown flag: $1"; usage >&2; exit 1 ;;
  esac
done

[[ -z "$RUN_ID" ]] && { log_error "--run-id is required"; usage >&2; exit 1; }

ado_require_env

log_info "Fetching timeline for run #${RUN_ID}..."
timeline_json=$(ado_api GET "build/builds/${RUN_ID}/timeline")

# Extract matching tasks as TSV: logId\tresult\tname
task_tsv=$(python3 -c "
import sys, json
tl = json.loads(sys.argv[1])
failed_only = sys.argv[2] == 'true'
task_filter = sys.argv[3].lower()

records = tl.get('records', [])
tasks = [r for r in records if r.get('type') == 'Task' and (r.get('log') or {}).get('id')]
tasks.sort(key=lambda r: r.get('order', 0))

for t in tasks:
    result = t.get('result', t.get('state', '?'))
    name = t.get('name', '?')
    log_id = t['log']['id']
    if failed_only and result != 'failed':
        continue
    if task_filter and task_filter not in name.lower():
        continue
    print(f'{log_id}\t{result}\t{name}')
" "$timeline_json" "$FAILED_ONLY" "$TASK_FILTER")

if [[ -z "$task_tsv" ]]; then
  log_info "No matching tasks found."
  if [[ "$JSON" == true ]]; then
    echo "[]"
  fi
  exit 0
fi

task_count=$(echo "$task_tsv" | wc -l | tr -d ' ')
log_info "Found ${task_count} matching task(s). Fetching logs..."

if [[ "$JSON" == true ]]; then
  json_items="["
  first=true
  while IFS=$'\t' read -r log_id result name; do
    log_text=$(ado_api GET "build/builds/${RUN_ID}/logs/${log_id}")
    item=$(python3 -c "
import sys, json
lines = sys.argv[1].splitlines()
tail = int(sys.argv[2])
if tail > 0 and len(lines) > tail:
    lines = lines[-tail:]
print(json.dumps({
    'task': sys.argv[3],
    'result': sys.argv[4],
    'log_id': int(sys.argv[5]),
    'lines': lines
}))
" "$log_text" "$TAIL" "$name" "$result" "$log_id")
    if [[ "$first" == true ]]; then
      first=false
    else
      json_items+=","
    fi
    json_items+="$item"
  done <<< "$task_tsv"
  json_items+="]"
  echo "$json_items" | python3 -m json.tool
else
  while IFS=$'\t' read -r log_id result name; do
    log_text=$(ado_api GET "build/builds/${RUN_ID}/logs/${log_id}")
    echo ""
    echo "=== [${result}] ${name} ==="
    if [[ "$TAIL" -gt 0 ]]; then
      echo "--- last ${TAIL} lines ---"
      echo "$log_text" | tail -n "$TAIL"
    else
      echo "$log_text"
    fi
  done <<< "$task_tsv"
fi
