#!/usr/bin/env bash
# deploy-switch.sh — Full pipeline: download → copy → install → factory reset
#
# Usage:
#   ./deploy-switch.sh -s <switch_ip>
#   ./deploy-switch.sh -s <switch_ip> -t <tag>
#   ./deploy-switch.sh -s <switch_ip> -p <platform>
#   ./deploy-switch.sh -s <switch_ip> -b <build_id>
#   ./deploy-switch.sh -s <switch_ip> -i <image.bin>
#
# Options:
#   -s <ip>       Switch IP address                                    (required)
#   -t <tag>      Build tag to download: prod | gating | upload | dev  (default: prod)
#   -p <plat>     Platform to download: mellanox | vs                  (default: mellanox)
#   -b <id>       Download a specific build by ID from the dashboard
#   -i <path>     Use a local .bin image instead of downloading        (skips download)
#   -f            Force re-download even if image already exists
#   -h            Show this help
#
# Examples:
#   ./deploy-switch.sh -s 10.9.100.61                          # latest prod mellanox
#   ./deploy-switch.sh -s 10.9.100.61 -t gating               # latest gating mellanox
#   ./deploy-switch.sh -s 10.9.100.61 -p vs                   # latest prod vs
#   ./deploy-switch.sh -s 10.9.100.61 -b 449                  # specific build by ID
#   ./deploy-switch.sh -s 10.9.100.61 -i downloaded-images/sonic-mellanox.bin  # use local file

set -euo pipefail

SECONDS=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "${SCRIPT_DIR}/deploy-image/check-deps.sh"
check_deps "curl python3 sshpass" "pv"

SWITCH_IP=""
TAG="prod"
PLATFORM="mellanox"
BUILD_ID=""
LOCAL_IMAGE=""
FORCE_DL=""

usage() {
  sed -n '/^# Usage:/,/^$/p' "$0" | sed 's/^# \?//'
  exit 0
}

while getopts "s:t:p:b:i:fh" opt; do
  case $opt in
    s) SWITCH_IP="$OPTARG" ;;
    t) TAG="$OPTARG" ;;
    p) PLATFORM="$OPTARG" ;;
    b) BUILD_ID="$OPTARG" ;;
    i) LOCAL_IMAGE="$OPTARG" ;;
    f) FORCE_DL="-f" ;;
    h) usage ;;
    *) echo "Unknown option -$OPTARG" >&2; exit 1 ;;
  esac
done

if [ -z "$SWITCH_IP" ]; then
  echo "Error: -s <switch_ip> is required." >&2
  echo "Run with -h for usage." >&2
  exit 1
fi

if ! [[ "$SWITCH_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; then
  echo "Error: invalid IPv4 address: ${SWITCH_IP}" >&2
  exit 1
fi

if [ -n "$LOCAL_IMAGE" ] && [ ! -f "$LOCAL_IMAGE" ]; then
  echo "Error: image file not found: ${LOCAL_IMAGE}" >&2
  exit 1
fi

# ── Credentials & SSH setup for wait_for_switch ──────────────────────────────
source "${SCRIPT_DIR}/deploy-image/creds.sh"

OCTET3=$(echo "$SWITCH_IP" | cut -d. -f3)
PREFIX=$(echo "$SWITCH_IP" | cut -d. -f1-2)
USE_JUMP=false
if [ "$PREFIX" = "192.168" ] && [ "$OCTET3" -ge 221 ] && [ "$OCTET3" -le 223 ]; then
  USE_JUMP=true
fi

SSH_OPTS=(
  -o StrictHostKeyChecking=no
  -o UserKnownHostsFile=/dev/null
  -o ConnectTimeout=10
)

# ── Helpers ───────────────────────────────────────────────────────────────────
format_elapsed() {
  local secs=$1
  if [ "$secs" -ge 60 ]; then
    printf '%dm %ds' $((secs / 60)) $((secs % 60))
  else
    printf '%ds' "$secs"
  fi
}

step_banner() {
  echo ""
  echo "[ $1 ] $2  (elapsed: $(format_elapsed $SECONDS))"
  echo ""
}

ESCAPED_JUMP_PASS="$(printf '%q' "$JUMP_PASS")"

ssh_check() {
  if $USE_JUMP; then
    sshpass -p "$SWITCH_PASS" ssh \
      "${SSH_OPTS[@]}" \
      -o "ProxyCommand sshpass -p ${ESCAPED_JUMP_PASS} ssh ${SSH_OPTS[*]} -W %h:%p ${JUMP_USER}@${JUMP_HOST}" \
      "${SWITCH_USER}@${SWITCH_IP}" "echo ok" 2>/dev/null
  else
    sshpass -p "$SWITCH_PASS" ssh \
      "${SSH_OPTS[@]}" \
      "${SWITCH_USER}@${SWITCH_IP}" "echo ok" 2>/dev/null
  fi
}

ssh_run() {
  if $USE_JUMP; then
    sshpass -p "$SWITCH_PASS" ssh \
      "${SSH_OPTS[@]}" \
      -o "ProxyCommand sshpass -p ${ESCAPED_JUMP_PASS} ssh ${SSH_OPTS[*]} -W %h:%p ${JUMP_USER}@${JUMP_HOST}" \
      "${SWITCH_USER}@${SWITCH_IP}" "$1"
  else
    sshpass -p "$SWITCH_PASS" ssh \
      "${SSH_OPTS[@]}" \
      "${SWITCH_USER}@${SWITCH_IP}" "$1"
  fi
}

wait_for_switch_down() {
  local timeout="${1:-120}"
  local interval=5
  local waited=0
  echo "  Waiting for ${SWITCH_IP} to go down (timeout: ${timeout}s)..."
  while [ "$waited" -lt "$timeout" ]; do
    if ! ssh_check &>/dev/null; then
      echo "  Switch is unreachable after ${waited}s."
      return 0
    fi
    sleep "$interval"
    waited=$((waited + interval))
  done
  echo "Warning: switch did not go down within ${timeout}s; proceeding anyway." >&2
  return 0
}

wait_for_switch() {
  local timeout="${1:-600}"
  local interval=15
  local waited=0
  echo "  Waiting for ${SWITCH_IP} to become reachable (timeout: ${timeout}s)..."
  while [ "$waited" -lt "$timeout" ]; do
    if ssh_check &>/dev/null; then
      echo "  Switch is back online after ${waited}s.  (total elapsed: $(format_elapsed $SECONDS))"
      return 0
    fi
    sleep "$interval"
    waited=$((waited + interval))
    echo "  Still waiting... ${waited}s"
  done
  echo "Error: ${SWITCH_IP} did not come back within ${timeout}s." >&2
  return 1
}

# ══════════════════════════════════════════════════════════════════════════════
if [ -n "$LOCAL_IMAGE" ]; then
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "  deploy-switch  →  ${SWITCH_IP}  [local: $(basename "$LOCAL_IMAGE")]"
  echo "╚══════════════════════════════════════════════════════════════╝"
elif [ -n "$BUILD_ID" ]; then
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "  deploy-switch  →  ${SWITCH_IP}  [build: #${BUILD_ID}]"
  echo "╚══════════════════════════════════════════════════════════════╝"
else
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "  deploy-switch  →  ${SWITCH_IP}  [tag: ${TAG}, platform: ${PLATFORM}]"
  echo "╚══════════════════════════════════════════════════════════════╝"
fi

# ── Step 1: Download (or use local image) ─────────────────────────────────────
if [ -n "$LOCAL_IMAGE" ]; then
  step_banner "1/6" "Using local image: ${LOCAL_IMAGE}"
  IMAGE_PATH="$LOCAL_IMAGE"
else
  if [ -n "$BUILD_ID" ]; then
    step_banner "1/6" "Downloading build #${BUILD_ID}..."
    DOWNLOAD_OUTPUT=$("${SCRIPT_DIR}/deploy-image/download-sonic.sh" -i "$BUILD_ID" $FORCE_DL)
  else
    step_banner "1/6" "Downloading image (tag: ${TAG}, platform: ${PLATFORM})..."
    DOWNLOAD_OUTPUT=$("${SCRIPT_DIR}/deploy-image/download-sonic.sh" -t "$TAG" -p "$PLATFORM" $FORCE_DL)
  fi
  echo "$DOWNLOAD_OUTPUT"

  IMAGE_PATH=$(echo "$DOWNLOAD_OUTPUT" | awk '/Output[[:space:]]*:/ { print $NF }')

  if [ -z "$IMAGE_PATH" ] || [ ! -f "$IMAGE_PATH" ]; then
    echo "Error: could not determine downloaded image path." >&2
    exit 1
  fi
fi

IMAGE_NAME=$(basename "$IMAGE_PATH")

# ── Step 2: Copy to switch ────────────────────────────────────────────────────
step_banner "2/6" "Copying ${IMAGE_NAME} to ${SWITCH_IP}..."

"${SCRIPT_DIR}/deploy-image/copy-image-to-switch.sh" -s "$SWITCH_IP" -i "$IMAGE_PATH"

# ── Verify checksum ──────────────────────────────────────────────────────────
echo ""
echo "  Verifying checksum..."

if command -v shasum &>/dev/null; then
  LOCAL_SHA=$(shasum -a 256 "$IMAGE_PATH" | awk '{print $1}')
else
  LOCAL_SHA=$(sha256sum "$IMAGE_PATH" | awk '{print $1}')
fi

REMOTE_SHA=$(ssh_run "sha256sum /home/admin/${IMAGE_NAME}" | awk '{print $1}')

if [ "$LOCAL_SHA" != "$REMOTE_SHA" ]; then
  echo "  Checksum mismatch! Retrying copy..."
  echo "    Local:  ${LOCAL_SHA}"
  echo "    Remote: ${REMOTE_SHA}"
  echo ""
  "${SCRIPT_DIR}/deploy-image/copy-image-to-switch.sh" -s "$SWITCH_IP" -i "$IMAGE_PATH"

  REMOTE_SHA=$(ssh_run "sha256sum /home/admin/${IMAGE_NAME}" | awk '{print $1}')
  if [ "$LOCAL_SHA" != "$REMOTE_SHA" ]; then
    echo "Error: checksum still does not match after retry." >&2
    echo "  Local:  ${LOCAL_SHA}" >&2
    echo "  Remote: ${REMOTE_SHA}" >&2
    exit 1
  fi
fi
echo "  Checksum OK: ${LOCAL_SHA}"

# ── Step 3: Install and reboot ────────────────────────────────────────────────
step_banner "3/6" "Installing ${IMAGE_NAME} on ${SWITCH_IP}..."

"${SCRIPT_DIR}/deploy-image/install-image.sh" -s "$SWITCH_IP" -n "$IMAGE_NAME"

# ── Step 4: Wait for switch to come back after reboot ─────────────────────────
step_banner "4/6" "Waiting for switch to reboot into new image..."

sleep 10   # brief pause before checking if SSH has dropped
wait_for_switch_down 120
wait_for_switch 600

# ── Step 5: Cleanup old image (now booted into new partition) ─────────────────
step_banner "5/6" "Cleaning up previous image from old partition..."

ssh_run "sudo sonic-installer cleanup -y"

# ── Step 6: Factory reset ─────────────────────────────────────────────────────
step_banner "6/6" "Factory-resetting switch..."

"${SCRIPT_DIR}/deploy-image/factory-reset-switch.sh" -s "$SWITCH_IP"

echo ""
echo "  Waiting for switch to come back after config reload..."
sleep 15
wait_for_switch 300

echo ""
echo "  Saving config (sudo config save -y)..."
ssh_run "sudo config save -y"

# ══════════════════════════════════════════════════════════════════════════════
TOTAL=$(format_elapsed $SECONDS)
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "  All done! ${IMAGE_NAME} deployed to ${SWITCH_IP}."
echo "  Switch is up and running with factory-default config."
echo "  Total time: ${TOTAL}"
echo "╚══════════════════════════════════════════════════════════════╝"
