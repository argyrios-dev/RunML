#!/bin/bash
set -euo pipefail

INSTALL_ROOT="$HOME/Library/Application Support/RunML"
LAUNCHER="$HOME/.local/bin/runml"
ZPROFILE="$HOME/.zprofile"
PATH_BEGIN="# >>> RunML PATH >>>"
PATH_END="# <<< RunML PATH <<<"

rm -f "$LAUNCHER"

# Remove only the installer-added PATH block.
if [[ -f "$ZPROFILE" ]]; then
    python3 - "$ZPROFILE" "$PATH_BEGIN" "$PATH_END" <<'PY'
import sys
from pathlib import Path
path = Path(sys.argv[1])
begin, end = sys.argv[2], sys.argv[3]
lines = path.read_text(encoding="utf-8").splitlines()
out = []
inside = False
for line in lines:
    if line.strip() == begin:
        inside = True
        continue
    if line.strip() == end:
        inside = False
        continue
    if not inside:
        out.append(line)
path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
PY
fi

rm -rf "$INSTALL_ROOT/runtime"
rm -f "$INSTALL_ROOT/uninstall.sh"

echo
echo "RunML runtime/terminal command removed."
echo "Your selected data directory and settings were NOT deleted."
echo "Open a new Terminal window to refresh PATH."
