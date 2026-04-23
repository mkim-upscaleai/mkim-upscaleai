#!/usr/bin/env bash
# download-sonic.sh — Download a SONiC image from the Sonic Ops dashboard
#
# Usage:
#   ./download-sonic.sh                        # latest prod mellanox build
#   ./download-sonic.sh -t gating              # latest gating mellanox build
#   ./download-sonic.sh -t prod -p vs          # latest prod vs build
#   ./download-sonic.sh -t prod -b upscaleai-202511  # specific branch
#   ./download-sonic.sh -i 449                 # specific build by ID
#   ./download-sonic.sh -t prod -o sonic.bin   # custom output filename
#
# Options:
#   -i <id>       Download a specific build by ID (overrides -t, -b, -p)
#   -t <tag>      Build tag to filter by     (default: prod)
#   -p <plat>     Platform to filter by: mellanox | vs  (default: mellanox)
#   -b <branch>   Branch to filter by        (default: any)
#   -o <file>     Output filename            (default: auto from URL)
#   -f            Force re-download even if image already exists
#   -h            Show this help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DASHBOARD="http://192.168.218.28:5010"
TAG="prod"
PLATFORM="mellanox"
BRANCH=""
BUILD_ID_ARG=""
OUTFILE=""
FORCE=false
OUTDIR="${SCRIPT_DIR}/../downloaded-images"

usage() {
  sed -n '/^# Usage:/,/^$/p' "$0" | sed 's/^# \?//'
  exit 0
}

while getopts "i:t:p:b:o:fh" opt; do
  case $opt in
    i) BUILD_ID_ARG="$OPTARG" ;;
    t) TAG="$OPTARG" ;;
    p) PLATFORM="$OPTARG" ;;
    b) BRANCH="$OPTARG" ;;
    o) OUTFILE="$OPTARG" ;;
    f) FORCE=true ;;
    h) usage ;;
    *) echo "Unknown option -$OPTARG" >&2; exit 1 ;;
  esac
done

if [ -n "$BUILD_ID_ARG" ]; then
  echo "Fetching build #${BUILD_ID_ARG}..."
  META=$(curl -sf "${DASHBOARD}/api/builds/${BUILD_ID_ARG}") || {
    echo "Error: could not fetch build #${BUILD_ID_ARG} from ${DASHBOARD}" >&2
    exit 1
  }
else
  QUERY="tag=${TAG}&status=success&platform=${PLATFORM}"
  [ -n "$BRANCH" ] && QUERY="${QUERY}&branch=${BRANCH}"

  echo "Fetching latest '${TAG}' build info (platform: ${PLATFORM})..."
  META=$(curl -sf "${DASHBOARD}/api/builds/latest?${QUERY}") || {
    echo "Error: could not reach dashboard at ${DASHBOARD}" >&2
    exit 1
  }
fi

# Parse fields
ARTIFACT=$(echo "$META" | python3 -c "import sys,json; print(json.load(sys.stdin).get('artifact',''))" 2>/dev/null)
BUILDTIME=$(echo "$META" | python3 -c "import sys,json; print(json.load(sys.stdin).get('buildtime',''))" 2>/dev/null)
BRANCH_OUT=$(echo "$META" | python3 -c "import sys,json; print(json.load(sys.stdin).get('branch',''))" 2>/dev/null)
BUILD_ID=$(echo "$META" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)

if [ -z "$ARTIFACT" ] || [ "$ARTIFACT" = "None" ]; then
  if [ -n "$BUILD_ID_ARG" ]; then
    echo "Error: no artifact URL found for build #${BUILD_ID_ARG}" >&2
  else
    echo "Error: no artifact URL found for tag='${TAG}' platform='${PLATFORM}'" >&2
  fi
  exit 1
fi

echo "  Build ID : ${BUILD_ID}"
echo "  Branch   : ${BRANCH_OUT}"
echo "  Built at : ${BUILDTIME}"

# Auto-generate output filename from URL if not specified
if [ -z "$OUTFILE" ]; then
  OUTFILE=$(basename "${ARTIFACT%%\?*}")   # strip query string, take filename
fi

mkdir -p "$OUTDIR"
OUTPATH="${OUTDIR}/${OUTFILE}"

if [ -f "$OUTPATH" ] && ! $FORCE; then
  echo "  Output   : ${OUTPATH}"
  echo ""
  echo "Image already exists in downloaded-images — skipping download. (use -f to force)"
  echo "Done: $(du -h "$OUTPATH" | cut -f1)  ${OUTPATH}"
else
  echo "  Output   : ${OUTPATH}"
  echo ""
  echo "Downloading..."
  curl -f -L --progress-bar -o "$OUTPATH" "$ARTIFACT"

  echo ""
  echo "Done: $(du -h "$OUTPATH" | cut -f1)  ${OUTPATH}"
fi
