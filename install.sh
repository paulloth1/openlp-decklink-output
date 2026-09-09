#!/usr/bin/env bash
#
# Install the DeckLink Output plugin into OpenLP's community plugin directory.
#
# OpenLP 3.1 and later scan <DataDir>/contrib/plugins/*/[!.]*plugin.py, so the
# plugin is a drop-in: no fork, no patching an installed OpenLP, and it survives
# OpenLP upgrades.
#
# Usage:
#   ./install.sh                 install (or update) the plugin
#   ./install.sh --uninstall     remove it
#   ./install.sh --target DIR    use a different OpenLP data directory
#
set -euo pipefail

PLUGIN_NAME="decklink"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/${PLUGIN_NAME}"
DATA_DIR="${OPENLP_DATA_DIR:-$HOME/.local/share/openlp}"
UNINSTALL=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --uninstall) UNINSTALL=1; shift ;;
        --target) DATA_DIR="$2"; shift 2 ;;
        -h|--help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

TARGET_DIR="${DATA_DIR}/contrib/plugins/${PLUGIN_NAME}"

if [[ "${UNINSTALL}" -eq 1 ]]; then
    if [[ -d "${TARGET_DIR}" ]]; then
        rm -rf "${TARGET_DIR}"
        echo "Removed ${TARGET_DIR}"
    else
        echo "Nothing installed at ${TARGET_DIR}"
    fi
    echo "Restart OpenLP to unload the plugin."
    exit 0
fi

if [[ ! -d "${SOURCE_DIR}" ]]; then
    echo "Cannot find the plugin source at ${SOURCE_DIR}" >&2
    exit 1
fi

if [[ ! -d "${DATA_DIR}" ]]; then
    echo "Warning: ${DATA_DIR} does not exist yet." >&2
    echo "That usually means OpenLP has not been run, or its data lives elsewhere." >&2
    echo "Run OpenLP once, or pass --target /path/to/openlp/data." >&2
fi

mkdir -p "$(dirname "${TARGET_DIR}")"
rm -rf "${TARGET_DIR}"
cp -R "${SOURCE_DIR}" "${TARGET_DIR}"
find "${TARGET_DIR}" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
echo "Installed to ${TARGET_DIR}"

echo
echo "Checking runtime dependencies..."
missing=0
check_python_module() {
    if python3 -c "import gi; gi.require_version('Gst','1.0'); from gi.repository import Gst" 2>/dev/null; then
        echo "  python3-gi + GStreamer      ok"
    else
        echo "  python3-gi + GStreamer      MISSING  -> sudo apt install python3-gi gstreamer1.0-tools"
        missing=1
    fi
}
check_element() {
    if command -v gst-inspect-1.0 >/dev/null 2>&1 && gst-inspect-1.0 "$1" >/dev/null 2>&1; then
        echo "  $1$(printf '%*s' $((26 - ${#1})) '')ok"
    else
        echo "  $1$(printf '%*s' $((26 - ${#1})) '')MISSING  -> sudo apt install $2"
        missing=1
    fi
}
check_python_module
check_element decklinkvideosink gstreamer1.0-plugins-bad
check_element videotestsrc gstreamer1.0-plugins-base
if [[ "${XDG_SESSION_TYPE:-}" == "wayland" ]]; then
    check_element pipewiresrc gstreamer1.0-pipewire
else
    check_element ximagesrc gstreamer1.0-plugins-good
fi

echo
if [[ "${missing}" -eq 1 ]]; then
    echo "Some dependencies are missing; install them before enabling the output."
fi
cat <<'NEXT'
Next steps:
  1. Install the Blackmagic Desktop Video driver if you have not already.
     Verify with:  lsmod | grep blackmagic
  2. Run the diagnostics:  python3 tools/smoketest.py check
  3. Start OpenLP, open Settings -> DeckLink Output, and enable the output.
NEXT
