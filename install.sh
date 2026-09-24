#!/usr/bin/env bash
#
# Install the DeckLink Output plugin for OpenLP.
#
# OpenLP 3.1.0 final and later load "community plugins" from
# <DataDir>/contrib/plugins/, which makes this a drop-in: no sudo, and it
# survives OpenLP upgrades.
#
# Earlier builds -- including 3.1.0~rc4, which is what Ubuntu 24.04 ships --
# have no community loader and silently ignore that directory. For those the
# plugin has to go into OpenLP's own plugins directory, which needs sudo. This
# script detects which case applies and will not guess on your behalf.
#
# Usage:
#   ./install.sh                 install to contrib/ (OpenLP 3.1.0 final or later)
#   ./install.sh --system        install into OpenLP's own plugins dir (needs sudo)
#   ./install.sh --uninstall     remove from both locations
#   ./install.sh --target DIR    use a different OpenLP data directory
#
set -euo pipefail

PLUGIN_NAME="decklink"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/${PLUGIN_NAME}"
DATA_DIR="${OPENLP_DATA_DIR:-$HOME/.local/share/openlp}"
MODE="contrib"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --uninstall) MODE="uninstall"; shift ;;
        --system) MODE="system"; shift ;;
        --target) DATA_DIR="$2"; shift 2 ;;
        -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

CONTRIB_DIR="${DATA_DIR}/contrib/plugins/${PLUGIN_NAME}"

# Where OpenLP's own package lives, or empty if python3 cannot import it.
openlp_package_dir() {
    python3 -c 'import os, openlp; print(os.path.dirname(openlp.__file__))' 2>/dev/null || true
}

# Prints "yes", "no" or "unknown": can this OpenLP load community plugins?
# Asks the installed code directly rather than parsing a version string,
# because "3.1.0~rc4" reads like 3.1.0 but predates the feature.
community_support() {
    python3 - <<'PY' 2>/dev/null || echo unknown
import inspect
try:
    from openlp.core.common import extension_loader
except Exception:
    print('unknown')
else:
    params = inspect.signature(extension_loader).parameters
    print('yes' if 'community' in params else 'no')
PY
}

SYSTEM_BASE="$(openlp_package_dir)"
SYSTEM_DIR="${SYSTEM_BASE:+${SYSTEM_BASE}/plugins/${PLUGIN_NAME}}"

copy_tree() {
    # copy_tree SRC DEST [sudo]
    local src="$1" dest="$2" run="${3:-}"
    $run mkdir -p "$(dirname "${dest}")"
    $run rm -rf "${dest}"
    $run cp -R "${src}" "${dest}"
    $run find "${dest}" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
}

if [[ "${MODE}" == "uninstall" ]]; then
    removed=0
    if [[ -d "${CONTRIB_DIR}" ]]; then
        rm -rf "${CONTRIB_DIR}"; echo "Removed ${CONTRIB_DIR}"; removed=1
    fi
    if [[ -n "${SYSTEM_DIR}" && -d "${SYSTEM_DIR}" ]]; then
        sudo rm -rf "${SYSTEM_DIR}"; echo "Removed ${SYSTEM_DIR}"; removed=1
    fi
    [[ "${removed}" -eq 0 ]] && echo "Nothing installed."
    echo "Restart OpenLP to unload the plugin."
    exit 0
fi

if [[ ! -d "${SOURCE_DIR}" ]]; then
    echo "Cannot find the plugin source at ${SOURCE_DIR}" >&2
    exit 1
fi

SUPPORT="$(community_support)"

if [[ "${MODE}" == "system" ]]; then
    if [[ -z "${SYSTEM_DIR}" ]]; then
        echo "python3 cannot import openlp, so its plugins directory is unknown." >&2
        echo "Is OpenLP installed from your distribution's packages?" >&2
        exit 1
    fi
    copy_tree "${SOURCE_DIR}" "${SYSTEM_DIR}" sudo
    sudo chown -R root:root "${SYSTEM_DIR}"
    sudo find "${SYSTEM_DIR}" -type d -exec chmod 755 {} +
    sudo find "${SYSTEM_DIR}" -type f -exec chmod 644 {} +
    echo "Installed to ${SYSTEM_DIR}"
    if [[ -d "${CONTRIB_DIR}" ]]; then
        echo "Note: an older copy also exists at ${CONTRIB_DIR}."
        echo "      Remove it to avoid confusion:  rm -rf '${CONTRIB_DIR}'"
    fi
else
    if [[ "${SUPPORT}" == "no" ]]; then
        cat >&2 <<MSG
This OpenLP cannot load community plugins, so installing to
  ${CONTRIB_DIR}
would be silently ignored. That includes 3.1.0~rc4, which Ubuntu 24.04 ships.

Install into OpenLP's own plugins directory instead (needs sudo):
  ./install.sh --system
MSG
        exit 1
    fi
    if [[ "${SUPPORT}" == "unknown" ]]; then
        echo "Warning: could not check whether this OpenLP loads community plugins." >&2
        echo "If the plugin does not appear in OpenLP, re-run with --system." >&2
    fi
    if [[ ! -d "${DATA_DIR}" ]]; then
        echo "Warning: ${DATA_DIR} does not exist yet." >&2
        echo "That usually means OpenLP has not been run, or its data lives elsewhere." >&2
        echo "Run OpenLP once, or pass --target /path/to/openlp/data." >&2
    fi
    copy_tree "${SOURCE_DIR}" "${CONTRIB_DIR}"
    echo "Installed to ${CONTRIB_DIR}"
fi

echo
echo "Checking runtime dependencies..."
missing=0
if python3 -c "import gi; gi.require_version('Gst','1.0'); from gi.repository import Gst" 2>/dev/null; then
    echo "  python3-gi + GStreamer      ok"
else
    echo "  python3-gi + GStreamer      MISSING  -> sudo apt install python3-gi gstreamer1.0-tools"
    missing=1
fi
check_element() {
    if command -v gst-inspect-1.0 >/dev/null 2>&1 && gst-inspect-1.0 "$1" >/dev/null 2>&1; then
        printf '  %-26s ok\n' "$1"
    else
        printf '  %-26s MISSING  -> sudo apt install %s\n' "$1" "$2"
        missing=1
    fi
}
check_element decklinkvideosink gstreamer1.0-plugins-bad
check_element videotestsrc gstreamer1.0-plugins-base
if [[ "${XDG_SESSION_TYPE:-}" == "wayland" ]]; then
    check_element pipewiresrc gstreamer1.0-pipewire
else
    check_element ximagesrc gstreamer1.0-plugins-good
fi
if [[ -e /dev/blackmagic/io0 ]]; then
    echo "  Desktop Video driver        ok (/dev/blackmagic/io0)"
else
    echo "  Desktop Video driver        NOT LOADED -> install it from blackmagicdesign.com/support"
    missing=1
fi

echo
[[ "${missing}" -eq 1 ]] && echo "Some dependencies are missing; install them before enabling the output."
cat <<'NEXT'
Next steps:
  1. Run the diagnostics:  python3 tools/smoketest.py check
  2. Prove the card:       python3 tools/smoketest.py bars --sink decklink --seconds 10
  3. Start OpenLP, activate "DeckLink Output" under Settings -> Manage Plugins,
     then enable it under Settings -> Configure OpenLP -> DeckLink Output.
NEXT
