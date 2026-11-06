#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
# Ubuntu 24.04+ installation entry point (python3-pyqt6 6.6+; the shared library
# upgrades the 1.75 repository rustc to the versioned rustc-1.79/cargo-1.79).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

DISTRO_FAMILY="debian"
DISTRO_LABEL="Ubuntu 24.04+"
DISTRO_MIN_VERSION="24.04"
EXPECTED_DISTRO="ubuntu"

# shellcheck source=packaging/install-common.sh
source "$DIR/packaging/install-common.sh"

main "$@"
