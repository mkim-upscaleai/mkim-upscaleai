#!/usr/bin/env bash
# copy-image-to-switch.sh — Copy a SONiC image from this machine to a switch
#
# Usage:
#   ./copy-image-to-switch.sh -s <switch_ip> -i <image_path>
#   ./copy-image-to-switch.sh -s 192.168.220.5 -i downloaded-images/sonic.bin
#   ./copy-image-to-switch.sh -s 192.168.221.5 -i downloaded-images/sonic.bin   # via jump host
#
# Options:
#   -s <ip>     Switch IP address                           (required)
#   -i <path>   Local path to the image file               (default: downloaded-images/sonic-mellanox.bin)
#   -d <path>   Destination path on the switch             (default: /home/admin/)
#   -h          Show this help
#
# Jump host:
#   Switches in 192.168.221.x–192.168.223.x are reached via server9 (192.168.211.12).
#
# Credentials are loaded from environment variables, .env file, or interactive prompt
# via creds.sh. See .env.example for the template.

set -euo pipefail

# ── Credentials ──────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/creds.sh"

DEST_PATH="/home/admin/"
DEFAULT_IMAGE="${SCRIPT_DIR}/../downloaded-images/sonic-mellanox.bin"

# ── Args ──────────────────────────────────────────────────────────────────────
SWITCH_IP=""
IMAGE_PATH=""

usage() {
  sed -n '/^# Usage:/,/^$/p' "$0" | sed 's/^# \?//'
  exit 0
}

while getopts "s:i:d:h" opt; do
  case $opt in
    s) SWITCH_IP="$OPTARG" ;;
    i) IMAGE_PATH="$OPTARG" ;;
    d) DEST_PATH="$OPTARG" ;;
    h) usage ;;
    *) echo "Unknown option -$OPTARG" >&2; exit 1 ;;
  esac
done

# ── Validate ──────────────────────────────────────────────────────────────────
[ -z "$IMAGE_PATH" ] && IMAGE_PATH="$DEFAULT_IMAGE"

missing=()
[ -z "$SWITCH_IP" ] && missing+=("-s <switch_ip>")

if [ ${#missing[@]} -gt 0 ]; then
  echo "Error: missing required options: ${missing[*]}" >&2
  echo "Run with -h for usage." >&2
  exit 1
fi

if [ ! -f "$IMAGE_PATH" ]; then
  echo "Error: image file not found: ${IMAGE_PATH}" >&2
  exit 1
fi

if ! command -v sshpass &>/dev/null; then
  echo "Error: sshpass is required but not installed." >&2
  echo "  macOS:  brew install hudochenkov/sshpass/sshpass" >&2
  echo "  Linux:  apt-get install sshpass  (or equivalent)" >&2
  exit 1
fi

# ── Determine if jump host is needed ─────────────────────────────────────────
# Switches in 192.168.221.x–192.168.223.x require a hop through server9.
OCTET3=$(echo "$SWITCH_IP" | cut -d. -f3)
PREFIX=$(echo "$SWITCH_IP" | cut -d. -f1-2)

USE_JUMP=false
if [ "$PREFIX" = "192.168" ] && [ "$OCTET3" -ge 221 ] && [ "$OCTET3" -le 223 ]; then
  USE_JUMP=true
fi

# ── Common SSH options ────────────────────────────────────────────────────────
SSH_OPTS=(
  -o StrictHostKeyChecking=no
  -o UserKnownHostsFile=/dev/null
  -o ConnectTimeout=15
)

# ── Build SSH command for reuse ────────────────────────────────────────────────
ESCAPED_JUMP_PASS="$(printf '%q' "$JUMP_PASS")"
SSH_CMD=(sshpass -p "$SWITCH_PASS" ssh "${SSH_OPTS[@]}")
if $USE_JUMP; then
  SSH_CMD+=(-o "ProxyCommand sshpass -p ${ESCAPED_JUMP_PASS} ssh ${SSH_OPTS[*]} -W %h:%p ${JUMP_USER}@${JUMP_HOST}")
fi

FILE_SIZE=$(du -h "$IMAGE_PATH" | cut -f1)
REMOTE_FILE="${DEST_PATH%/}/$(basename "$IMAGE_PATH")"

# ── Copy ──────────────────────────────────────────────────────────────────────
echo "Copying image to switch..."
echo "  Image      : ${IMAGE_PATH}  (${FILE_SIZE})"
echo "  Switch     : ${SWITCH_USER}@${SWITCH_IP}:${REMOTE_FILE}"
if $USE_JUMP; then
  echo "  Jump host  : ${JUMP_USER}@${JUMP_HOST}"
fi
echo ""

if command -v pv &>/dev/null; then
  pv "$IMAGE_PATH" | "${SSH_CMD[@]}" "${SWITCH_USER}@${SWITCH_IP}" "cat > '${REMOTE_FILE}'"
else
  echo "  Transferring ${FILE_SIZE}... (install pv for a progress bar: brew install pv)"
  "${SSH_CMD[@]}" "${SWITCH_USER}@${SWITCH_IP}" "cat > '${REMOTE_FILE}'" < "$IMAGE_PATH" &
  SCP_PID=$!
  FILE_BYTES=$(wc -c < "$IMAGE_PATH" | tr -d ' ')
  while kill -0 "$SCP_PID" 2>/dev/null; do
    REMOTE_BYTES=$("${SSH_CMD[@]}" "${SWITCH_USER}@${SWITCH_IP}" "stat -c%s '${REMOTE_FILE}' 2>/dev/null || echo 0" 2>/dev/null || echo 0)
    if [ "$FILE_BYTES" -gt 0 ] && [ "$REMOTE_BYTES" -gt 0 ]; then
      PCT=$((REMOTE_BYTES * 100 / FILE_BYTES))
      TRANSFERRED=$(numfmt --to=iec "$REMOTE_BYTES" 2>/dev/null || echo "${REMOTE_BYTES} bytes")
      printf "\r  Progress: %s / %s  (%d%%)" "$TRANSFERRED" "$FILE_SIZE" "$PCT"
    fi
    sleep 5
  done
  printf "\r  Progress: %s / %s  (100%%)\n" "$FILE_SIZE" "$FILE_SIZE"
  wait "$SCP_PID"
fi

echo ""
echo "Done: $(basename "$IMAGE_PATH") (${FILE_SIZE}) copied to ${SWITCH_USER}@${SWITCH_IP}:${REMOTE_FILE}"
