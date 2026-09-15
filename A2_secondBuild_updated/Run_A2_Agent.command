#!/bin/bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR" || exit 1
VENV_PY="$ROOT_DIR/.venv/bin/python"

valid_python() {
    "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1
}

if [ -x "$VENV_PY" ] && valid_python "$VENV_PY"; then
    BOOTSTRAP_PY="$VENV_PY"
else
    BOOTSTRAP_PY=""
    for candidate in \
        python python3 python3.13 python3.12 python3.11 python3.10 python3.9 \
        /opt/homebrew/bin/python3 /usr/local/bin/python3 \
        /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 \
        /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
        /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 \
        /Library/Frameworks/Python.framework/Versions/3.10/bin/python3 \
        /Library/Frameworks/Python.framework/Versions/3.9/bin/python3
    do
        if command -v "$candidate" >/dev/null 2>&1; then
            resolved="$(command -v "$candidate")"
            if valid_python "$resolved"; then
                BOOTSTRAP_PY="$resolved"
                break
            fi
        elif [ -x "$candidate" ] && valid_python "$candidate"; then
            BOOTSTRAP_PY="$candidate"
            break
        fi
    done

    while [ -z "$BOOTSTRAP_PY" ]; do
        echo
        echo "A compatible Python executable was not detected automatically."
        echo "Enter the full path to a Python 3.9 or newer executable."
        echo "No Python installation will be attempted."
        read -r -p "Python executable path, or B to exit: " user_python
        user_python="${user_python%\"}"
        user_python="${user_python#\"}"
        if [ "$user_python" = "B" ] || [ "$user_python" = "b" ]; then
            exit 0
        fi
        if [ -x "$user_python" ] && valid_python "$user_python"; then
            BOOTSTRAP_PY="$user_python"
        else
            echo "That executable is not Python 3.9 or newer."
        fi
    done

    echo "Preparing the private project environment..."
    "$BOOTSTRAP_PY" -m venv --clear "$ROOT_DIR/.venv" || {
        echo "Setup did not complete. Run this file again to repair the private environment."
        read -r -p "Press Enter to close."
        exit 1
    }
fi

echo "Checking project dependencies..."
"$VENV_PY" -m pip install --disable-pip-version-check --quiet -r "$ROOT_DIR/requirements.txt" || {
    echo "Dependency setup did not complete. Run this file again to retry safely."
    read -r -p "Press Enter to close."
    exit 1
}

echo "Starting the PE6201 A2 Agent..."
"$VENV_PY" "$ROOT_DIR/main.py"
run_status=$?
if [ "$run_status" -ne 0 ]; then
    echo
    echo "The agent stopped with exit code $run_status."
fi
echo
read -r -p "Press Enter to close."
exit "$run_status"
