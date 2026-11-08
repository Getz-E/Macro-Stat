#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
# Fedora 41+ installation entry point (python3-pyqt6 6.7+, rust 1.83+).
set -euo pipefail

# Yardımcı kütüphane source edilmeden önce kök çalıştırmayı reddet.
if [ "$(id -u)" -eq 0 ]; then
    printf '❌ Do not run this installer as root. Run it as your regular user; the script elevates only package and udev steps.\n' >&2
    exit 1
fi

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

DISTRO_FAMILY="fedora"
DISTRO_LABEL="Fedora 41+"
DISTRO_MIN_VERSION="41"
EXPECTED_DISTRO="fedora"

# shellcheck source=packaging/install-common.sh
source "$DIR/packaging/install-common.sh"

main "$@"
