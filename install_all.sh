#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
# ==============================================================================
# MacroStat distribution router.
# Detects the distribution and runs the matching install script:
#   install_ubuntu.sh  — Ubuntu 24.04+
#   install_debian.sh  — Debian 13+
#   install_fedora.sh  — Fedora 41+
#   install_arch.sh    — Arch / CachyOS (rolling)
# All arguments are passed through to the selected script.
# ==============================================================================
set -euo pipefail

# Depo tarafından denetlenen yardımcı kütüphaneyi yüklemeden önce kök
# çalıştırmayı reddet. Kurulum yalnızca normal kullanıcı olarak çalışır;
# betik paket ve udev adımlarını kendisi yükseltir.
if [ "$(id -u)" -eq 0 ]; then
    printf '❌ Do not run this installer as root. Run it as your regular user; the script elevates only package and udev steps.\n' >&2
    exit 1
fi

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"

# shellcheck source=packaging/install-common.sh
source "$DIR/packaging/install-common.sh"

family="$(detect_family)"
case "$family" in
    ubuntu) exec "$DIR/install_ubuntu.sh" "$@" ;;
    debian) exec "$DIR/install_debian.sh" "$@" ;;
    fedora) exec "$DIR/install_fedora.sh" "$@" ;;
    arch)   exec "$DIR/install_arch.sh" "$@" ;;
    *)
        printf "❌ Unsupported distribution: %s\n" "$family" >&2
        exit 1
        ;;
esac
