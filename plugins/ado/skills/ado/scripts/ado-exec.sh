#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/ado-client.sh
source "$SCRIPT_DIR/lib/ado-client.sh"

usage() {
  cat <<'EOF'
Usage: ado-exec.sh [--org URL] [--shared-az-config] -- COMMAND [ARG...]

Run COMMAND with Azure DevOps credentials in its environment.

A PAT in AZURE_DEVOPS_EXT_PAT is used as it is. Otherwise the access token
from ADO_TOKEN, or one minted from az login for the Entra tenant that backs
the org, is exported to COMMAND only as ADO_TOKEN, AZURE_DEVOPS_EXT_PAT
(read by az devops commands) and ADO_AUTH_HEADER (for curl -H). No
credential is written to disk.

COMMAND runs with AZURE_CONFIG_DIR set to an empty temporary directory,
which is removed when COMMAND exits. The az devops commands in COMMAND then
find no az login account and use the exported credential. AZURE_EXTENSION_DIR
and AZURE_DEVOPS_EXT_CONFIG_DIR keep pointing at your az extensions and at
the azure-devops extension's settings and cache.

Flags:
  --org URL            Organization URL (default: $ADO_ORG)
  --shared-az-config   Run COMMAND with your az config and its az login
                       accounts, for a block that also runs Azure resource
                       commands such as az account
  -h, --help           Show this help

Examples:
  ado-exec.sh -- az boards work-item show --id 123 --org "$ADO_ORG" --detect false
  ado-exec.sh -- bash -c 'curl -sS -H "$ADO_AUTH_HEADER" "$ADO_ORG/_apis/connectionData"'
  ado-exec.sh --shared-az-config -- bash -c 'az account show; az devops project list --org "$ADO_ORG"'
EOF
}

ORG=""
SHARED_AZ_CONFIG=0

missing_value() { log_error "$1 requires a value"; usage >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --org)              [[ -n "${2-}" ]] || missing_value "$1"; ORG="$2"; shift 2 ;;
    --shared-az-config) SHARED_AZ_CONFIG=1; shift ;;
    -h|--help)          usage; exit 0 ;;
    --)                 shift; break ;;
    *)                  log_error "Unknown flag: $1"; usage >&2; exit 1 ;;
  esac
done

[[ $# -gt 0 ]] || { log_error "A command is required after --"; usage >&2; exit 1; }

if [[ -n "$ORG" ]]; then
  ADO_ORG="$ORG"
fi
ado_require_org || exit 1

if [[ -z "${AZURE_DEVOPS_EXT_PAT:-}" ]] || _ado_is_jwt "$AZURE_DEVOPS_EXT_PAT"; then
  ado_resolve_auth || exit 1
  export ADO_TOKEN="$_ADO_TOKEN" AZURE_DEVOPS_EXT_PAT="$_ADO_TOKEN" ADO_AUTH_HEADER
  if [[ "$_ADO_AUTH_SOURCE" == minted ]]; then
    export ADO_TOKEN_MINTED=1
  else
    unset ADO_TOKEN_MINTED
  fi
fi

if [[ "$SHARED_AZ_CONFIG" == 1 ]]; then
  exec "$@"
fi

# The az devops extension tries cached az login accounts before
# AZURE_DEVOPS_EXT_PAT and uses the first one the org accepts, so with the
# caller's az config a command can run as another signed-in account. An
# empty config holds no account. ADO_AZ_CONFIG_DIR lets the client library
# still mint from the caller's az login.
az_config="${AZURE_CONFIG_DIR:-$HOME/.azure}"
export ADO_AZ_CONFIG_DIR="$az_config"
export AZURE_EXTENSION_DIR="${AZURE_EXTENSION_DIR:-$az_config/cliextensions}"
export AZURE_DEVOPS_EXT_CONFIG_DIR="${AZURE_DEVOPS_EXT_CONFIG_DIR:-$az_config/azuredevops}"

tmp_root="${TMPDIR:-/tmp}"
if ! fresh_config=$(mktemp -d "${tmp_root%/}/ado-exec-az.XXXXXX"); then
  log_error "Could not create a temporary az config directory in ${tmp_root}"
  exit 1
fi
trap 'rm -rf -- "$fresh_config"' EXIT
export AZURE_CONFIG_DIR="$fresh_config"

status=0
"$@" || status=$?
exit "$status"
