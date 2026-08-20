#!/usr/bin/env bash
# Shared ADO REST API client library.
# Source this file; do not execute directly.
#
# Required env vars: ADO_ORG, ADO_PROJECT
# Auth (checked in order): AZURE_DEVOPS_EXT_PAT, ADO_TOKEN, az CLI fallback

set -euo pipefail

_ADO_PROJECT_ID=""

log_info()  { printf '[INFO]  %s\n' "$*" >&2; }
log_error() { printf '[ERROR] %s\n' "$*" >&2; }

# Assert ADO_ORG and ADO_PROJECT are set, and normalize ADO_ORG.
# Call this from the calling script AFTER arg parsing (so --help and usage
# errors can surface without requiring auth configuration). Idempotent.
ado_require_env() {
  : "${ADO_ORG:?Set ADO_ORG (e.g. https://dev.azure.com/myorg)}"
  : "${ADO_PROJECT:?Set ADO_PROJECT}"
  ADO_ORG="${ADO_ORG%/}"
  export ADO_ORG ADO_PROJECT
  if [ -n "${AZURE_DEVOPS_EXT_PAT:-}" ]; then
    export AZURE_DEVOPS_EXT_PAT
  fi
}

ado_resolve_auth() {
  if [[ -n "${AZURE_DEVOPS_EXT_PAT:-}" ]]; then
    local b64
    b64=$(printf ':%s' "$AZURE_DEVOPS_EXT_PAT" | base64 | tr -d '\n')
    ADO_AUTH_HEADER="Authorization: Basic ${b64}"
  elif [[ -n "${ADO_TOKEN:-}" ]]; then
    ADO_AUTH_HEADER="Authorization: Bearer ${ADO_TOKEN}"
  else
    local token
    # 499b84ac-... is the public Azure DevOps resource GUID (same for every tenant).
    token=$(az account get-access-token \
      --resource 499b84ac-1321-427f-aa17-267ca6975798 \
      --query accessToken -o tsv 2>/dev/null) \
      || { log_error "No auth found. Set AZURE_DEVOPS_EXT_PAT, ADO_TOKEN, or log in with az cli."; return 1; }
    ADO_AUTH_HEADER="Authorization: Bearer ${token}"
  fi
  export ADO_AUTH_HEADER
}

# ado_api METHOD PATH [BODY] [API_VERSION]
# PATH is relative (e.g. "git/repositories") - base URL is built automatically.
ado_api() {
  local method="$1" path="$2" body="${3:-}" api_version="${4:-7.1}"

  if [[ -z "${ADO_AUTH_HEADER:-}" ]]; then
    ado_resolve_auth || return 1
  fi

  local url="${ADO_ORG}/${ADO_PROJECT}/_apis/${path}"
  # Append api-version (handle existing query params)
  if [[ "$url" == *"?"* ]]; then
    url="${url}&api-version=${api_version}"
  else
    url="${url}?api-version=${api_version}"
  fi

  local -a curl_args=(
    -s -S --fail-with-body
    -H "$ADO_AUTH_HEADER"
    -H "Content-Type: application/json"
    -X "$method"
  )

  if [[ -n "$body" ]]; then
    curl_args+=(-d "$body")
  fi

  curl "${curl_args[@]}" "$url"
}

# Like ado_api but uses preview API version
ado_api_preview() {
  local method="$1" path="$2" body="${3:-}" preview="${4:-7.1-preview.1}"
  ado_api "$method" "$path" "$body" "$preview"
}

# Like ado_api but org-scoped (no project in URL): ${ADO_ORG}/_apis/${path}
ado_api_org() {
  local method="$1" path="$2" body="${3:-}" api_version="${4:-7.1}"

  if [[ -z "${ADO_AUTH_HEADER:-}" ]]; then
    ado_resolve_auth || return 1
  fi

  local url="${ADO_ORG}/_apis/${path}"
  if [[ "$url" == *"?"* ]]; then
    url="${url}&api-version=${api_version}"
  else
    url="${url}?api-version=${api_version}"
  fi

  local -a curl_args=(
    -s -S --fail-with-body
    -H "$ADO_AUTH_HEADER"
    -H "Content-Type: application/json"
    -X "$method"
  )

  if [[ -n "$body" ]]; then
    curl_args+=(-d "$body")
  fi

  curl "${curl_args[@]}" "$url"
}

# Like ado_api_org but targets feeds.dev.azure.com (Azure Artifacts host).
# The packaging/feeds API lives on a different hostname than the rest of ADO.
ado_api_feeds() {
  local method="$1" path="$2" body="${3:-}" api_version="${4:-7.1}"

  if [[ -z "${ADO_AUTH_HEADER:-}" ]]; then
    ado_resolve_auth || return 1
  fi

  # Replace dev.azure.com with feeds.dev.azure.com
  local feeds_org="${ADO_ORG/dev.azure.com/feeds.dev.azure.com}"
  local url="${feeds_org}/_apis/${path}"
  if [[ "$url" == *"?"* ]]; then
    url="${url}&api-version=${api_version}"
  else
    url="${url}?api-version=${api_version}"
  fi

  local -a curl_args=(
    -s -S --fail-with-body
    -H "$ADO_AUTH_HEADER"
    -H "Content-Type: application/json"
    -X "$method"
  )

  if [[ -n "$body" ]]; then
    curl_args+=(-d "$body")
  fi

  curl "${curl_args[@]}" "$url"
}

ado_get_project_id() {
  if [[ -n "$_ADO_PROJECT_ID" ]]; then
    echo "$_ADO_PROJECT_ID"
    return
  fi

  if [[ -z "${ADO_AUTH_HEADER:-}" ]]; then
    ado_resolve_auth || return 1
  fi

  _ADO_PROJECT_ID=$(curl -s -S --fail-with-body \
    -H "$ADO_AUTH_HEADER" \
    "${ADO_ORG}/_apis/projects/${ADO_PROJECT}?api-version=7.1" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
  echo "$_ADO_PROJECT_ID"
}
