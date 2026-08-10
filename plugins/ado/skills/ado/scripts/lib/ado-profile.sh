# shellcheck shell=sh
# ADO profile selection. Source this file; do not execute directly.
#
# Credentials are exported once, in your terminal, BEFORE the session starts,
# and are inherited read-only. This file only reads that environment - it never
# exports or mutates session-level credentials. Two shapes are supported:
#
#   - Plain triple:   ADO_ORG / ADO_PROJECT / AZURE_DEVOPS_EXT_PAT
#   - Named profiles: one namespaced triple per alias <X>:
#                     <X>_ADO_ORG / <X>_ADO_PROJECT / <X>_ADO_PAT
#                     (e.g. WORK_ADO_ORG, PERSONAL_ADO_ORG). Any number may be
#                     present at once - the set of *_ADO_ORG vars is the registry.
#
# Public functions:
#   ado_profile [ALIAS]        Resolve and print the applicable alias. Prints
#                              nothing when the inherited plain triple should be
#                              used as-is; fails (lists profiles) when ambiguous.
#   ado_env     [ALIAS|auto]   Print `export ...` lines for the resolved profile.
#                              Bind a whole command block: eval "$(ado_env auto)"
#   ado_with    ALIAS|auto CMD Run one command string against a profile in a
#                              transient subshell (nothing persists past it).
#   ado_profiles               List discovered aliases with their org/project.
#
# Written to run identically under bash (the wrapper scripts) and zsh (the
# interactive shell): no bash-only indirection, and no reliance on unquoted
# word-splitting (zsh does not split unquoted parameters).

# Alias names that have a <NAME>_ADO_ORG in the environment, one per line.
_ado_alias_list() {
  env | sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)_ADO_ORG=.*/\1/p' | sort -u
}

# Value of <ALIAS>_ADO_<FIELD>, portable across bash and zsh.
_ado_var() { # $1=ALIAS $2=ORG|PROJECT|PAT
  eval "printf '%s' \"\${${1}_ADO_${2}:-}\""
}

# Single-quote a value so it survives eval.
_ado_q() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }

ado_profiles() {
  if [ -z "$(_ado_alias_list)" ]; then
    printf '  (no <ALIAS>_ADO_ORG variables in the environment)\n'
    return 0
  fi
  _ado_alias_list | while IFS= read -r _a; do
    printf '  %-10s %s  (project: %s)\n' "$_a" "$(_ado_var "$_a" ORG)" "$(_ado_var "$_a" PROJECT)"
  done
}

ado_profile() {
  # 1. Explicit alias arg (not "auto"), or $ADO_PROFILE.
  if [ -n "${1:-}" ] && [ "$1" != auto ]; then printf '%s\n' "$1"; return 0; fi
  if [ -n "${ADO_PROFILE:-}" ]; then printf '%s\n' "$ADO_PROFILE"; return 0; fi

  _al=$(_ado_alias_list)

  # 2. Match $PWD against a clone under dev.azure.com/<org>.
  _cwdorg=$(printf '%s' "${PWD:-}" | sed -n 's#.*/dev\.azure\.com/\([^/]*\).*#\1#p')
  if [ -n "$_cwdorg" ]; then
    _match=$(printf '%s\n' "$_al" | while IFS= read -r _a; do
      [ -n "$_a" ] || continue
      _url=$(_ado_var "$_a" ORG)
      if [ "${_url##*/}" = "$_cwdorg" ]; then printf '%s' "$_a"; break; fi
    done)
    if [ -n "$_match" ]; then printf '%s\n' "$_match"; return 0; fi
  fi

  # 3. Exactly one alias defined.
  _n=$(printf '%s\n' "$_al" | grep -c . || true)
  if [ "$_n" -eq 1 ]; then printf '%s\n' "$_al"; return 0; fi

  # 4. Plain triple already inherited -> use it as-is (print nothing).
  if [ -n "${ADO_ORG:-}" ] && [ -n "${ADO_PROJECT:-}" ] && [ -n "${AZURE_DEVOPS_EXT_PAT:-}" ]; then
    return 0
  fi

  # 5. Ambiguous or nothing loaded -> explain on stderr and fail.
  if [ "$_n" -gt 1 ]; then
    printf 'ado: %s ADO profiles are loaded and the working directory does not identify one.\n' "$_n" >&2
    # shellcheck disable=SC2016  # the $(...) is literal help text, not meant to expand
    printf 'ado: name one (ado_with <ALIAS> ..., eval "$(ado_env <ALIAS>)") or export ADO_PROFILE. Available:\n' >&2
  else
    printf 'ado: no ADO credentials found. Export the plain ADO_ORG/ADO_PROJECT/AZURE_DEVOPS_EXT_PAT,\n' >&2
    printf 'ado: export a namespaced <ALIAS>_ADO_ORG/PROJECT/PAT set, or read a sequester profile\n' >&2
    printf 'ado: per command (sequester env exec <PROFILE> -- ...).\n' >&2
  fi
  ado_profiles >&2
  return 1
}

# Print `export` lines for the resolved profile. Empty output (success) means
# the inherited plain triple is already correct and should be used as-is.
ado_env() {
  _a=$(ado_profile "${1:-}") || return 1
  [ -n "$_a" ] || return 0
  _o=$(_ado_var "$_a" ORG); _p=$(_ado_var "$_a" PROJECT); _t=$(_ado_var "$_a" PAT)
  if [ -z "$_o" ] || [ -z "$_p" ] || [ -z "$_t" ]; then
    printf 'ado: profile %s is missing one of %s_ADO_ORG / %s_ADO_PROJECT / %s_ADO_PAT\n' "$_a" "$_a" "$_a" "$_a" >&2
    return 1
  fi
  printf 'export ADO_ORG=%s ADO_PROJECT=%s AZURE_DEVOPS_EXT_PAT=%s\n' \
    "$(_ado_q "$_o")" "$(_ado_q "$_p")" "$(_ado_q "$_t")"
}

# Run one command STRING against a profile, bound only for that command.
#   ado_with OP 'az repos pr list --org "$ADO_ORG" -p "$ADO_PROJECT" --detect false'
# Pass the command single-quoted so $ADO_ORG etc. expand inside the subshell.
ado_with() {
  _a="${1:-}"; shift 2>/dev/null || true
  _exports=$(ado_env "$_a") || return 1
  ( eval "$_exports"; eval "$*" )
}
