#!/usr/bin/env bash
# factory-reset-switch.sh — Reset a SONiC switch to factory defaults, preserving mgmt IP
#
# Usage:
#   ./factory-reset-switch.sh -s <switch_ip>
#
# Options:
#   -s <ip>     Switch IP address    (required)
#   -h          Show this help
#
# Steps:
#   1. Extract MGMT_INTERFACE and MGMT_PORT from current config_db.json
#   2. Backup config_db.json to config_db.json.bak-before-deploy
#   3. Run `sudo config-setup factory`
#   4. Restore saved mgmt fields into the new factory config
#   5. Run `sudo config reload -y -f`
#
# Notes:
#   If the switch has no static MGMT_INTERFACE (i.e. uses DHCP), step 4 is skipped.
#   Switches in 192.168.221.x–192.168.223.x are reached via the server9 jump host.

set -euo pipefail

# ── Credentials ───────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/creds.sh"

# ── Args ──────────────────────────────────────────────────────────────────────
SWITCH_IP=""

usage() {
  sed -n '/^# Usage:/,/^$/p' "$0" | sed 's/^# \?//'
  exit 0
}

while getopts "s:h" opt; do
  case $opt in
    s) SWITCH_IP="$OPTARG" ;;
    h) usage ;;
    *) echo "Unknown option -$OPTARG" >&2; exit 1 ;;
  esac
done

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

# ── Jump host detection (192.168.221.x–192.168.223.x) ────────────────────────
OCTET3=$(echo "$SWITCH_IP" | cut -d. -f3)
PREFIX=$(echo "$SWITCH_IP" | cut -d. -f1-2)

USE_JUMP=false
if [ "$PREFIX" = "192.168" ] && [ "$OCTET3" -ge 221 ] && [ "$OCTET3" -le 223 ]; then
  USE_JUMP=true
fi

SSH_OPTS=(
  -o StrictHostKeyChecking=no
  -o UserKnownHostsFile=/dev/null
  -o ConnectTimeout=15
)

ESCAPED_JUMP_PASS="$(printf '%q' "$JUMP_PASS")"

run_ssh() {
  local cmd="$1"
  if $USE_JUMP; then
    sshpass -p "$SWITCH_PASS" ssh \
      "${SSH_OPTS[@]}" \
      -o "ProxyCommand sshpass -p ${ESCAPED_JUMP_PASS} ssh ${SSH_OPTS[*]} -W %h:%p ${JUMP_USER}@${JUMP_HOST}" \
      "${SWITCH_USER}@${SWITCH_IP}" "$cmd"
  else
    sshpass -p "$SWITCH_PASS" ssh \
      "${SSH_OPTS[@]}" \
      "${SWITCH_USER}@${SWITCH_IP}" "$cmd"
  fi
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

# ── Step 1: Extract MGMT_INTERFACE and MGMT_PORT ─────────────────────────────
echo "  [1/5] Extracting management interface config..."

PY_EXTRACT='
import json
with open("/etc/sonic/config_db.json") as f:
    cfg = json.load(f)
mgmt = {}
if "MGMT_INTERFACE" in cfg:
    mgmt["MGMT_INTERFACE"] = cfg["MGMT_INTERFACE"]
if "MGMT_PORT" in cfg:
    mgmt["MGMT_PORT"] = cfg["MGMT_PORT"]
with open("/tmp/mgmt_backup.json", "w") as f:
    json.dump(mgmt, f, indent=4)
if mgmt:
    print("MGMT_SAVED")
    print(json.dumps(mgmt, indent=4))
else:
    print("MGMT_DHCP")
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

# ── Step 2: Backup current config ────────────────────────────────────────────
echo "  [2/5] Backing up config_db.json..."
run_ssh "sudo mv /etc/sonic/config_db.json /etc/sonic/config_db.json.bak-before-deploy"
echo "        Saved as /etc/sonic/config_db.json.bak-before-deploy"

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
echo "  [5/5] Reloading config (sudo config reload -y -f)..."
run_ssh "sudo config reload -y -f" || true

echo ""
echo "Factory reset complete on ${SWITCH_IP}. Config reload in progress."
