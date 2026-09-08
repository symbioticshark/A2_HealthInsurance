#!/bin/bash
# Run_A2_Agent.command
#
# Double-click this in Finder to run the agent on macOS. Right-click it once
# and choose "Open" the very first time (Gatekeeper blocks an unsigned
# script on the first launch; after that, double-click works normally).
#
# If double-clicking does nothing, it's almost always the executable bit --
# fix it once from Terminal:
#   chmod +x Run_A2_Agent.command
#
# What this does: finds python3, makes sure `requests` is installed (only
# needed for the live-battery command, harmless otherwise), then opens a
# small menu. It always runs from THIS file's folder, wherever you moved it.

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 not found."
    echo "Install it from https://www.python.org/downloads/macos/ or run: brew install python3"
    read -n 1 -s -r -p "Press any key to close..."
    exit 1
fi

python3 -c "import requests" 2>/dev/null || {
    echo "Installing the one optional dependency (requests, for the live-battery command)..."
    python3 -m pip install --quiet --user requests
}

echo "=============================================="
echo " PE6201 A2 -- Problem A agent"
echo " Running from: $(pwd)"
echo "=============================================="
echo "  1) Scripted evaluation, 1 trial   (main.py eval)"
echo "  2) Scripted evaluation, 3 trials  (main.py eval --trials 3)"
echo "  3) Trace one case                 (main.py run CLM-8888)"
echo "  4) D7 failure demo                (main.py failures)"
echo "  5) Data/label sanity check        (main.py check)"
echo "  6) Custom command"
echo "  q) Quit"
echo "=============================================="
read -r -p "Choice: " choice

case "$choice" in
    1) python3 main.py eval ;;
    2) python3 main.py eval --trials 3 --verbose ;;
    3) read -r -p "Case id (e.g. CLM-8888): " cid; python3 main.py run "$cid" ;;
    4) python3 main.py failures ;;
    5) python3 main.py check ;;
    6) read -r -p "Arguments after main.py: " customargs; python3 main.py $customargs ;;
    q|Q) exit 0 ;;
    *) echo "Unrecognised choice, running default eval." ; python3 main.py eval ;;
esac

echo
read -n 1 -s -r -p "Done. Press any key to close this window..."
