#!/usr/bin/env bash
# check-deps.sh — Verify (and optionally install) required dependencies
#
# Source this script; it exports `check_deps` which accepts a list of
# required commands and an optional list of optional commands:
#
#   source check-deps.sh
#   check_deps "curl python3 sshpass" "pv"
#
# Required deps that are missing will be auto-installed (with confirmation).
# Optional deps that are missing print a hint but don't block execution.

_detect_pkg_manager() {
  case "$(uname -s)" in
    Darwin)
      if command -v brew &>/dev/null; then
        echo "brew"
      else
        echo "none"
      fi
      ;;
    Linux)
      if command -v apt-get &>/dev/null; then
        echo "apt"
      elif command -v dnf &>/dev/null; then
        echo "dnf"
      elif command -v yum &>/dev/null; then
        echo "yum"
      else
        echo "none"
      fi
      ;;
    *)
      echo "none"
      ;;
  esac
}

_install_cmd() {
  local pkg_mgr="$1"
  local cmd="$2"

  case "$pkg_mgr" in
    brew)
      case "$cmd" in
        sshpass) brew install hudochenkov/sshpass/sshpass ;;
        *)       brew install "$cmd" ;;
      esac
      ;;
    apt)
      sudo apt-get update -qq && sudo apt-get install -y "$cmd"
      ;;
    dnf)
      sudo dnf install -y "$cmd"
      ;;
    yum)
      sudo yum install -y "$cmd"
      ;;
  esac
}

_install_hint() {
  local pkg_mgr="$1"
  local cmd="$2"

  case "$pkg_mgr" in
    brew)
      case "$cmd" in
        sshpass) echo "  brew install hudochenkov/sshpass/sshpass" ;;
        *)       echo "  brew install $cmd" ;;
      esac
      ;;
    apt)  echo "  sudo apt-get install $cmd" ;;
    dnf)  echo "  sudo dnf install $cmd" ;;
    yum)  echo "  sudo yum install $cmd" ;;
    none) echo "  (install '$cmd' using your system's package manager)" ;;
  esac
}

check_deps() {
  local required="$1"
  local optional="${2:-}"
  local pkg_mgr
  pkg_mgr=$(_detect_pkg_manager)

  local missing=()
  for cmd in $required; do
    if ! command -v "$cmd" &>/dev/null; then
      missing+=("$cmd")
    fi
  done

  if [ ${#missing[@]} -gt 0 ]; then
    echo "Missing required dependencies: ${missing[*]}"
    echo ""

    if [ "$pkg_mgr" = "none" ]; then
      echo "Could not detect a supported package manager. Please install manually:"
      for cmd in "${missing[@]}"; do
        _install_hint "none" "$cmd"
      done
      exit 1
    fi

    echo "Install with $pkg_mgr? [Y/n] "
    read -r answer </dev/tty
    if [[ "$answer" =~ ^[Nn] ]]; then
      echo "Cannot continue without: ${missing[*]}" >&2
      exit 1
    fi

    for cmd in "${missing[@]}"; do
      echo "Installing $cmd..."
      if ! _install_cmd "$pkg_mgr" "$cmd"; then
        echo "Error: failed to install $cmd. Install manually:" >&2
        _install_hint "$pkg_mgr" "$cmd" >&2
        exit 1
      fi
    done
    echo ""
  fi

  for cmd in $optional; do
    if ! command -v "$cmd" &>/dev/null; then
      echo "Optional: '$cmd' not found — install for a better experience:"
      _install_hint "$pkg_mgr" "$cmd"
      echo ""
    fi
  done
}
