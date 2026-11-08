#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
# Debian 13+ installation entry point (python3-pyqt6 6.9+, rustc 1.85+).
set -euo pipefail

# Yardımcı kütüphane source edilmeden önce kök çalıştırmayı reddet.
if [ "$(id -u)" -eq 0 ]; then
    printf '❌ Do not run this installer as root. Run it as your regular user; the script elevates only package and udev steps.\n' >&2
    exit 1
fi

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

DISTRO_FAMILY="debian"
DISTRO_LABEL="Debian 13+"
DISTRO_MIN_VERSION="13"
EXPECTED_DISTRO="debian"

# shellcheck source=packaging/install-common.sh
source "$DIR/packaging/install-common.sh"

main "$@"
