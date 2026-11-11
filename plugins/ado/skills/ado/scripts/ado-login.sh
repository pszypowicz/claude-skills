#!/usr/bin/env bash
# shellcheck source-path=SCRIPTDIR
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/ado-client.sh
source "$SCRIPT_DIR/lib/ado-client.sh"

usage() {
  cat <<'EOF'
Usage: ado-login.sh [--org URL | --tenant ID] [--device-code | --browser]
                    [--timeout SECONDS] [--interval SECONDS]

Sign in with az login to the Entra tenant behind an Azure DevOps org, once
for every session on this machine that shares the az config, and exit as
soon as a token for Azure DevOps can be minted.

The first session that needs the tenant runs az login and prints its
sign-in message, such as the device code. A session that finds that login
in progress prints the same message and starts no login of its own. Every
session checks for a token and exits 0 once one is available, whichever
login provided it. The device code flow is used over SSH and the browser
flow otherwise. When the login moves the default subscription, the previous
default is restored.

Flags:
  --org URL            Organization whose tenant to sign in to (default: $ADO_ORG)
  --tenant ID          Tenant to sign in to, skipping the lookup (default: $ADO_TENANT_ID)
  --device-code        Use the device code flow, also outside SSH
  --browser            Use the browser flow, also over SSH
  --timeout SECONDS    Give up after this many seconds (default: 900, the device code lifetime)
  --interval SECONDS   Time between token checks (default: 5)
  -h, --help           Show this help

Exit status: 0 once a token can be minted, 1 when the sign-in failed or
timed out, 2 for a usage error.

Examples:
  ado-login.sh --org https://dev.azure.com/myorg
  ado-login.sh --tenant 11111111-2222-3333-4444-555555555555 --device-code
EOF
}

usage_error() { log_error "$1"; usage >&2; exit 2; }
missing_value() { usage_error "$1 requires a value"; }

ORG=""
TENANT=""
MODE=""
TIMEOUT=900
INTERVAL=5

while [[ $# -gt 0 ]]; do
  case "$1" in
    --org)         [[ -n "${2-}" ]] || missing_value "$1"; ORG="$2"; shift 2 ;;
    --tenant)      [[ -n "${2-}" ]] || missing_value "$1"; TENANT="$2"; shift 2 ;;
    --device-code) MODE=device; shift ;;
    --browser)     MODE=browser; shift ;;
    --timeout)     [[ -n "${2-}" ]] || missing_value "$1"; TIMEOUT="$2"; shift 2 ;;
    --interval)    [[ -n "${2-}" ]] || missing_value "$1"; INTERVAL="$2"; shift 2 ;;
    -h|--help)     usage; exit 0 ;;
    *)             usage_error "Unknown flag: $1" ;;
  esac
done

[[ "$TIMEOUT" =~ ^[0-9]+$ ]] || usage_error "--timeout takes whole seconds, got: $TIMEOUT"
[[ "$INTERVAL" =~ ^[0-9]+([.][0-9]+)?$ ]] || usage_error "--interval takes seconds, got: $INTERVAL"

if [[ -n "$TENANT" || -n "${ADO_TENANT_ID:-}" ]]; then
  tenant="${TENANT:-$ADO_TENANT_ID}"
  [[ "$tenant" =~ $_ADO_GUID_RE ]] || usage_error "Not a tenant GUID: $tenant"
else
  [[ -z "$ORG" ]] || ADO_ORG="$ORG"
  [[ -n "${ADO_ORG:-}" ]] || usage_error "Name the org with --org or ADO_ORG, or the tenant with --tenant"
  ado_require_org
  ado_discover_tenant || exit 1
  tenant="$_ADO_TENANT_ID"
  if [[ -z "$tenant" ]]; then
    log_error "Could not find the Entra tenant behind ${ADO_ORG}. Pass it with --tenant."
    exit 1
  fi
fi

case "$MODE" in
  device)  device=1 ;;
  browser) device=0 ;;
  *)       if ado_over_ssh; then device=1; else device=0; fi ;;
esac

# The lock sits in the az config it guards, so exactly the sessions that
# share one token cache coordinate. ado-exec.sh names the caller's config in
# ADO_AZ_CONFIG_DIR while its command runs against an empty one.
lock_root="${ADO_AZ_CONFIG_DIR:-${AZURE_CONFIG_DIR:-$HOME/.azure}}/ado-login"
lock="$lock_root/$tenant"

owner=0
child_pid=""
prev_sub=""
shown=""

cleanup() {
  if [[ "$owner" == 1 ]]; then
    if [[ -n "$child_pid" ]] && kill -0 "$child_pid" 2>/dev/null; then
      kill "$child_pid" 2>/dev/null || true
      wait "$child_pid" 2>/dev/null || true
    fi
    rm -rf "$lock"
  fi
}
trap cleanup EXIT
trap 'exit 1' INT TERM HUP

token_ready() {
  local token
  token=$(_ado_az account get-access-token --resource "$ADO_RESOURCE_ID" --tenant "$tenant" \
    --query accessToken -o tsv 2>/dev/null) || return 1
  [[ -n "$token" ]]
}

# The message file holds the owner's az login output. Only a complete last
# line is shown, so a half-written device code never reaches the user.
message_complete() {
  local text
  [[ -s "$lock/message" ]] || return 1
  text=$(cat "$lock/message" 2>/dev/null; printf .)
  text="${text%.}"
  [[ "$text" == *$'\n' ]]
}

show_message() {
  local text
  message_complete || return 0
  text=$(cat "$lock/message" 2>/dev/null) || return 0
  [[ "$text" != "$shown" ]] || return 0
  shown="$text"
  if [[ "$owner" == 1 ]]; then
    printf '%s\n' "$text"
  else
    printf 'ado-login: another session is already signing in to tenant %s. Use its sign-in:\n%s\n' "$tenant" "$text"
  fi
}

# A lock whose owner process is gone is stale. An owner writes its pid right
# after creating the lock, so a lock without a pid counts as stale only once
# it is over a minute old.
lock_stale() {
  local pid=""
  if [[ -f "$lock/pid" ]]; then
    pid=$(cat "$lock/pid" 2>/dev/null) || pid=""
  fi
  if [[ -n "$pid" ]]; then
    if kill -0 "$pid" 2>/dev/null; then
      return 1
    fi
    return 0
  else
    [[ -n "$(find "$lock" -maxdepth 0 -mmin +1 2>/dev/null)" ]]
  fi
}

take_lock() {
  mkdir -p "$lock_root" || return 1
  mkdir "$lock" 2>/dev/null || return 1
  echo "$$" >"$lock/pid"
  owner=1
}

start_login() {
  local -a args=(login --tenant "$tenant" --allow-no-subscriptions --scope "${ADO_RESOURCE_ID}/.default" --output none)
  local tries=0
  if [[ "$device" == 1 ]]; then
    args+=(--use-device-code)
  fi
  prev_sub=$(_ado_az account show --query id -o tsv 2>/dev/null) || prev_sub=""
  # exec makes the background pid the az process itself, so cleanup stops
  # the login and leaves no az waiting on a code nobody will enter.
  (
    if [[ -n "${ADO_AZ_CONFIG_DIR:-}" ]]; then
      export AZURE_CONFIG_DIR="$ADO_AZ_CONFIG_DIR"
    fi
    exec az "${args[@]}"
  ) </dev/null >/dev/null 2>"$lock/message" &
  child_pid=$!
  # Print the sign-in message as soon as az writes it, so the code reaches
  # the user before the first token check.
  while ((tries < 100)); do
    message_complete && break
    kill -0 "$child_pid" 2>/dev/null || break
    sleep 0.1
    tries=$((tries + 1))
  done
  show_message
}

restore_default() {
  local now
  [[ -n "$prev_sub" ]] || return 0
  now=$(_ado_az account show --query id -o tsv 2>/dev/null) || now=""
  [[ -n "$now" && "$now" != "$prev_sub" ]] || return 0
  if _ado_az account set --subscription "$prev_sub" >/dev/null 2>&1; then
    echo "ado-login: restored the default subscription ${prev_sub}."
  else
    log_warn "The login moved the default subscription to ${now}, and ${prev_sub} could not be restored. Run: az account set --subscription <your subscription>"
  fi
}

signed_in() {
  if [[ "$owner" == 1 ]]; then
    restore_default
  fi
  echo "ado-login: signed in to tenant ${tenant}."
  exit 0
}

if token_ready; then
  echo "ado-login: already signed in to tenant ${tenant}."
  exit 0
fi

deadline=$((SECONDS + TIMEOUT))
while :; do
  if token_ready; then
    signed_in
  fi

  if [[ "$owner" == 1 ]]; then
    show_message
    if ! kill -0 "$child_pid" 2>/dev/null; then
      status=0
      wait "$child_pid" || status=$?
      child_pid=""
      if [[ "$status" -ne 0 ]]; then
        log_error "az login failed (exit ${status}):"
        cat "$lock/message" >&2 2>/dev/null || true
        exit 1
      fi
      if token_ready; then
        signed_in
      fi
      log_error "az login finished, but no token for tenant ${tenant} can be minted:"
      _ado_az account get-access-token --resource "$ADO_RESOURCE_ID" --tenant "$tenant" 2>&1 >/dev/null | tail -3 >&2 || true
      exit 1
    fi
  elif [[ -d "$lock" ]]; then
    if lock_stale; then
      rm -rf "$lock"
      continue
    fi
    show_message
  elif take_lock; then
    start_login
    continue
  fi

  if ((SECONDS >= deadline)); then
    log_error "Timed out after ${TIMEOUT}s waiting for a sign-in to tenant ${tenant}."
    exit 1
  fi
  sleep "$INTERVAL"
done
