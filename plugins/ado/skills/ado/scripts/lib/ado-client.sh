#!/usr/bin/env bash
# Shared ADO REST API client library.
# Source this file; do not execute directly.
#
# Required env vars: ADO_ORG, ADO_PROJECT (ADO_ORG alone for org-scoped calls)
# Auth (checked in order): AZURE_DEVOPS_EXT_PAT, ADO_TOKEN, then an az login
# token minted for the Entra tenant that backs ADO_ORG.

set -euo pipefail

# Public Azure DevOps resource id, the same in every tenant.
ADO_RESOURCE_ID="499b84ac-1321-427f-aa17-267ca6975798"
_ADO_NIL_TENANT="00000000-0000-0000-0000-000000000000"
_ADO_GUID_RE='^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'

_ADO_PROJECT_ID=""
_ADO_TENANT_ID=""
_ADO_TENANT_ORG=""
_ADO_AUTH_SOURCE=""   # pat, token (supplied by the caller) or minted (from az login)
_ADO_AUTH_VAR=""      # environment variable the credential came from
_ADO_TOKEN=""         # bearer token for the token and minted sources

log_info()  { printf '[INFO]  %s\n' "$*" >&2; }
log_warn()  { printf '[WARN]  %s\n' "$*" >&2; }
log_error() { printf '[ERROR] %s\n' "$*" >&2; }

# Assert ADO_ORG is set and normalize it. Idempotent.
ado_require_org() {
  if [[ -z "${ADO_ORG:-}" ]]; then
    log_error "Missing: ADO_ORG. Export ADO_ORG (e.g. https://dev.azure.com/myorg)."
    return 1
  fi
  ADO_ORG="${ADO_ORG%/}"
  export ADO_ORG
}

# Assert ADO_ORG and ADO_PROJECT are set, and normalize ADO_ORG.
# Call this from the calling script AFTER arg parsing (so --help and usage
# errors can surface without requiring auth configuration). Idempotent.
ado_require_env() {
  local missing=""
  [[ -n "${ADO_ORG:-}" ]] || missing="ADO_ORG"
  [[ -n "${ADO_PROJECT:-}" ]] || missing="${missing:+$missing }ADO_PROJECT"
  if [[ -n "$missing" ]]; then
    log_error "Missing: ${missing}. Export ADO_ORG (e.g. https://dev.azure.com/myorg) and ADO_PROJECT, or wrap the command in: sequester env exec <org> -- bash -c 'export ADO_ORG=... ADO_PROJECT=...; <command>'"
    return 1
  fi
  ado_require_org
  export ADO_PROJECT
  if [ -n "${AZURE_DEVOPS_EXT_PAT:-}" ]; then
    export AZURE_DEVOPS_EXT_PAT
  fi
}

_ado_is_jwt() { [[ "$1" == eyJ*.*.* ]]; }

# Set _ADO_TENANT_ID to the Entra tenant that backs ADO_ORG, or to "" when
# the org reports none. ADO_TENANT_ID overrides the lookup. The result is
# cached per org for the rest of the shell, so call this outside $(...).
ado_discover_tenant() {
  if [[ -n "${ADO_TENANT_ID:-}" ]]; then
    if [[ ! "$ADO_TENANT_ID" =~ $_ADO_GUID_RE ]]; then
      log_error "ADO_TENANT_ID is not a tenant GUID: ${ADO_TENANT_ID}"
      return 1
    fi
    _ADO_TENANT_ID="$ADO_TENANT_ID"
    _ADO_TENANT_ORG="$ADO_ORG"
    return 0
  fi
  if [[ "$_ADO_TENANT_ORG" == "$ADO_ORG" ]]; then
    return 0
  fi
  _ADO_TENANT_ORG="$ADO_ORG"
  _ADO_TENANT_ID=""

  # The org names its tenant in a response header, even to anonymous callers.
  local headers value candidate
  if ! headers=$(curl -sS --max-time 20 -o /dev/null -D - "${ADO_ORG}/_apis/connectionData"); then
    log_warn "Could not look up the Entra tenant of ${ADO_ORG}. Minting for the az login default tenant."
    return 0
  fi
  value=$(printf '%s\n' "$headers" | tr -d '\r' \
    | awk -F': *' '!found && tolower($1) == "x-vss-resourcetenant" { print $2; found = 1 }')
  if [[ -z "$value" ]]; then
    log_warn "${ADO_ORG} did not report its Entra tenant. Minting for the az login default tenant."
    return 0
  fi
  # The value can list several tenants. The nil GUID marks an org that no
  # Entra tenant backs, which needs no --tenant.
  while IFS= read -r candidate; do
    candidate="${candidate//[[:space:]]/}"
    if [[ "$candidate" =~ $_ADO_GUID_RE && "$candidate" != "$_ADO_NIL_TENANT" ]]; then
      _ADO_TENANT_ID="$candidate"
      return 0
    fi
  done < <(printf '%s\n' "$value" | tr ',' '\n')
}

# Print one claim of the active bearer token, or nothing if it cannot be read.
_ado_token_claim() {
  printf '%s' "$_ADO_TOKEN" | python3 -c '
import base64, json, sys
try:
    seg = sys.stdin.read().strip().split(".")[1]
    seg += "=" * (-len(seg) % 4)
    print(json.loads(base64.urlsafe_b64decode(seg)).get(sys.argv[1], ""))
except Exception:
    pass
' "$1"
}

_ado_use_bearer() {
  _ADO_TOKEN="$1"
  _ADO_AUTH_SOURCE="$2"
  _ADO_AUTH_VAR="$3"
  ADO_AUTH_HEADER="Authorization: Bearer $1"
}

# Run az against the caller's az login. ado-exec.sh gives its command an
# empty AZURE_CONFIG_DIR and names the caller's config in ADO_AZ_CONFIG_DIR,
# so a script inside the wrapper still mints from the caller's account.
_ado_az() {
  if [[ -n "${ADO_AZ_CONFIG_DIR:-}" ]]; then
    AZURE_CONFIG_DIR="$ADO_AZ_CONFIG_DIR" az "$@"
  else
    az "$@"
  fi
}

_ado_explain_mint_failure() {
  local out="$1" tenant_flag="" home=""
  if [[ -n "$_ADO_TENANT_ID" ]]; then
    tenant_flag="--tenant ${_ADO_TENANT_ID} "
  fi
  case "$out" in
    *AADSTS700082*)
      home=$(_ado_az account show --query tenantId -o tsv 2>/dev/null) || home=""
      log_error "The az login session expired after going unused (AADSTS700082). Sign in again with: az login --tenant ${home:-<your subscription tenant>}"
      ;;
    *AADSTS50020*|*AADSTS90072*)
      log_error "Your az account is not a member or guest of tenant ${_ADO_TENANT_ID:-<unknown>}, which backs ${ADO_ORG}. Ask an org admin for access, or use a PAT."
      ;;
    *AADSTS50076*|*AADSTS50079*|*AADSTS50158*|*AADSTS65001*|*interaction_required*)
      log_error "The tenant behind ${ADO_ORG} requires an interactive sign-in. Run: az login ${tenant_flag}--allow-no-subscriptions --scope ${ADO_RESOURCE_ID}/.default"
      log_error "That login can switch your default subscription. Restore it afterwards with: az account set --subscription <your subscription>"
      ;;
    *"az login"*)
      log_error "The az CLI is not logged in. Run 'az login', set AZURE_DEVOPS_EXT_PAT, or use a sequester profile."
      ;;
    *)
      log_error "az account get-access-token failed."
      ;;
  esac
  printf '%s\n' "$out" >&2
}

# Mint an Azure DevOps access token from the az login session, for the
# tenant that backs ADO_ORG, and make it the active credential.
_ado_mint() {
  if ! command -v az >/dev/null 2>&1; then
    log_error "No credentials: AZURE_DEVOPS_EXT_PAT and ADO_TOKEN are unset and the az CLI is not installed. Set a PAT, use a sequester profile, or install az and run 'az login'."
    return 1
  fi
  ado_discover_tenant || return 1

  local -a args=(account get-access-token --resource "$ADO_RESOURCE_ID" --query accessToken -o tsv)
  if [[ -n "$_ADO_TENANT_ID" ]]; then
    args+=(--tenant "$_ADO_TENANT_ID")
  fi
  # stderr is kept to explain a failure. On success the token is the only
  # JWT-shaped line, whatever warnings az prints around it.
  local out line token=""
  if ! out=$(_ado_az "${args[@]}" 2>&1); then
    _ado_explain_mint_failure "$out"
    return 1
  fi
  while IFS= read -r line; do
    if _ado_is_jwt "$line"; then
      token="$line"
    fi
  done < <(printf '%s\n' "$out")
  if [[ -z "$token" ]]; then
    log_error "az account get-access-token returned no token."
    printf '%s\n' "$out" >&2
    return 1
  fi
  _ado_use_bearer "$token" minted ""
}

# Pick the credential and set ADO_AUTH_HEADER. Call once at the top level of
# a script: state set inside $(...) is lost when the subshell exits.
ado_resolve_auth() {
  local pat="${AZURE_DEVOPS_EXT_PAT:-}" token_source=token
  # ado-exec.sh marks tokens it minted, so they can be minted again on expiry.
  if [[ "${ADO_TOKEN_MINTED:-}" == 1 ]]; then
    token_source=minted
  fi
  if [[ -n "$pat" ]] && ! _ado_is_jwt "$pat"; then
    local b64
    b64=$(printf ':%s' "$pat" | base64 | tr -d '\n')
    ADO_AUTH_HEADER="Authorization: Basic ${b64}"
    _ADO_AUTH_SOURCE=pat
    _ADO_AUTH_VAR=AZURE_DEVOPS_EXT_PAT
    _ADO_TOKEN=""
  elif [[ -n "${ADO_TOKEN:-}" ]]; then
    _ado_use_bearer "$ADO_TOKEN" "$token_source" ADO_TOKEN
  elif [[ -n "$pat" ]]; then
    _ado_use_bearer "$pat" "$token_source" AZURE_DEVOPS_EXT_PAT
  else
    _ado_mint || return 1
    return 0
  fi
  if [[ "$_ADO_AUTH_SOURCE" == minted ]]; then
    _ado_refresh_if_expiring || return 1
  fi
}

# A minted token handed down by ado-exec.sh can be close to expiry. Minting
# again here, before any $(...) subshell, gives every request the new token.
_ado_refresh_if_expiring() {
  local exp
  exp=$(_ado_token_claim exp) || exp=""
  if [[ "$exp" =~ ^[0-9]+$ ]] && (( exp - $(date +%s) < 300 )); then
    log_info "The token in ${_ADO_AUTH_VAR} expires within 5 minutes or has expired. Minting a new one."
    _ado_mint
  fi
}

# Send one request. Sets _ADO_HTTP_CODE, _ADO_HTTP_REDIRECT, _ADO_HTTP_TYPE
# and _ADO_HTTP_BODY. Fails only when curl gets no HTTP response.
_ado_send() {
  local method="$1" url="$2" body="$3" resp meta
  local -a args=(-sS -K - -X "$method" -H "Content-Type: application/json"
    -w '\n%{http_code}\t%{redirect_url}\t%{content_type}')
  if [[ -n "$body" ]]; then
    args+=(-d "$body")
  fi
  # The credential goes in through stdin to keep it out of the process list.
  if ! resp=$(printf 'header = "%s"\n' "$ADO_AUTH_HEADER" | curl "${args[@]}" "$url"); then
    log_error "No response from ${method} ${url}"
    return 1
  fi
  meta="${resp##*$'\n'}"
  _ADO_HTTP_BODY="${resp%$'\n'*}"
  _ADO_HTTP_CODE="${meta%%$'\t'*}"
  meta="${meta#*$'\t'}"
  _ADO_HTTP_REDIRECT="${meta%%$'\t'*}"
  _ADO_HTTP_TYPE="${meta#*$'\t'}"
}

_ado_is_html() {
  local head="${_ADO_HTTP_BODY:0:100}"
  head="${head#"${head%%[![:space:]]*}"}"
  [[ "$_ADO_HTTP_TYPE" == text/html* || "$head" == "<!"[Dd][Oo][Cc]* || "$head" == "<"[Hh][Tt][Mm][Ll]* ]]
}

_ado_is_read() { [[ "$1" == GET || "$1" == HEAD ]]; }

# 401 or a redirect to sign-in means the credential was refused before the
# request ran. On reads, an HTML page or any redirect is taken the same way.
# A write gets no such guess, because an HTML error page can follow a write
# that went through.
_ado_is_auth_rejection() {
  case "$_ADO_HTTP_CODE" in
    401) return 0 ;;
    3??)
      if [[ "$_ADO_HTTP_REDIRECT" == *_signin* || "$_ADO_HTTP_REDIRECT" == *login.microsoftonline.com* ]]; then
        return 0
      fi
      ;;
  esac
  if _ado_is_read "$1"; then
    case "$_ADO_HTTP_CODE" in
      3??) return 0 ;;
      2??) _ado_is_html && return 0 ;;
    esac
  fi
  return 1
}

_ado_explain_rejection() {
  local why="HTTP ${_ADO_HTTP_CODE}"
  if [[ "$_ADO_HTTP_CODE" == 3?? ]]; then
    why="${why}, redirect to sign-in"
  fi
  case "$_ADO_AUTH_SOURCE" in
    pat)
      log_error "Azure DevOps rejected AZURE_DEVOPS_EXT_PAT (${why}). The PAT may be expired or revoked, belong to another org, or lack the scope for this call."
      ;;
    token)
      log_error "Azure DevOps rejected the access token in ${_ADO_AUTH_VAR} (${why}). Access tokens expire after about an hour. Unset ${_ADO_AUTH_VAR} to mint a new one from az login."
      ;;
    *)
      log_error "Azure DevOps rejected the token minted from az login (${why}) for ${ADO_ORG}."
      ;;
  esac
}


# 403 "has not been materialized": the org does not know the identity in the
# token, usually because the token was issued by another tenant.
_ado_explain_unknown_identity() {
  local token_tenant="" org_tenant
  if [[ -n "$_ADO_TOKEN" ]]; then
    token_tenant=$(_ado_token_claim tid) || token_tenant=""
  fi
  ado_discover_tenant || true
  org_tenant="${_ADO_TENANT_ID:-<unknown>}"
  if [[ -n "$token_tenant" && "$token_tenant" == "$_ADO_TENANT_ID" ]]; then
    log_error "${ADO_ORG} does not know your identity yet (\"has not been materialized\"). Sign in to the org once in a browser, or ask an org admin to add you."
    return 0
  fi
  log_error "The token was issued by tenant ${token_tenant:-<unknown>}, but ${ADO_ORG} is backed by tenant ${org_tenant} (\"has not been materialized\")."
  if [[ "$_ADO_AUTH_SOURCE" == token ]]; then
    log_error "Unset ${_ADO_AUTH_VAR} to mint a token for the org tenant from az login."
  else
    log_error "Set ADO_TENANT_ID to the org tenant and run again."
  fi
}

_ado_remint() {
  local previous="$_ADO_TOKEN" code="$_ADO_HTTP_CODE"
  _ado_mint || return 1
  if [[ "$_ADO_TOKEN" == "$previous" ]]; then
    log_error "Azure DevOps rejected the token (HTTP ${code}) and az returned the same one. Your account may lack access to ${ADO_ORG}."
    return 1
  fi
  log_info "Azure DevOps rejected the token (HTTP ${code}). Minted a new one and retrying."
}

# ado_request METHOD URL [BODY]
# Send a request to an absolute URL with the active credential and print the
# response body. A rejected token minted from az login is minted again and
# the request retried once.
ado_request() {
  local method="$1" url="$2" body="${3:-}" attempt
  if [[ -z "$_ADO_AUTH_SOURCE" ]]; then
    ado_resolve_auth || return 1
  fi
  for attempt in 1 2; do
    _ado_send "$method" "$url" "$body" || return 1
    if [[ "$_ADO_HTTP_CODE" == 2?? ]] && ! _ado_is_html; then
      printf '%s' "$_ADO_HTTP_BODY"
      return 0
    fi
    if _ado_is_auth_rejection "$method"; then
      if [[ "$attempt" == 1 && "$_ADO_AUTH_SOURCE" == minted ]]; then
        _ado_remint || return 1
        continue
      fi
      _ado_explain_rejection
      return 1
    fi
    if [[ "$_ADO_HTTP_CODE" == 403 && ( "$_ADO_HTTP_BODY" == *"has not been materialized"* || "$_ADO_HTTP_BODY" == *AadUserStateException* ) ]]; then
      _ado_explain_unknown_identity
      return 1
    fi
    log_error "HTTP ${_ADO_HTTP_CODE} from ${method} ${url}"
    if ! _ado_is_read "$method" && [[ "$_ADO_HTTP_CODE" == [23]?? ]]; then
      log_error "Not retried, because the change may have gone through. Check before running it again."
    fi
    if [[ -n "$_ADO_HTTP_BODY" ]]; then
      printf '%s\n' "$_ADO_HTTP_BODY" >&2
    fi
    return 1
  done
}

_ado_url() {
  local url="$1/_apis/$2"
  if [[ "$url" == *"?"* ]]; then
    printf '%s&api-version=%s' "$url" "$3"
  else
    printf '%s?api-version=%s' "$url" "$3"
  fi
}

# ado_api METHOD PATH [BODY] [API_VERSION]
# PATH is relative (e.g. "git/repositories") - base URL is built automatically.
ado_api() {
  local method="$1" path="$2" body="${3:-}" api_version="${4:-7.1}" url
  url=$(_ado_url "${ADO_ORG}/${ADO_PROJECT}" "$path" "$api_version")
  ado_request "$method" "$url" "$body"
}

# Like ado_api but uses preview API version
ado_api_preview() {
  local method="$1" path="$2" body="${3:-}" preview="${4:-7.1-preview.1}"
  ado_api "$method" "$path" "$body" "$preview"
}

# Like ado_api but org-scoped (no project in URL): ${ADO_ORG}/_apis/${path}
ado_api_org() {
  local method="$1" path="$2" body="${3:-}" api_version="${4:-7.1}" url
  url=$(_ado_url "$ADO_ORG" "$path" "$api_version")
  ado_request "$method" "$url" "$body"
}

# Like ado_api_org but targets feeds.dev.azure.com (Azure Artifacts host).
# The packaging/feeds API lives on a different hostname than the rest of ADO.
ado_api_feeds() {
  local method="$1" path="$2" body="${3:-}" api_version="${4:-7.1}" url
  url=$(_ado_url "${ADO_ORG/dev.azure.com/feeds.dev.azure.com}" "$path" "$api_version")
  ado_request "$method" "$url" "$body"
}

ado_get_project_id() {
  if [[ -z "$_ADO_PROJECT_ID" ]]; then
    local json
    json=$(ado_request GET "${ADO_ORG}/_apis/projects/${ADO_PROJECT}?api-version=7.1") || return 1
    _ADO_PROJECT_ID=$(printf '%s' "$json" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
  fi
  echo "$_ADO_PROJECT_ID"
}
