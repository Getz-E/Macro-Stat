#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
# ==============================================================================
# MacroStat - AppImage paketleyici (CachyOS / Arch Linux)
# Tek kanonik kök dizin yapısını kullanır.
# Not: PyQt6 AppImage içine gömülmez; sistemde kurulu olmalıdır.
# ==============================================================================
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo "🚀 [1/4] Paketleme araçları kontrol ediliyor..."
if command -v pacman >/dev/null 2>&1; then
    missing=()
    for pkg in rust cargo python python-pyqt6 libevdev pkgconf wget; do
        pacman -Q "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
    done
    if [ ${#missing[@]} -gt 0 ]; then
        sudo pacman -S --needed --noconfirm "${missing[@]}"
    fi
fi
if ! python3 -c 'import PyQt6' >/dev/null 2>&1; then
    echo "❌ PyQt6 bulunamadı. AppImage sistemdeki PyQt6 ile çalışır: sudo pacman -S python-pyqt6" >&2
    exit 1
fi

APPDIR="$DIR/MacroStat.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" \
         "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/scalable/apps"

echo "⚙️ [2/4] Rust makro motoru derleniyor..."
cargo build --release
cp target/release/cachymacro-daemon "$APPDIR/usr/bin/"
chmod +x "$APPDIR/usr/bin/cachymacro-daemon"

echo "📁 [3/4] Python GUI ve masaüstü bileşenleri hazırlanıyor..."
cp gui.py "$APPDIR/usr/bin/"
# Yalnızca kaynak dosyalar: __pycache__ / bayat .pyc pakete girmesin.
install -d "$APPDIR/usr/bin/macrostat"
cp macrostat/*.py "$APPDIR/usr/bin/macrostat/"
cp -r assets "$APPDIR/usr/bin/"
cp profile.json "$APPDIR/usr/bin/"
chmod +x "$APPDIR/usr/bin/gui.py"

cat <<'EOF' >"$APPDIR/macrostat.desktop"
[Desktop Entry]
Name=MacroStat
Comment=CachyOS Low-Latency Hardware Macro Engine
Exec=AppRun
Icon=macrostat
Type=Application
Categories=Utility;Game;
Terminal=false
StartupWMClass=MacroStat
EOF
cp "$APPDIR/macrostat.desktop" "$APPDIR/usr/share/applications/"

cp assets/macrostat.svg "$APPDIR/macrostat.svg"
cp "$APPDIR/macrostat.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/"
cp "$APPDIR/macrostat.svg" "$APPDIR/.DirIcon"

cat <<'EOF' >"$APPDIR/AppRun"
#!/bin/bash
set -euo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
export APPDIR="$SELF_DIR"
export PATH="$SELF_DIR/usr/bin:$PATH"

mkdir -p "$HOME/.config/cachymacro"
if [ ! -f "$HOME/.config/cachymacro/profile.json" ]; then
    if [ -f "$SELF_DIR/usr/bin/assets/default_profile.json" ]; then
        cp "$SELF_DIR/usr/bin/assets/default_profile.json" "$HOME/.config/cachymacro/profile.json"
    elif [ -f "$SELF_DIR/usr/bin/profile.json" ]; then
        cp "$SELF_DIR/usr/bin/profile.json" "$HOME/.config/cachymacro/profile.json"
    fi
fi

# İzinler udev kuralıyla verilir (chmod 666 kullanılmaz).
if [ ! -w /dev/uinput ]; then
    echo "⚠️ /dev/uinput yazılabilir değil. 'sudo ./install_all.sh' ile udev kuralını kurun ve oturumu yenileyin."
fi

exec python3 "$SELF_DIR/usr/bin/gui.py" "$@"
EOF
chmod +x "$APPDIR/AppRun"

echo "📦 [4/4] AppImage oluşturuluyor..."
TOOL=""
if command -v appimagetool >/dev/null 2>&1; then
    TOOL="$(command -v appimagetool)"
elif [ -x "$DIR/appimagetool" ]; then
    TOOL="$DIR/appimagetool"
else
    echo "⬇️ appimagetool indiriliyor..."
    URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
    if command -v wget >/dev/null 2>&1; then
        wget -q -O "$DIR/appimagetool" "$URL"
    else
        curl -sL -o "$DIR/appimagetool" "$URL"
    fi
    if [ -n "${APPIMAGETOOL_SHA256:-}" ]; then
        echo "${APPIMAGETOOL_SHA256}  $DIR/appimagetool" | sha256sum -c -
    else
        echo "ℹ️ APPIMAGETOOL_SHA256 tanımlı değil; indirilen araç doğrulanmadı."
    fi
    chmod +x "$DIR/appimagetool"
    TOOL="$DIR/appimagetool"
fi

ARCH=x86_64 "$TOOL" "$APPDIR" MacroStat-x86_64.AppImage
chmod +x MacroStat-x86_64.AppImage
echo "🎉 [BAŞARILI] 'MacroStat-x86_64.AppImage' oluşturuldu!"
echo "Çalıştırmak için: ./MacroStat-x86_64.AppImage (sistemde PyQt6 kurulu olmalıdır)"
