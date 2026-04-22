#!/usr/bin/env bash
# testbed.sh — Manage Caspian SONiC testbed topologies
#
# Usage:
#   ./testbed.sh <action> -s <spine> -t <topology> [-c <test>]
#
# Actions:
#   setup         Add topology + deploy minigraph (add-topo then deploy-mg)
#   add-topo      Add topology to testbed
#   remove-topo   Remove topology from testbed
#   deploy-mg     Deploy minigraph
#   run-tests     Run full test suite
#   single-test   Run a single test (requires -c)
#   show          Print the generated commands without executing
#
# Options:
#   -s <num>    Spine number: 6, 7, 8, 9, 10                    (required)
#   -t <topo>   Topology: t0, t1, t1-lag, t0-64, t1-64          (required)
#   -c <test>   Test path for single-test (e.g. clock/test_clock.py)
#   -h          Show this help
#
# Examples:
#   ./testbed.sh setup       -s 8 -t t0       # add topo + deploy-mg for spine8 t0
#   ./testbed.sh add-topo    -s 7 -t t1       # add t1 topology on spine7
#   ./testbed.sh remove-topo -s 9 -t t0-64    # remove t0-64 topology on spine9
#   ./testbed.sh deploy-mg   -s 10 -t t1-lag  # deploy minigraph for t1-lag on spine10
#   ./testbed.sh run-tests   -s 8 -t t0       # run full t0 test suite on spine8
#   ./testbed.sh single-test -s 8 -t t0 -c clock/test_clock.py
#   ./testbed.sh show        -s 8 -t t0       # print all commands for this testbed

set -euo pipefail

# ── Paths (on the test server) ────────────────────────────────────────────────
ANSIBLE_DIR="/var/AzDevOps/ansible"
TESTS_DIR="/var/AzDevOps/tests"
TESTBED_YAML="${ANSIBLE_DIR}/testbed.yaml"
VEOS_INV="${ANSIBLE_DIR}/veos"
PASSWORD_FILE="${ANSIBLE_DIR}/password.txt"

# ── Parse args ────────────────────────────────────────────────────────────────
usage() {
  sed -n '/^# Usage:/,/^$/p' "$0" | sed 's/^# \?//'
  exit 0
}

case "${1:-}" in -h|--help) usage ;; esac

ACTION="${1:-}"
shift 2>/dev/null || true

SPINE=""
TOPO=""
TEST_CASE=""

while getopts ":s:t:c:h" opt; do
  case $opt in
    s) SPINE="$OPTARG" ;;
    t) TOPO="$OPTARG" ;;
    c) TEST_CASE="$OPTARG" ;;
    h) usage ;;
    :) echo "Error: option -$OPTARG requires an argument." >&2; exit 1 ;;
    ?) echo "Error: unknown option -$OPTARG." >&2; exit 1 ;;
  esac
done

# ── Validate action ──────────────────────────────────────────────────────────
VALID_ACTIONS="setup add-topo remove-topo deploy-mg run-tests single-test show"
if [ -z "$ACTION" ] || ! echo "$VALID_ACTIONS" | grep -qw "$ACTION"; then
  echo "Error: action must be one of: ${VALID_ACTIONS}" >&2
  echo "Run with -h for usage." >&2
  exit 1
fi

# ── Validate spine ───────────────────────────────────────────────────────────
if [ -z "$SPINE" ]; then
  echo "Error: -s <spine> is required (6, 7, 8, 9, 10)." >&2
  exit 1
fi
if ! echo "6 7 8 9 10" | grep -qw "$SPINE"; then
  echo "Error: spine must be 6, 7, 8, 9, or 10 (got: ${SPINE})." >&2
  exit 1
fi

# ── Validate topology ────────────────────────────────────────────────────────
if [ -z "$TOPO" ]; then
  echo "Error: -t <topology> is required (t0, t1, t1-lag, t0-64, t1-64)." >&2
  exit 1
fi
if ! echo "t0 t1 t1-lag t0-64 t1-64" | grep -qw "$TOPO"; then
  echo "Error: topology must be t0, t1, t1-lag, t0-64, or t1-64 (got: ${TOPO})." >&2
  exit 1
fi

if [ "$ACTION" = "single-test" ] && [ -z "$TEST_CASE" ]; then
  echo "Error: single-test requires -c <test_path>." >&2
  exit 1
fi

if [ -n "$TEST_CASE" ] && ! [[ "$TEST_CASE" =~ ^[a-zA-Z0-9_./-]+$ ]]; then
  echo "Error: test path contains invalid characters (got: ${TEST_CASE})." >&2
  echo "  Only alphanumeric, '/', '_', '-', and '.' are allowed." >&2
  exit 1
fi

# ── Derive names ──────────────────────────────────────────────────────────────
TESTBED_NAME="caspian_testbed_${TOPO}_spine${SPINE}-800"

if [ "$SPINE" = "10" ]; then
  DEVICE_NAME="spine10-800"
else
  DEVICE_NAME="upscalelab2-spine${SPINE}-800"
fi

# t0 and t0-64 test as t0; everything else tests as t1
case "$TOPO" in
  t0|t0-64) TEST_TOPO="t0,any" ;;
  *)        TEST_TOPO="t1,any" ;;
esac

# ── Command builders ──────────────────────────────────────────────────────────
cmd_add_topo() {
  echo "sudo su -c \"cd '${ANSIBLE_DIR}' && time ./testbed-cli.sh -t '${TESTBED_YAML}' -m '${VEOS_INV}' -k ceos add-topo '${TESTBED_NAME}' '${PASSWORD_FILE}' -vvvv\""
}

cmd_remove_topo() {
  echo "sudo su -c \"cd '${ANSIBLE_DIR}' && time ./testbed-cli.sh -t '${TESTBED_YAML}' -m '${VEOS_INV}' -k ceos remove-topo '${TESTBED_NAME}' '${PASSWORD_FILE}' -vvvv\""
}

cmd_deploy_mg() {
  echo "cd '${ANSIBLE_DIR}' && time ./testbed-cli.sh -t testbed.yaml deploy-mg '${TESTBED_NAME}' veos ./password.txt -e use_ptf_tacacs_server=false -vvv"
}

cmd_run_tests() {
  echo "cd '${TESTS_DIR}' && sudo ./run_tests.sh -d '${DEVICE_NAME}' -f ../ansible/testbed.yaml -i ../ansible/veos -k debug -l debug -p test_logs/logs -F tests.txt -t '${TEST_TOPO}' -n '${TESTBED_NAME}' -e '--deselect-file=tests_deselect.txt --skip_sanity --alluredir=allure-results' -u"
}

cmd_single_test() {
  local test_path="$1"
  echo "cd '${TESTS_DIR}' && sudo ./run_tests.sh -d '${DEVICE_NAME}' -f ../ansible/testbed.yaml -i ../ansible/veos -k debug -l debug -p test_logs/logs -c '${test_path}' -t '${TEST_TOPO}' -n '${TESTBED_NAME}' -e '--skip_sanity --alluredir=allure-results' -u"
}

# ── Ensure test list files exist ───────────────────────────────────────────────
ensure_test_files() {
  for fname in tests.txt tests_deselect.txt; do
    local fpath="${TESTS_DIR}/${fname}"
    if [ ! -f "$fpath" ]; then
      echo "  ${fname} not found at ${fpath}."
      echo "  Enter test entries (one per line). Press Ctrl-D when done:"
      echo "  (Leave empty and press Ctrl-D to create an empty file.)"
      echo ""
      sudo tee "$fpath" > /dev/null
      echo ""
      echo "  Created ${fpath} ($(wc -l < "$fpath" | tr -d ' ') lines)."
      echo ""
    fi
  done
}

# ── Execute ───────────────────────────────────────────────────────────────────
run_cmd() {
  local label="$1" cmd="$2"
  echo "── ${label} ──"
  echo "  ${cmd}"
  echo ""
  eval "$cmd"
}

echo ""
echo "  Testbed  : ${TESTBED_NAME}"
echo "  Device   : ${DEVICE_NAME}"
echo "  Topology : ${TOPO}"
echo "  Spine    : ${SPINE}"
echo ""

case "$ACTION" in
  show)
    echo "── add-topo ──"
    echo "  $(cmd_add_topo)"
    echo ""
    echo "── remove-topo ──"
    echo "  $(cmd_remove_topo)"
    echo ""
    echo "── deploy-mg ──"
    echo "  $(cmd_deploy_mg)"
    echo ""
    echo "── run-tests ──"
    echo "  $(cmd_run_tests)"
    echo ""
    echo "── single-test (example) ──"
    echo "  $(cmd_single_test 'clock/test_clock.py')"
    ;;

  add-topo)
    run_cmd "add-topo" "$(cmd_add_topo)"
    ;;

  remove-topo)
    run_cmd "remove-topo" "$(cmd_remove_topo)"
    ;;

  deploy-mg)
    run_cmd "deploy-mg" "$(cmd_deploy_mg)"
    ;;

  setup)
    run_cmd "add-topo" "$(cmd_add_topo)"
    echo ""
    run_cmd "deploy-mg" "$(cmd_deploy_mg)"
    echo ""
    echo "Setup complete for ${TESTBED_NAME}."
    ;;

  run-tests)
    ensure_test_files
    run_cmd "run-tests" "$(cmd_run_tests)"
    ;;

  single-test)
    run_cmd "single-test" "$(cmd_single_test "$TEST_CASE")"
    ;;
esac
