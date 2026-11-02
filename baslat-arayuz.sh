#!/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
if [ -f "$DIR/cachymacro/gui.py" ]; then
    cd "$DIR/cachymacro"
else
    cd "$DIR"
fi
trap "pkill -9 -f cachymacro-daemon 2>/dev/null || true" EXIT INT TERM
python3 gui.py
pkill -9 -f cachymacro-daemon 2>/dev/null || true
