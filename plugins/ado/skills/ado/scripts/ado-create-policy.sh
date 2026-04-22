#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/ado-client.sh
source "$SCRIPT_DIR/lib/ado-client.sh"

usage() {
  cat <<EOF >&2
Usage:
  ado-create-policy.sh --repo NAME --type build             --pipeline-id ID [OPTIONS]
  ado-create-policy.sh --repo NAME --type approver          [--min-approvers N] [OPTIONS]
  ado-create-policy.sh --repo NAME --type required-reviewer --reviewer ID_OR_SEARCH [OPTIONS]

Create a branch policy on a repository.

Policy types:
  build               Build validation (requires --pipeline-id)
  approver            Minimum reviewer/approver count
  required-reviewer   Specific person or group must approve (requires --reviewer)

Flags:
  --repo NAME           Repository name (required)
  --type TYPE           Policy type: build | approver | required-reviewer (required)
  --pipeline-id ID      Pipeline ID (required for build)
  --min-approvers N     Minimum approver count (default: 1, for approver type)
  --creator-vote        Creator's vote counts as a reviewer
  --reset-on-push       Reset approvals when source branch is updated (default: true)
  --no-reset-on-push    Keep approvals when source branch is updated
  --reviewer VALUE      Identity: email, display name, team name, or raw GUID (repeatable)
  --filename-patterns P Comma-separated path patterns (e.g. "/*.tf,/pipelines/*")
  --branch BRANCH       Target branch (default: main)
  --display-name TEXT   Display name for the policy
  --blocking            Policy blocks PR completion (default)
  --no-blocking         Policy is advisory only
  --json                Output raw JSON instead of summary
EOF
  exit 1
}

REPO="" TYPE="" PIPELINE_ID="" BRANCH="main" DISPLAY_NAME="" BLOCKING=true JSON=false
MIN_APPROVERS=1 CREATOR_VOTE=false RESET_ON_PUSH=true
REVIEWERS=() FILENAME_PATTERNS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)              REPO="$2"; shift 2 ;;
    --type)              TYPE="$2"; shift 2 ;;
    --pipeline-id)       PIPELINE_ID="$2"; shift 2 ;;
    --min-approvers)     MIN_APPROVERS="$2"; shift 2 ;;
    --creator-vote)      CREATOR_VOTE=true; shift ;;
    --reset-on-push)     RESET_ON_PUSH=true; shift ;;
    --no-reset-on-push)  RESET_ON_PUSH=false; shift ;;
    --reviewer)          REVIEWERS+=("$2"); shift 2 ;;
    --filename-patterns) FILENAME_PATTERNS="$2"; shift 2 ;;
    --branch)            BRANCH="$2"; shift 2 ;;
    --display-name)      DISPLAY_NAME="$2"; shift 2 ;;
    --blocking)          BLOCKING=true; shift ;;
    --no-blocking)       BLOCKING=false; shift ;;
    --json)              JSON=true; shift ;;
    -h|--help)           usage ;;
    *)                   log_error "Unknown flag: $1"; usage ;;
  esac
done

[[ -z "$REPO" ]] && { log_error "--repo is required"; usage; }
[[ -z "$TYPE" ]] && { log_error "--type is required"; usage; }
[[ "$TYPE" != "build" && "$TYPE" != "approver" && "$TYPE" != "required-reviewer" ]] && \
  { log_error "--type must be 'build', 'approver', or 'required-reviewer'"; usage; }
[[ "$TYPE" == "build" && -z "$PIPELINE_ID" ]] && { log_error "--pipeline-id is required for build type"; usage; }
[[ "$TYPE" == "required-reviewer" && ${#REVIEWERS[@]} -eq 0 ]] && { log_error "--reviewer is required for required-reviewer type"; usage; }

ado_require_env

# Resolve a reviewer search term to an ADO identity GUID.
# Accepts: raw GUID, email address, display name, or team name.
# Users: Graph users API -> descriptor -> Storage Keys API -> GUID
# Teams: Teams API -> id (already a GUID)
resolve_reviewer() {
  local search="$1"

  # If it looks like a GUID already, return as-is
  if [[ "$search" =~ ^[0-9a-fA-F-]{36}$ ]]; then
    echo "$search"
    return
  fi

  # Extract org name from ADO_ORG for VSSPS URL
  local org_name
  org_name="${ADO_ORG#https://dev.azure.com/}"
  local vssps_base="https://vssps.dev.azure.com/${org_name}"

  [[ -z "${ADO_AUTH_HEADER:-}" ]] && ado_resolve_auth

  # Try Graph users API - match by email or display name, return descriptor
  local users_result
  users_result=$(curl -s -S \
    -H "$ADO_AUTH_HEADER" -H "Content-Type: application/json" \
    "${vssps_base}/_apis/graph/users?api-version=7.1-preview.1" 2>/dev/null) || true

  if [[ -n "$users_result" ]]; then
    local descriptor
    descriptor=$(python3 -c "
import sys, json
raw = sys.argv[1].lstrip('\ufeff')
try:
    data = json.loads(raw)
except (json.JSONDecodeError, ValueError):
    sys.exit(1)
users = data.get('value', [])
search = sys.argv[2].lower()

# Exact email match
for u in users:
    if (u.get('mailAddress') or '').lower() == search:
        print(u['descriptor'])
        sys.exit(0)

# Exact display name match
for u in users:
    if (u.get('displayName') or '').lower() == search:
        print(u['descriptor'])
        sys.exit(0)

sys.exit(1)
" "$users_result" "$search" 2>/dev/null) || true

    # Convert descriptor to storage key (GUID)
    if [[ -n "$descriptor" ]]; then
      local sk_result
      sk_result=$(curl -s -S \
        -H "$ADO_AUTH_HEADER" -H "Content-Type: application/json" \
        "${vssps_base}/_apis/graph/storagekeys/${descriptor}?api-version=7.1-preview.1" 2>/dev/null) || true

      local guid
      guid=$(python3 -c "
import sys, json
try:
    data = json.loads(sys.argv[1].lstrip('\ufeff'))
    print(data['value'])
except Exception:
    sys.exit(1)
" "$sk_result" 2>/dev/null) || true

      if [[ -n "$guid" ]]; then
        echo "$guid"
        return
      fi
      log_error "Found user descriptor but failed to get storage key GUID"
      return 1
    fi
  fi

  # Teams API fallback - team id is already a GUID
  local teams_result
  teams_result=$(curl -s -S \
    -H "$ADO_AUTH_HEADER" -H "Content-Type: application/json" \
    "${ADO_ORG}/_apis/projects/${ADO_PROJECT}/teams?api-version=7.1" 2>/dev/null) || true

  if [[ -n "$teams_result" ]]; then
    local resolved
    resolved=$(python3 -c "
import sys, json
raw = sys.argv[1].lstrip('\ufeff')
try:
    data = json.loads(raw)
except (json.JSONDecodeError, ValueError):
    sys.exit(1)
search = sys.argv[2].lower()
for t in data.get('value', []):
    if t.get('name', '').lower() == search:
        print(t['id'])
        sys.exit(0)
sys.exit(1)
" "$teams_result" "$search" 2>/dev/null) || true

    if [[ -n "$resolved" ]]; then
      echo "$resolved"
      return
    fi
  fi

  # Nothing found - list available users and teams
  python3 -c "
import sys, json

print('Could not resolve reviewer: ' + sys.argv[1], file=sys.stderr)

try:
    users = json.loads(sys.argv[2].lstrip('\ufeff')).get('value', [])
    if users:
        print('Available users:', file=sys.stderr)
        for u in users:
            dn = u.get('displayName', '?')
            mail = u.get('mailAddress', '?')
            print(f'  {dn}  [{mail}]', file=sys.stderr)
except Exception:
    pass

try:
    teams = json.loads(sys.argv[3].lstrip('\ufeff')).get('value', [])
    if teams:
        print('Available teams:', file=sys.stderr)
        for t in teams:
            print(f'  {t[\"id\"]}  {t[\"name\"]}', file=sys.stderr)
except Exception:
    pass
" "$search" "${users_result:-{}}" "${teams_result:-{}}" >&2
  return 1
}

# Resolve all reviewer IDs upfront for required-reviewer type
REVIEWER_IDS=()
if [[ "$TYPE" == "required-reviewer" ]]; then
  [[ -z "${ADO_AUTH_HEADER:-}" ]] && ado_resolve_auth
  for rev in "${REVIEWERS[@]}"; do
    rid=$(resolve_reviewer "$rev") || exit 1
    REVIEWER_IDS+=("$rid")
  done
fi

repo_json=$(ado_api GET "git/repositories/${REPO}")
repo_id=$(echo "$repo_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

if [[ "$TYPE" == "build" ]]; then
  body=$(python3 -c "
import json, sys
repo_id = sys.argv[1]
pipeline_id = int(sys.argv[2])
branch = sys.argv[3]
display_name = sys.argv[4]
blocking = sys.argv[5] == 'true'

policy = {
    'isEnabled': True,
    'isBlocking': blocking,
    'type': {
        'id': '0609b952-1397-4640-95ec-e00a01b2c241'
    },
    'settings': {
        'buildDefinitionId': pipeline_id,
        'queueOnSourceUpdateOnly': False,
        'manualQueueOnly': False,
        'displayName': display_name,
        'validDuration': 0.0,
        'scope': [{
            'refName': f'refs/heads/{branch}',
            'matchKind': 'Exact',
            'repositoryId': repo_id
        }]
    }
}
print(json.dumps(policy))
" "$repo_id" "$PIPELINE_ID" "$BRANCH" "$DISPLAY_NAME" "$BLOCKING")

elif [[ "$TYPE" == "approver" ]]; then
  body=$(python3 -c "
import json, sys
repo_id = sys.argv[1]
branch = sys.argv[2]
blocking = sys.argv[3] == 'true'
min_approvers = int(sys.argv[4])
creator_vote = sys.argv[5] == 'true'
reset_on_push = sys.argv[6] == 'true'

policy = {
    'isEnabled': True,
    'isBlocking': blocking,
    'type': {
        'id': 'fa4e907d-c16b-4a4c-9dfa-4906e5d171dd'
    },
    'settings': {
        'minimumApproverCount': min_approvers,
        'creatorVoteCounts': creator_vote,
        'allowDownvotes': False,
        'resetOnSourcePush': reset_on_push,
        'scope': [{
            'refName': f'refs/heads/{branch}',
            'matchKind': 'Exact',
            'repositoryId': repo_id
        }]
    }
}
print(json.dumps(policy))
" "$repo_id" "$BRANCH" "$BLOCKING" "$MIN_APPROVERS" "$CREATOR_VOTE" "$RESET_ON_PUSH")

elif [[ "$TYPE" == "required-reviewer" ]]; then
  # Build JSON array of reviewer IDs
  reviewer_json=$(printf '%s\n' "${REVIEWER_IDS[@]}" | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin]))")

  body=$(python3 -c "
import json, sys
repo_id = sys.argv[1]
branch = sys.argv[2]
blocking = sys.argv[3] == 'true'
reviewer_ids = json.loads(sys.argv[4])
filename_patterns = sys.argv[5]
display_name = sys.argv[6]

settings = {
    'requiredReviewerIds': reviewer_ids,
    'scope': [{
        'refName': f'refs/heads/{branch}',
        'matchKind': 'Exact',
        'repositoryId': repo_id
    }]
}
if filename_patterns:
    settings['filenamePatterns'] = [p.strip() for p in filename_patterns.split(',')]
if display_name:
    settings['message'] = display_name

policy = {
    'isEnabled': True,
    'isBlocking': blocking,
    'type': {
        'id': 'fd2167ab-b0be-447a-8ec8-39368250530e'
    },
    'settings': settings
}
print(json.dumps(policy))
" "$repo_id" "$BRANCH" "$BLOCKING" "$reviewer_json" "$FILENAME_PATTERNS" "$DISPLAY_NAME")
fi

result=$(ado_api POST "policy/configurations" "$body")

if [[ "$JSON" == true ]]; then
  echo "$result" | python3 -m json.tool
else
  python3 -c "
import sys, json
cfg = json.loads(sys.argv[1])
cid = cfg['id']
blocking = 'blocking' if cfg.get('isBlocking') else 'advisory'
scope = cfg.get('settings', {}).get('scope', [{}])[0]
ref = scope.get('refName', '?')
ptype = sys.argv[2]

if ptype == 'build':
    name = cfg.get('settings', {}).get('displayName', '')
    print(f'Created policy #{cid}: {name} (Build, {blocking}, {ref})')
elif ptype == 'approver':
    count = cfg.get('settings', {}).get('minimumApproverCount', 1)
    reset = cfg.get('settings', {}).get('resetOnSourcePush', False)
    creator = cfg.get('settings', {}).get('creatorVoteCounts', False)
    print(f'Created policy #{cid}: Minimum reviewers (Approver, {blocking}, {ref})')
    print(f'  Min approvers:    {count}')
    print(f'  Reset on push:    {reset}')
    print(f'  Creator vote:     {creator}')
elif ptype == 'required-reviewer':
    ids = cfg.get('settings', {}).get('requiredReviewerIds', [])
    patterns = cfg.get('settings', {}).get('filenamePatterns', [])
    msg = cfg.get('settings', {}).get('message', '')
    id_str = ', '.join(ids)
    print(f'Created policy #{cid}: Required reviewers ({blocking}, {ref})')
    print(f'  Reviewer IDs:     {id_str}')
    if msg:
        print(f'  Message:          {msg}')
    if patterns:
        pat_str = ', '.join(patterns)
        print(f'  File patterns:    {pat_str}')
" "$result" "$TYPE"
fi
