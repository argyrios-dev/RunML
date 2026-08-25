#!/bin/bash
set -euo pipefail

echo
echo "RunML v0.6.0 - macOS Apple Silicon installer/updater"
echo "----------------------------------------------------"
echo

if [[ "$(uname -s)" != "Darwin" ]]; then
    echo "ERROR: install.sh is for macOS."
    echo "Windows users should run install.ps1."
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 was not found."
    echo "Install a native Apple Silicon Python 3.10+ and run this installer again."
    exit 1
fi

PY_VERSION="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')"
if ! python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
then
    echo "ERROR: Python 3.10+ is required. Found Python $PY_VERSION."
    exit 1
fi

# Detect Apple Silicon hardware even when the current shell is translated.
APPLE_SILICON="$(sysctl -n hw.optional.arm64 2>/dev/null || echo 0)"
PY_ARCH="$(python3 -c 'import platform; print(platform.machine().lower())')"

if [[ "$APPLE_SILICON" != "1" ]]; then
    echo "ERROR: RunML v0.6 officially supports Apple Silicon Macs (M1 or newer)."
    exit 1
fi

if [[ "$PY_ARCH" != "arm64" ]]; then
    echo "ERROR: Python is running as '$PY_ARCH' instead of native 'arm64'."
    echo "RunML will not install under Rosetta/x86_64 Python."
    echo "Install/use a native Apple Silicon Python and retry."
    exit 1
fi

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_ROOT="$HOME/Library/Application Support/RunML"
RUNTIME_DIR="$INSTALL_ROOT/runtime"
STATE_DIR="$INSTALL_ROOT"
BIN_DIR="$HOME/.local/bin"
LAUNCHER="$BIN_DIR/runml"
POINTER_FILE="$STATE_DIR/location.json"
LEGACY_POINTER="$HOME/.config/runml/location.json"
FIRST_START_MARKER="$STATE_DIR/first-start.done"
UNINSTALLER="$INSTALL_ROOT/uninstall.sh"

mkdir -p "$INSTALL_ROOT" "$BIN_DIR"

HAD_PREVIOUS_INSTALL=0
if [[ -d "$RUNTIME_DIR" || -f "$LAUNCHER" ]]; then
    HAD_PREVIOUS_INSTALL=1
    echo "Previous RunML installation detected."
    if [[ -x "$RUNTIME_DIR/bin/python" ]]; then
        OLD_VERSION="$("$RUNTIME_DIR/bin/python" -m runml --version 2>/dev/null || true)"
        [[ -n "$OLD_VERSION" ]] && echo "Installed: $OLD_VERSION"
    fi
    echo "It will be replaced by RunML v0.6.0."
    echo
fi

read_pointer() {
    local file="$1"
    [[ -f "$file" ]] || return 1
    python3 - "$file" <<'PY'
import json, sys
from pathlib import Path
try:
    value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["data_dir"]
    print(value)
except Exception:
    raise SystemExit(1)
PY
}

DATA_DIR=""
if DATA_DIR="$(read_pointer "$POINTER_FILE" 2>/dev/null)"; then
    :
elif DATA_DIR="$(read_pointer "$LEGACY_POINTER" 2>/dev/null)"; then
    # Migrate the old pointer into the native macOS application-support path.
    python3 - "$POINTER_FILE" "$DATA_DIR" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps({"data_dir": sys.argv[2]}, indent=2), encoding="utf-8")
PY
else
    DATA_DIR=""
fi

has_learning_data() {
    local base="$1"
    [[ -d "$base" ]] || return 1
    local child
    for child in data models reports; do
        if [[ -d "$base/$child" ]] && find "$base/$child" -type f -print -quit 2>/dev/null | grep -q .; then
            return 0
        fi
    done
    return 1
}

if [[ -n "$DATA_DIR" ]] && has_learning_data "$DATA_DIR"; then
    echo "Previous RunML learning data was found at:"
    echo "  $DATA_DIR"
    printf "Delete previous TRAINED DATA/models/reports before upgrading? [y/N]: "
    IFS= read -r answer
    answer_lower="$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')"
    case "$answer_lower" in
        y|yes|s|si|sí)
            for child in data models reports; do
                rm -rf "$DATA_DIR/$child"
                mkdir -p "$DATA_DIR/$child"
            done
            echo "Previous learning data removed. Settings were preserved."
            ;;
        *)
            echo "Previous learning data will be preserved."
            ;;
    esac
    echo
fi

if [[ -d "$RUNTIME_DIR" ]]; then
    echo "Replacing private RunML runtime..."
    rm -rf "$RUNTIME_DIR"
fi

echo "Creating native arm64 Python runtime..."
python3 -m venv "$RUNTIME_DIR"

PYTHON="$RUNTIME_DIR/bin/python"

echo "Installing RunML..."
"$PYTHON" -m pip install --disable-pip-version-check "$SOURCE_DIR"

cat > "$LAUNCHER" <<'EOF'
#!/bin/bash
exec "$HOME/Library/Application Support/RunML/runtime/bin/python" -m runml "$@"
EOF
chmod 755 "$LAUNCHER"

cp "$SOURCE_DIR/uninstall.sh" "$UNINSTALLER"
chmod 755 "$UNINSTALLER"

ZPROFILE="$HOME/.zprofile"
PATH_BEGIN="# >>> RunML PATH >>>"
PATH_END="# <<< RunML PATH <<<"

if ! grep -Fq "$PATH_BEGIN" "$ZPROFILE" 2>/dev/null; then
    {
        echo
        echo "$PATH_BEGIN"
        echo 'export PATH="$HOME/.local/bin:$PATH"'
        echo "$PATH_END"
    } >> "$ZPROFILE"
    echo "Added ~/.local/bin to PATH in ~/.zprofile."
fi

# Fresh installs ask for storage on first start.
# Upgrades with a valid previous data directory retain their location/settings.
if [[ -n "$DATA_DIR" && -d "$DATA_DIR" ]]; then
    printf '%s\n' "0.6.0" > "$FIRST_START_MARKER"
else
    rm -f "$FIRST_START_MARKER"
fi

echo
echo "RunML v0.6.0 installed successfully."
echo "Native architecture: arm64"
echo
echo "Open a new Terminal window and run:"
echo "  runml"
echo
if [[ -z "$DATA_DIR" || ! -d "$DATA_DIR" ]]; then
    echo "The first start will require you to choose a data directory."
else
    echo "Existing RunML settings/data location preserved:"
    echo "  $DATA_DIR"
fi
