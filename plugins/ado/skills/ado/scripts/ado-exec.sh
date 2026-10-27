#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/ado-client.sh
source "$SCRIPT_DIR/lib/ado-client.sh"

usage() {
  cat <<'EOF'
Usage: ado-exec.sh [--org URL] -- COMMAND [ARG...]

Run COMMAND with Azure DevOps credentials in its environment.

With a PAT in AZURE_DEVOPS_EXT_PAT, COMMAND runs unchanged. Otherwise the
access token from ADO_TOKEN, or one minted from az login for the Entra
tenant that backs the org, is exported to COMMAND only as ADO_TOKEN,
AZURE_DEVOPS_EXT_PAT (read by az devops commands) and ADO_AUTH_HEADER
(for curl -H). Nothing is written to disk.

Flags:
  --org URL    Organization URL (default: $ADO_ORG)
  -h, --help   Show this help

Examples:
  ado-exec.sh -- az boards work-item show --id 123 --org "$ADO_ORG" --detect false
  ado-exec.sh -- bash -c 'curl -sS -H "$ADO_AUTH_HEADER" "$ADO_ORG/_apis/connectionData"'
EOF
}

ORG=""

missing_value() { log_error "$1 requires a value"; usage >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --org)     [[ -n "${2-}" ]] || missing_value "$1"; ORG="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --)        shift; break ;;
    *)         log_error "Unknown flag: $1"; usage >&2; exit 1 ;;
  esac
done

[[ $# -gt 0 ]] || { log_error "A command is required after --"; usage >&2; exit 1; }

if [[ -n "$ORG" ]]; then
  ADO_ORG="$ORG"
fi
ado_require_org || exit 1

if [[ -n "${AZURE_DEVOPS_EXT_PAT:-}" ]] && ! _ado_is_jwt "$AZURE_DEVOPS_EXT_PAT"; then
  exec "$@"
fi

ado_resolve_auth || exit 1
export ADO_TOKEN="$_ADO_TOKEN" AZURE_DEVOPS_EXT_PAT="$_ADO_TOKEN" ADO_AUTH_HEADER
if [[ "$_ADO_AUTH_SOURCE" == minted ]]; then
  export ADO_TOKEN_MINTED=1
else
  unset ADO_TOKEN_MINTED
fi
exec "$@"
