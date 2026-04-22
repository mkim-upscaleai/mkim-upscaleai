#!/usr/bin/env bash
# creds.sh — Shared credential loader for deploy-image scripts
#
# Resolves each credential in order:
#   1. Already set in environment  (e.g. export SWITCH_PASS=...)
#   2. Defined in .env file        (upscaleai-scripts/.env)
#   3. Prompt the user interactively
#
# Source this file; do not execute it directly.
#   source "$(dirname "${BASH_SOURCE[0]}")/creds.sh"

_CREDS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_ENV_FILE="${_CREDS_DIR}/../.env"

# Load .env if it exists (won't overwrite vars already exported in the environment)
if [ -f "$_ENV_FILE" ]; then
  while IFS='=' read -r key value; do
    key=$(echo "$key" | xargs)
    [[ "$key" =~ ^# ]] && continue
    [[ -z "$key" ]] && continue
    value=$(echo "$value" | sed "s/^['\"]//;s/['\"]$//" | xargs)
    if [ -z "${!key:-}" ]; then
      export "$key=$value"
    fi
  done < "$_ENV_FILE"
fi

# Prompt for any credential still unset
_prompt_if_empty() {
  local var_name="$1" prompt_text="$2" is_secret="${3:-false}"
  if [ -z "${!var_name:-}" ]; then
    if [ "$is_secret" = "true" ]; then
      read -rsp "$prompt_text" "$var_name"
      echo ""
    else
      read -rp "$prompt_text" "$var_name"
    fi
    export "$var_name"
  fi
}

# Only prompt for passwords; non-secret fields use defaults silently
: "${JUMP_HOST:=192.168.211.12}"
export JUMP_HOST

: "${JUMP_USER:=casper}"
export JUMP_USER

: "${SWITCH_USER:=admin}"
export SWITCH_USER

if [ -z "${JUMP_PASS:-}" ]; then
  read -rsp "Jump host password (${JUMP_USER}@${JUMP_HOST}): " JUMP_PASS
  echo ""
  export JUMP_PASS
fi

if [ -z "${SWITCH_PASS:-}" ]; then
  read -rsp "Switch password (${SWITCH_USER}): " SWITCH_PASS
  echo ""
  export SWITCH_PASS
fi

unset -f _prompt_if_empty
unset _CREDS_DIR _ENV_FILE
