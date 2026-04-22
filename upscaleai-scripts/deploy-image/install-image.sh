#!/usr/bin/env bash
# install-image.sh — Install a SONiC image on a switch via sonic-installer, then reboot
#
# Usage:
#   ./install-image.sh -s <switch_ip>
#   ./install-image.sh -s <switch_ip> -n <image_name>
#
# Options:
#   -s <ip>     Switch IP address                                   (required)
#   -n <name>   Image filename on the switch                        (default: sonic-mellanox.bin)
#   -h          Show this help
#
# Notes:
#   Assumes the image is already at /home/admin/<image_name> on the switch.
#   Use copy-image-to-switch.sh first if needed.
#   Switches in 192.168.221.x–192.168.223.x are reached via the server9 jump host.

set -euo pipefail

# ── Credentials ───────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/creds.sh"

SWITCH_IMAGE_DIR="/home/admin"

# ── Args ──────────────────────────────────────────────────────────────────────
SWITCH_IP=""
IMAGE_NAME="sonic-mellanox.bin"

usage() {
  sed -n '/^# Usage:/,/^$/p' "$0" | sed 's/^# \?//'
  exit 0
}

while getopts "s:n:h" opt; do
  case $opt in
    s) SWITCH_IP="$OPTARG" ;;
    n) IMAGE_NAME="$OPTARG" ;;
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

REMOTE_IMAGE="${SWITCH_IMAGE_DIR}/${IMAGE_NAME}"

echo "Installing image on switch..."
echo "  Image   : ${REMOTE_IMAGE}"
echo "  Switch  : ${SWITCH_USER}@${SWITCH_IP}"
if $USE_JUMP; then
  echo "  Via     : ${JUMP_USER}@${JUMP_HOST}"
fi
echo ""

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

echo "Step 1/2: Installing image..."
run_ssh "sudo sonic-installer install ${REMOTE_IMAGE} -y"

echo ""
echo "Step 2/2: Rebooting switch..."
run_ssh "sudo reboot" || true   # reboot drops the connection; ignore the SSH exit code

echo ""
echo "Done: ${IMAGE_NAME} installed on ${SWITCH_IP}. Switch is rebooting."
