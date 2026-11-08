#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
# Ubuntu 24.04+ installation entry point (python3-pyqt6 6.6+; the shared library
# upgrades the 1.75 repository rustc to the versioned rustc-1.79/cargo-1.79).
set -euo pipefail

# Yardımcı kütüphane source edilmeden önce kök çalıştırmayı reddet.
if [ "$(id -u)" -eq 0 ]; then
    printf '❌ Do not run this installer as root. Run it as your regular user; the script elevates only package and udev steps.\n' >&2
    exit 1
fi

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

DISTRO_FAMILY="debian"
DISTRO_LABEL="Ubuntu 24.04+"
DISTRO_MIN_VERSION="24.04"
EXPECTED_DISTRO="ubuntu"

# shellcheck source=packaging/install-common.sh
source "$DIR/packaging/install-common.sh"

main "$@"
