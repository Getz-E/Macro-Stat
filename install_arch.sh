#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
# Arch Linux / CachyOS / EndeavourOS / Manjaro installation entry point.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

DISTRO_FAMILY="arch"
DISTRO_LABEL="Arch Linux / CachyOS (rolling)"
DISTRO_MIN_VERSION=""
EXPECTED_DISTRO="arch"

# shellcheck source=packaging/install-common.sh
source "$DIR/packaging/install-common.sh"

main "$@"
