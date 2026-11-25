#!/bin/bash
# Symlink the scripts into ~/.local/bin and install the desktop entry.
set -eu
REPO="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin"; APPS="$HOME/.local/share/applications"
mkdir -p "$BIN" "$APPS"

missing=()
for cmd in pw-jack pw-link python3; do command -v "$cmd" >/dev/null || missing+=("$cmd"); done
[ -e /usr/lib/carla/libcarla_standalone2.so ] || missing+=("carla")
[ -d "$HOME/.local/opt/AIDA-X/AIDA-X.lv2" ] || echo "warning: AIDA-X.lv2 not found in ~/.local/opt/AIDA-X" >&2
if [ ${#missing[@]} -gt 0 ]; then
  echo "missing: ${missing[*]}  (try: sudo apt install carla pipewire-jack)" >&2; exit 1
fi

link() {  # link SRC DEST, backing up a real file once
  if [ -e "$2" ] && [ ! -L "$2" ]; then mv "$2" "$2.bak"; echo "backed up $2 -> $2.bak"; fi
  ln -sfn "$1" "$2"; echo "$2 -> $1"
}
link "$REPO/bin/aida-x-live"       "$BIN/aida-x-live"
link "$REPO/bin/aida-x-carla.py"   "$BIN/aida-x-carla.py"
link "$REPO/bin/aida-x-ctl"        "$BIN/aida-x-ctl"
link "$REPO/bin/aida-x-presets"    "$BIN/aida-x-presets"
link "$REPO/bin/aida-x-standalone" "$BIN/aida-x"
cp "$REPO/aida-x-live.desktop" "$REPO/aida-x-presets.desktop" "$APPS/"
