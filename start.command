#!/bin/bash
# Soundboard launcher for macOS. Double-click it (first time: right-click > Open),
# or in Terminal type:  bash  (then drag this file in)  and press Enter.
cd "$(dirname "$0")" || exit 1

pause() { echo; read -r -p "Press Enter to close this window..."; }

# Python 3.9+ from python.org (the copy built into macOS is often too old or just an installer stub)
PY=""
for c in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
        PY="$c"; break
    fi
done
if [ -z "$PY" ]; then
    echo
    echo " Python 3 is not installed (or is too old)."
    echo " Opening the download page: install Python for macOS, then open start.command again."
    open "https://www.python.org/downloads/macos/"
    pause; exit 1
fi

# The app's own copy of its packages, so it never touches the rest of your Mac
if [ ! -x ".venv/bin/python" ]; then
    echo "First start: setting things up. This downloads about 150 MB and takes a few minutes..."
    "$PY" -m venv .venv || { echo " Could not create the app's Python folder."; pause; exit 1; }
fi
.venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt || {
    echo; echo " Could not download what the app needs. Check your internet connection and try again."
    pause; exit 1; }

echo "Starting Soundboard..."
.venv/bin/python soundboard.py || {
    echo; echo " The app closed with an error. The details are above, and saved in error.log."
    pause; exit 1; }
