#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
# MacroStat arayüz başlatıcısı.
# Tek kanonik dizin yapısı kullanılır; motorun yaşam döngüsünü gui.py yönetir.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"
exec python3 "$DIR/gui.py" "$@"
