#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
# ==============================================================================
# MacroStat - CachyOS / Arch Linux ince kurulum betiği
# Gömülü kaynak içermez; mevcut proje ağacını doğrular, derler ve izinleri kurar.
# ==============================================================================
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo "🚀 [1/6] Sistem paketleri kontrol ediliyor..."
if command -v pacman >/dev/null 2>&1; then
    missing=()
    for pkg in rust cargo python python-pyqt6 libevdev pkgconf; do
        pacman -Q "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
    done
    if [ ${#missing[@]} -gt 0 ]; then
        echo "   Eksik paketler: ${missing[*]}"
        sudo pacman -S --needed --noconfirm "${missing[@]}"
    else
        echo "   Tüm paketler kurulu."
    fi
else
    echo "   pacman bulunamadı; paket kurulumu atlandı."
fi

echo "📁 [2/6] Proje dosyaları doğrulanıyor..."
for f in Cargo.toml src/main.rs gui.py profile.json baslat-arayuz.sh \
         macrostat/__init__.py macrostat/i18n.py macrostat/settings.py \
         assets/macrostat.svg; do
    if [ ! -f "$f" ]; then
        echo "❌ Eksik dosya: $f" >&2
        exit 1
    fi
done
echo "   Dosya yapısı geçerli (kök dizin kanonik)."

echo "🛡️ [3/6] udev donanım izin kuralı tanımlanıyor..."
TARGET_USER="${SUDO_USER:-$USER}"
sudo modprobe uinput 2>/dev/null || true
# MODE 0666 yerine yalnızca oturum sahibine (uaccess) ve input grubuna izin verilir.
sudo tee /etc/udev/rules.d/99-cachymacro.rules >/dev/null <<'EOF'
KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput", GROUP="input", MODE="0660"
SUBSYSTEM=="input", KERNEL=="event*", TAG+="uaccess", GROUP="input", MODE="0660"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger
if ! id -nG "$TARGET_USER" | tr ' ' '\n' | grep -qx input; then
    sudo usermod -aG input "$TARGET_USER"
    echo "   '$TARGET_USER' input grubuna eklendi. Etkin olması için oturumu kapatıp açın."
fi

echo "⚙️ [4/6] Rust makro motoru derleniyor (release)..."
cargo build --release
cp target/release/cachymacro-daemon ./cachymacro-daemon
chmod +x ./cachymacro-daemon ./baslat-arayuz.sh ./build_appimage.sh

echo "🖥️ [5/6] Masaüstü kısayolu ve simge kuruluyor..."
USER_HOME="$(getent passwd "$TARGET_USER" 2>/dev/null | awk -F: '{print $6}')"
[ -n "$USER_HOME" ] || USER_HOME="$HOME"
APPS_DIR="$USER_HOME/.local/share/applications"
ICON_DIR="$USER_HOME/.local/share/icons/hicolor/scalable/apps"

as_user() {
    if [ "$(id -un)" = "$TARGET_USER" ]; then
        "$@"
    else
        sudo -u "$TARGET_USER" "$@"
    fi
}

as_user mkdir -p "$APPS_DIR" "$ICON_DIR"
as_user install -m 644 assets/macrostat.svg "$ICON_DIR/macrostat.svg"

TMP_DESKTOP="$(mktemp)"
trap 'rm -f "$TMP_DESKTOP"' EXIT
cat >"$TMP_DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=MacroStat
Comment=Low-latency hardware macro engine
Exec="$DIR/baslat-arayuz.sh"
Icon=macrostat
Terminal=false
Categories=Utility;Game;
StartupWMClass=MacroStat
EOF
as_user install -m 644 "$TMP_DESKTOP" "$APPS_DIR/macrostat.desktop"
rm -f "$TMP_DESKTOP"
trap - EXIT

if command -v update-desktop-database >/dev/null 2>&1; then
    as_user update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
fi
echo "   Kısayol: $APPS_DIR/macrostat.desktop (Exec: $DIR/baslat-arayuz.sh)"

echo "✅ [6/6] Kurulum tamamlandı."
echo "   Arayüzü başlatmak için: ./baslat-arayuz.sh"
