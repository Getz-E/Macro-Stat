#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
# Fedora 41+ installation entry point (python3-pyqt6 6.7+, rust 1.83+).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

DISTRO_FAMILY="fedora"
DISTRO_LABEL="Fedora 41+"
DISTRO_MIN_VERSION="41"
EXPECTED_DISTRO="fedora"

# shellcheck source=packaging/install-common.sh
source "$DIR/packaging/install-common.sh"

main "$@"
