#!/bin/bash
# ==============================================================================
# MacroStat - Otomatik AppImage Paketleyici (CachyOS / Arch Linux)
# Her şey tek bir taşınabilir AppImage dosyasında kutudan çıktığı gibi çalışır
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

echo "🚀 [1/4] Paketleme araçları kontrol ediliyor..."
if command -v pacman &> /dev/null; then
    sudo pacman -S --needed --noconfirm rust cargo libevdev pkgconf python python-pyqt6 wget || true
fi

APPDIR="$DIR/MacroStat.AppDir"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/scalable/apps"

echo "⚙️ [2/4] Rust makro motoru derleniyor..."
if [ -f "cachymacro/Cargo.toml" ]; then
    (cd cachymacro && cargo build --release)
    cp cachymacro/target/release/cachymacro-daemon "$APPDIR/usr/bin/"
elif [ -f "Cargo.toml" ]; then
    cargo build --release
    cp target/release/cachymacro-daemon "$APPDIR/usr/bin/"
fi
chmod +x "$APPDIR/usr/bin/cachymacro-daemon"

echo "📁 [3/4] Python GUI ve masaüstü bileşenleri hazırlanıyor..."
if [ -f "cachymacro/gui.py" ]; then
    cp cachymacro/gui.py "$APPDIR/usr/bin/"
    cp cachymacro/profile.json "$APPDIR/usr/bin/" 2>/dev/null || true
else
    cp gui.py "$APPDIR/usr/bin/"
    cp profile.json "$APPDIR/usr/bin/" 2>/dev/null || true
fi
chmod +x "$APPDIR/usr/bin/gui.py"

cat << 'EOF' > "$APPDIR/macrostat.desktop"
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

cat << 'EOF' > "$APPDIR/macrostat.svg"
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0b0f19" />
      <stop offset="100%" stop-color="#0284c7" />
    </linearGradient>
  </defs>
  <rect width="128" height="128" rx="28" fill="url(#bg)" />
  <circle cx="64" cy="64" r="46" fill="none" stroke="#38bdf8" stroke-width="4" stroke-dasharray="6 4" />
  <path d="M48 40 L88 64 L48 88 Z" fill="#38bdf8" />
  <circle cx="64" cy="64" r="8" fill="#10b981" />
</svg>
EOF
cp "$APPDIR/macrostat.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/"
cp "$APPDIR/macrostat.svg" "$APPDIR/.DirIcon"

cat << 'EOF' > "$APPDIR/AppRun"
#!/bin/bash
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
export APPDIR="$SELF_DIR"
export PATH="$SELF_DIR/usr/bin:$PATH"

# Kalıcı kullanıcı ayarları: ~/.config/cachymacro
mkdir -p "$HOME/.config/cachymacro"
if [ ! -f "$HOME/.config/cachymacro/profile.json" ] && [ -f "$SELF_DIR/usr/bin/profile.json" ]; then
    cp "$SELF_DIR/usr/bin/profile.json" "$HOME/.config/cachymacro/profile.json"
fi

# Donanım izin kontrolü
if [ ! -w /dev/uinput ] || [ ! -r /dev/input/event0 ]; then
    if command -v pkexec &>/dev/null; then
        pkexec sh -c 'modprobe uinput 2>/dev/null; chmod 666 /dev/uinput /dev/input/event* 2>/dev/null; usermod -aG input "$USER" 2>/dev/null' 2>/dev/null || true
    fi
fi

trap "pkill -9 -f cachymacro-daemon 2>/dev/null || true" EXIT INT TERM
exec python3 "$SELF_DIR/usr/bin/gui.py" "$@"
EOF
chmod +x "$APPDIR/AppRun"

echo "📦 [4/4] AppImage oluşturuluyor..."
if ! command -v appimagetool &> /dev/null; then
    if [ ! -f "appimagetool" ]; then
        echo "⬇️ appimagetool indiriliyor..."
        wget -q -O appimagetool https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage || curl -sL -o appimagetool https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
        chmod +x appimagetool
    fi
    ARCH=x86_64 ./appimagetool "$APPDIR" MacroStat-x86_64.AppImage
else
    ARCH=x86_64 appimagetool "$APPDIR" MacroStat-x86_64.AppImage
fi

chmod +x MacroStat-x86_64.AppImage
echo "🎉 [BAŞARILI] 'MacroStat-x86_64.AppImage' oluşturuldu!"
echo "Çalıştırmak için: ./MacroStat-x86_64.AppImage"
