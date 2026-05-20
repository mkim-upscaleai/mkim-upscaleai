#!/usr/bin/env bash
# factory-reset-switch.sh — Reset a SONiC switch to factory defaults, preserving mgmt IP
#
# Usage:
#   ./factory-reset-switch.sh -s <switch_ip>
#
# Options:
#   -s <ip>     Switch IP address    (required)
#   -u <user>   SSH username         (default: from $SWITCH_USER or "admin")
#   -p <pass>   SSH password         (default: from $SWITCH_PASS or prompt)
#   -h          Show this help
#
# Credentials:
#   Resolved in order: CLI flags > environment variables > ~/.env file > prompt.
#
# Steps:
#   1. Save MGMT_INTERFACE / MGMT_PORT / MGMT_VRF_CONFIG from running CONFIG_DB
#      (via ``sonic-cfggen -d --print-data`` — sees golden_config_db.json merged
#      with any runtime overrides, unlike reading /etc/sonic/config_db.json)
#   2. mv /etc/sonic/config_db.json -> /etc/sonic/config_db.json.bk
#      (single fixed-name backup; overwritten on each run.
#       Skipped if config_db.json does not exist on the switch.)
#   3. Run `sudo config-setup factory`
#   4. Merge the saved mgmt fields back into the new /etc/sonic/config_db.json
#   5. Run `sudo config reload -y -f`

set -euo pipefail

# ── Credentials ───────────────────────────────────────────────────────────────
# Load ~/.env if it exists (won't overwrite vars already in the environment)
_ENV_FILE="${HOME}/.env"
if [ -f "$_ENV_FILE" ]; then
  while IFS='=' read -r key value; do
    key=$(echo "$key" | xargs)
    [[ "$key" =~ ^# ]] && continue
    [[ -z "$key" ]] && continue
    value=$(echo "$value" | sed "s/^['\"]//;s/['\"]$//" | xargs)
    if [ -z "${!key:-}" ]; then
      export "$key=$value"
    fi
  done <"$_ENV_FILE"
fi

# ── Args ──────────────────────────────────────────────────────────────────────
SWITCH_IP=""
CLI_USER=""
CLI_PASS=""

usage() {
  sed -n '/^# Usage:/,/^$/p' "$0" | sed 's/^# \?//'
  exit 0
}

while getopts "s:u:p:h" opt; do
  case $opt in
  s) SWITCH_IP="$OPTARG" ;;
  u) CLI_USER="$OPTARG" ;;
  p) CLI_PASS="$OPTARG" ;;
  h) usage ;;
  *)
    echo "Unknown option -$OPTARG" >&2
    exit 1
    ;;
  esac
done

SWITCH_USER="${CLI_USER:-${SWITCH_USER:-admin}}"

if [ -n "$CLI_PASS" ]; then
  SWITCH_PASS="$CLI_PASS"
elif [ -z "${SWITCH_PASS:-}" ]; then
  read -rsp "Switch password (${SWITCH_USER}@${SWITCH_IP:-<ip>}): " SWITCH_PASS
  echo ""
fi

# ── Validate ──────────────────────────────────────────────────────────────────
if [ -z "$SWITCH_IP" ]; then
  echo "Error: -s <switch_ip> is required." >&2
  echo "Run with -h for usage." >&2
  exit 1
fi

if ! command -v sshpass &>/dev/null; then
  echo "Error: sshpass is required but not installed." >&2
  echo "  macOS:  brew install hudochenkov/sshpass/sshpass" >&2
  echo "  Linux:  apt-get install sshpass  (or equivalent)" >&2
  exit 1
fi

SSH_OPTS=(
  -o ConnectTimeout=15
)

run_ssh() {
  local cmd="$1"
  SSHPASS="$SWITCH_PASS" sshpass -e ssh \
    "${SSH_OPTS[@]}" \
    "${SWITCH_USER}@${SWITCH_IP}" "$cmd"
}

# Runs a python3 script on the switch via base64 encoding (avoids quoting issues)
run_remote_python() {
  local script="$1"
  local use_sudo="${2:-false}"
  local encoded
  encoded=$(printf '%s' "$script" | base64 | tr -d '\n')
  if [ "$use_sudo" = "true" ]; then
    run_ssh "echo '${encoded}' | base64 -d | sudo python3"
  else
    run_ssh "echo '${encoded}' | base64 -d | python3"
  fi
}

echo "Factory-resetting switch ${SWITCH_IP}..."
echo ""

BACKUP_PATH="/etc/sonic/config_db.json.bk"
BACKUP_TS="$(date +%Y%m%d-%H%M%S)"

# ── Step 1: Save mgmt config from running CONFIG_DB ──────────────────────────
# We read from the live CONFIG_DB (sonic-cfggen -d) instead of /etc/sonic/config_db.json
# because the on-disk file may not contain the full mgmt config — golden_config_db.json
# entries and runtime overrides only show up in the merged running view.
echo "  [1/5] Saving management interface config from running CONFIG_DB..."

PY_EXTRACT='
import json, subprocess, sys
try:
    out = subprocess.check_output(
        ["sonic-cfggen", "-d", "--print-data"],
        stderr=subprocess.PIPE, text=True,
    )
    cfg = json.loads(out)
except Exception as e:
    print(f"MGMT_ERROR:{e}", file=sys.stderr)
    sys.exit(2)

# Tables we preserve across factory reset. Add more here if your setup needs them.
MGMT_TABLES = ("MGMT_INTERFACE", "MGMT_PORT", "MGMT_VRF_CONFIG")
mgmt = {t: cfg[t] for t in MGMT_TABLES if t in cfg and cfg[t]}

if mgmt:
    print("MGMT_SAVED")
    print(json.dumps(mgmt))
    with open("/tmp/mgmt_backup.json", "w") as f:
        json.dump(mgmt, f, indent=4)
    print("MGMT_SAVED_TO_FILE")
else:
    print("MGMT_NONE")
'

EXTRACT_OUTPUT=$(run_remote_python "$PY_EXTRACT")
HAS_STATIC_MGMT=false
if echo "$EXTRACT_OUTPUT" | grep -q "MGMT_SAVED"; then
  HAS_STATIC_MGMT=true
  echo "        Static mgmt config found — will restore after factory reset."
  echo "$EXTRACT_OUTPUT" | tail -n +2 | sed 's/^/        /'
else
  echo "        No static mgmt config (DHCP) — nothing to restore."
fi

# ── Step 2: Backup current config (if present) ───────────────────────────────
# /etc/sonic/config_db.json may legitimately be absent (e.g. switch booted purely
# from golden_config_db.json or a fresh image with no persisted config). In that
# case there is nothing to back up — skip rather than aborting the reset.
echo "  [2/5] Backing up config_db.json..."
BACKUP_OUTPUT=$(run_ssh "if [ -f /etc/sonic/config_db.json ]; then sudo mv /etc/sonic/config_db.json ${BACKUP_PATH}-${BACKUP_TS} && echo BACKED_UP; else echo NO_CONFIG_DB; fi")
if echo "$BACKUP_OUTPUT" | grep -q "BACKED_UP"; then
  echo "        Saved as ${BACKUP_PATH}-${BACKUP_TS}"
else
  echo "        No /etc/sonic/config_db.json on switch — skipping backup."
fi

# ── Step 3: Factory reset ─────────────────────────────────────────────────────
echo "  [3/5] Running config-setup factory..."
run_ssh "sudo config-setup factory"
echo "        Factory config generated."

# ── Step 4: Restore mgmt fields ──────────────────────────────────────────────
if $HAS_STATIC_MGMT; then
  echo "  [4/5] Restoring management interface config..."

PY_MERGE='
import json
with open("/etc/sonic/config_db.json") as f:
    cfg = json.load(f)
with open("/tmp/mgmt_backup.json") as f:
    mgmt = json.load(f)
cfg.update(mgmt)
with open("/etc/sonic/config_db.json", "w") as f:
    json.dump(cfg, f, indent=4, sort_keys=True)
print("MGMT_RESTORED")
'

  MERGE_OUTPUT=$(run_remote_python "$PY_MERGE" true)
  if echo "$MERGE_OUTPUT" | grep -q "MGMT_RESTORED"; then
    echo "        Management config restored to config_db.json."
  else
    echo "        Warning: could not confirm mgmt restore." >&2
    echo "        Output: ${MERGE_OUTPUT}" >&2
  fi
else
  echo "  [4/5] Skipped — switch uses DHCP."
fi


# ── Step 5: Config reload ─────────────────────────────────────────────────────
echo "  [5/5] Starting config reload..."
if ! run_ssh "nohup sudo config reload -y -f >/tmp/config-reload.log 2>&1 </dev/null &"; then
  echo "Error: failed to start config reload." >&2
  exit 1
fi

echo ""
echo "Factory reset requested on ${SWITCH_IP}. Config reload started."
