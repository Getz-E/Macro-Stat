#!/bin/bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"
trap "pkill -9 -f cachymacro-daemon 2>/dev/null || true" EXIT INT TERM
python3 gui.py
pkill -9 -f cachymacro-daemon 2>/dev/null || true
