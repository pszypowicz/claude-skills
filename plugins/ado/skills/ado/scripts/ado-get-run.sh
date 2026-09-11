#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/ado-client.sh
source "$SCRIPT_DIR/lib/ado-client.sh"

usage() {
  cat <<EOF
Usage: ado-get-run.sh --run-id ID [--json]

Show run metadata and stage/job tree with pass/fail indicators.

Flags:
  --run-id ID   Build/run ID (required)
  --json        Output raw JSON (run object with _timeline merged)
EOF
}

RUN_ID="" JSON=false

missing_value() { log_error "$1 requires a value"; usage >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id) [[ -n "${2-}" ]] || missing_value "$1"; RUN_ID="$2"; shift 2 ;;
    --json)   JSON=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *)         log_error "Unknown flag: $1"; usage >&2; exit 1 ;;
  esac
done

[[ -z "$RUN_ID" ]] && { log_error "--run-id is required"; usage >&2; exit 1; }

ado_require_env

log_info "Fetching run #${RUN_ID}..."

run_json=$(ado_api GET "build/builds/${RUN_ID}")
timeline_json=$(ado_api GET "build/builds/${RUN_ID}/timeline")

if [[ "$JSON" == true ]]; then
  python3 -c "
import sys, json
run = json.loads(sys.argv[1])
tl = json.loads(sys.argv[2])
run['_timeline'] = tl.get('records', [])
print(json.dumps(run, indent=2))
" "$run_json" "$timeline_json"
else
  python3 -c "
import sys, json
from datetime import datetime

run = json.loads(sys.argv[1])
tl = json.loads(sys.argv[2])
records = tl.get('records', [])

build_number = run.get('buildNumber', '?')
def_name = run.get('definition', {}).get('name', '?')
status = run.get('status', '?')
result = run.get('result', '-')
branch = run.get('sourceBranch', '').replace('refs/heads/', '')
reason = run.get('reason', '?')
start_time = run.get('startTime', '')
finish_time = run.get('finishTime', '')

duration_str = '-'
if start_time and finish_time:
    try:
        fmt = '%Y-%m-%dT%H:%M:%S'
        s = datetime.strptime(start_time[:19], fmt)
        f = datetime.strptime(finish_time[:19], fmt)
        total_secs = int((f - s).total_seconds())
        mins, secs = divmod(total_secs, 60)
        duration_str = f'{mins}m {secs}s'
    except Exception:
        duration_str = '?'

print(f'Run #{build_number}   {def_name}')
print(f'  State:     {status}')
print(f'  Result:    {result}')
print(f'  Branch:    {branch}')
print(f'  Reason:    {reason}')
print(f'  Started:   {start_time[:19].replace(\"T\", \" \")}')
print(f'  Finished:  {finish_time[:19].replace(\"T\", \" \") if finish_time else \"-\"}')
print(f'  Duration:  {duration_str}')
print()

# Build stage/job tree
stages = [r for r in records if r.get('type') == 'Stage']
jobs = [r for r in records if r.get('type') == 'Job']
stages.sort(key=lambda r: r.get('order', 0))
jobs.sort(key=lambda r: r.get('order', 0))

# ADO hierarchy: Stage -> Phase -> Job. Jobs have Phase parents, not Stage parents.
# Build Phase->Stage lookup so we can resolve Jobs back to their Stage.
phases = [r for r in records if r.get('type') == 'Phase']
phase_to_stage = {}
for p in phases:
    phase_to_stage[p.get('id', '')] = p.get('parentId', '')

jobs_by_stage = {}
for j in jobs:
    phase_id = j.get('parentId', '')
    stage_id = phase_to_stage.get(phase_id, phase_id)
    jobs_by_stage.setdefault(stage_id, []).append(j)

def fmt_result(r):
    res = r.get('result') or r.get('state') or '?'
    return f'[{res:<9}]'

print('Stages/Jobs:')
for stage in stages:
    print(f'  {fmt_result(stage)} {stage.get(\"name\", \"?\")}')
    children = jobs_by_stage.get(stage.get('id', ''), [])
    for job in children:
        print(f'    {fmt_result(job)} Job {job.get(\"name\", \"?\")}')

web_url = f'{sys.argv[3]}/_build/results?buildId={sys.argv[4]}'
print(f'  Web: {web_url}')
" "$run_json" "$timeline_json" "${ADO_ORG}/${ADO_PROJECT}" "$RUN_ID"
fi
