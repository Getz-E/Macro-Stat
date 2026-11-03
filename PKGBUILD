# Maintainer: MacroStat contributors
# Yerel paket: repo kökündeki PKGBUILD ile `makepkg -si` çalıştırılır.
# GitHub yayını sonrası AUR için `source=()` yerine sürüm tarball'ı kullanılmalıdır.
pkgname=macrostat
pkgver=1.0.0
pkgrel=1
pkgdesc="Low-latency Linux macro engine (evdev/uinput) with a PyQt6 interface"
arch=('x86_64')
url="https://github.com/ensargtz/Macro-Stat"
license=('GPL-3.0-or-later')
depends=('python' 'python-pyqt6' 'libevdev')
makedepends=('rust' 'cargo' 'pkgconf')
source=()
sha256sums=()

# Depo kökündeki src/ (Rust kaynağı) ile çakışmaması için ayrı çalışma dizini.
BUILDDIR="$startdir/.makepkg"

build() {
    cd "$startdir"
    cargo build --release --locked
}

package() {
    cd "$startdir"

    install -Dm755 target/release/cachymacro-daemon \
        "$pkgdir/usr/bin/cachymacro-daemon"
    install -Dm755 packaging/macrostat "$pkgdir/usr/bin/macrostat"

    install -Dm644 gui.py "$pkgdir/usr/lib/macrostat/gui.py"
    install -d "$pkgdir/usr/lib/macrostat/macrostat"
    install -m644 macrostat/*.py "$pkgdir/usr/lib/macrostat/macrostat/"
    install -Dm644 assets/default_profile.json \
        "$pkgdir/usr/lib/macrostat/assets/default_profile.json"
    install -Dm644 assets/macrostat.svg \
        "$pkgdir/usr/share/icons/hicolor/scalable/apps/macrostat.svg"
    install -Dm644 packaging/macrostat.desktop \
        "$pkgdir/usr/share/applications/macrostat.desktop"
    install -Dm644 packaging/99-cachymacro.rules \
        "$pkgdir/usr/lib/udev/rules.d/99-cachymacro.rules"
}
