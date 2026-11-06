# MacroStat

[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)](https://www.python.org/)
[![Rust 1.75+](https://img.shields.io/badge/rust-1.75%2B-orange.svg)](https://www.rust-lang.org/)
![Platform: Linux x86_64](https://img.shields.io/badge/platform-Linux%20x86__64-lightgrey.svg)

A low-latency, fully offline macro engine for Linux. The Rust core reads and
injects input through Linux `evdev` + `uinput`; the interface is built with
PyQt6. No network access, no telemetry, no third-party services.

Ubuntu, Debian, Fedora and Arch/CachyOS are supported.

| Distribution | Minimum version | Installer |
|---|---|---|
| Ubuntu | 24.04 | `install_ubuntu.sh` |
| Debian | 13 (trixie) | `install_debian.sh` |
| Fedora | 41 | `install_fedora.sh` |
| Arch / CachyOS | rolling | `install_arch.sh` |

`install_all.sh` detects the distribution and runs the right script. Older
releases are unsupported (the PyQt6 and/or Rust packages are missing or too old).

## Repository layout

```
Cargo.toml / Cargo.lock        Rust dependencies
src/main.rs                    Single engine source
gui.py                         Thin entry point
macrostat/                     PyQt6 interface: app, common, settings, theme, widgets,
                               nav, core, macros, editor, recorder, system,
                               onboarding, logpanel, transfer, kwin, sanitize, i18n
assets/macrostat.svg           Application icon
assets/default_profile.json    Single default profile template (demos disabled)
profile.json                   Symlink kept for the legacy path
macrostat-daemon               Compiled engine (local; cargo build --release)
install_all.sh                 Detects the distribution and calls the right installer
install_{ubuntu,debian,fedora,arch}.sh  Distribution-specific installers
uninstall.sh                   Removes only the files installed by MacroStat
PKGBUILD                       Local Arch/CachyOS package (`makepkg -si`)
packaging/install-common.sh    Shared installer library (packages, udev, shortcut)
packaging/                     Package launcher, .desktop file and udev rule
start-macrostat.sh             Starts the interface
tests/                         Python unit tests (unittest)
requirements.txt               Python dependency (PyQt6)
SECURITY.md / THIRD_PARTY.md   Security model and third-party licenses
.github/workflows/             CI and release archive workflows
```

User profile: `~/.config/macrostat/profile.json` (seeded from the repository
template on first launch). Legacy single-file profiles are migrated on startup.

## Quick start

```bash
git clone https://github.com/ensargtz/Macro-Stat.git
cd Macro-Stat
./install_all.sh          # detects the distro: packages + udev + build + shortcut
./start-macrostat.sh
```

You can also run the distribution-specific script directly
(e.g. `./install_ubuntu.sh`). The installer adds a **MacroStat** shortcut to the
application menu and to the desktop; double-click the desktop icon to open the
interface. Pass `--no-desktop-shortcut` to skip the desktop shortcut and
`--skip-packages` to skip package installation. An existing `MacroStat.desktop`
that does not belong to MacroStat is never overwritten.

> **GNOME note:** GNOME does not show desktop icons by default; the shortcut is
> still created and remains reachable from the application menu. On KDE/XFCE/
> Cinnamon double-clicking works directly.

On first launch the **setup wizard** opens automatically: system status (✓/✗),
the narrowly scoped udev permission, and starting the engine. No privileged
command runs until the wizard is confirmed; on later launches the engine starts
automatically. Reopen the wizard any time via
**System & Guide → Run setup again**.

Requirements: Python **3.10+**, PyQt6 **6.5+**, Rust **1.75+** (for the release
build). No `libevdev` or `pkg-config` is required; the `evdev` crate is pure
Rust. CI runs on Python 3.12. The demo macros in the default profile ship
**disabled** for safety; check the trigger before enabling them.

To install as a package on Arch/CachyOS (repository root):

```bash
makepkg -si
```

The rule only uses `TAG+="uaccess"` + `MODE="0660"`; broad `input` group
membership or `chmod 666` is not needed. Alternatively the
**Fix Hardware Permissions Automatically (udev)** button in the interface
installs the same rule through a narrowly scoped `pkexec`.

## Engine behaviour

- Triggers are compiled at startup; they are not re-parsed on every key event.
- Left/right Ctrl, Shift, Alt and Meta are treated as equivalent.
- Combinations do not retrigger until one of the keys is released and pressed again.
- Concurrently running macros are serialised by a single execution lock; key
  state never gets mixed.
- The `TEXT` action writes **US-ASCII** characters only; unsupported characters
  (ç, ğ, ı, ö, ş, ü …) are skipped and a warning is logged once. Keyboard-layout
  mapping belongs to the compositor, so this limitation is deliberate.
- Held virtual keys are released on `SIGTERM`/`SIGINT` and on window close.
- A second engine for the same user is blocked by a `flock` lock.
- Device add/remove is detected instantly via `inotify`; the 4-second polling
  loop is only a fallback when `inotify` is unavailable.
- The log lives in a private runtime directory (`$XDG_RUNTIME_DIR/macrostat.log`,
  otherwise `~/.cache/macrostat/`), is readable only by its owner (`0600`) and
  rotates at 1 MB; it also trims itself in long-running engines.

## Interface features

- **Navigation:** **Macros**, **Macro Editor**, **Live Key Recorder** and
  **System & Guide** pages in the left sidebar. The top bar holds profile
  selection, engine status and the **STOP** button; the **⋯** menu contains
  language, theme, log and restart.
- **First-run wizard:** three steps — System Status (refreshable ✓/✗ checks),
  Fix Permissions (setup stays off without the checkbox; only the `uaccess`
  rule) and Ready (summary + option to start the engine). The result is stored
  as `onboarding_completed` in `settings.json`.
- **Live log panel:** opened as a bottom panel via **⋯ → View Log**. Text
  filter, auto-scroll, pause/resume, clear and close; visibility is persisted as
  `log_panel_visible` in `settings.json`. The panel recovers if the log is reset
  or rotated; it keeps at most 5000 lines.
- **Press/release dual action:** the **Release Actions** group in the editor
  edits the second action sequence that runs when the key is released (applies
  in `PRESS_AND_RELEASE` mode).
- **Theme:** **⋯ → Theme** offers **System / Dark / Light**; dark is the
  default, applied immediately and stored in `settings.json`. Exactly one theme
  is checked at any time.
- **Language:** **⋯ → Dil / Language** switches Turkish/English. The choice is
  stored in `~/.config/macrostat/settings.json` and the interface restarts; the
  engine is unaffected.
- **Profile management:** new profile, rename, delete and import/export from the
  top-bar **⋯** menu. The last profile cannot be deleted. Export writes either
  the active profile only or all profiles as a single JSON file.
- **Backup:** every save keeps `profile.json.bak`; the last backup can be
  restored in one click from the System tab.
- **Test macro:** the editor's test button runs the engine temporarily in
  `--test-macro` mode, including unsaved actions, without touching your real
  profile. The test engine uses a separate `MacroStat Test Engine` virtual device.
- **Live recorder:** records keyboard and mouse (buttons + wheel) events.
- **System-wide mouse path:** with the checkbox in the recorder, pointer
  movement is captured across the whole desktop through `evdev`, stored as a
  `MOUSE_PATH` action and replayed with relative deltas and timing. Recording is
  coalesced every 4 ms, the Pause key or the UI button stops it, and the limit is
  10 minutes / 200,000 points. On **X11** and **KDE Plasma Wayland** the cursor
  position at recording start is saved and the pointer is moved there before
  playback, so the path starts at the same screen position. On KDE Wayland the
  position is read through the KWin scripting interface and alignment is done
  via KWin's `org_kde_kwin_fake_input`; if neither is available (e.g. GNOME
  Wayland) the start position is not saved and playback starts from the current
  pointer position.

## Emergency stop

The default STOP key is **Pause** (`KEY_PAUSE`). It can be changed per profile
with `panicKey` and is persisted with the profile. After a STOP the engine stays
off until the **Restart** button in the interface is pressed or the assigned
restart key is hit. The restart key defaults to **F12** (`KEY_F12`), is changed
via **⋯ → Set Restart Key** and stored as `restartKey` in the profile; while the
engine is stopped, only a lightweight watcher process that reads that key runs.

## Troubleshooting

- **🔴 Engine stopped / permission error:** run `./install_all.sh` (or your
  distro's `install_*.sh`), use the udev fix button in the interface, or click
  **Run setup again**; then log out and back in.
- **Engine not found:** run `cargo build --release`; the interface copies the
  `target/release` output to the repository root.
- **Log:** `$XDG_RUNTIME_DIR/macrostat.log` (or `~/.cache/macrostat/`; rotated to
  `.1` above 1 MB).
- **Orphan process / stuck keys after STOP:** the new engine shuts down cleanly
  on `SIGTERM`; the interface never uses `pkill -f`, it verifies the pidfile plus
  `/proc/<pid>/exe`.

## Development

```bash
cargo build --release          # engine: target/release/macrostat-daemon
cargo test                     # Rust unit tests
cargo fmt --check
cargo clippy --all-targets -- -D warnings
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests   # interface tests
```

CI (`.github/workflows/ci.yml`) runs Rust fmt/clippy/test, the Rust 1.75 MSRV
build and installation verification on four distribution images (Ubuntu 24.04,
Debian trixie, Fedora 41, Arch). The version is fixed at `1.0.0`.

## Uninstall

```bash
./uninstall.sh                    # removes only what the installer added
./uninstall.sh --purge-profile    # also removes the user profile
```

The uninstaller removes only: menu/desktop shortcuts marked
`X-MacroStat-Autogenerated=true`, the icon file if it is identical to the
installed one, and the udev rule if its content matches ours. Your own
`.desktop`/icon files, the profile (unless the flag is given), logs, build
outputs and system packages are **not** removed. System packages installed with
`makepkg` belong to the package manager; remove them with
`pacman -R macrostat`.

## License

Copyright (C) 2026 MacroStat contributors.

This project is distributed under the **GNU General Public License v3.0 or
later** (`GPL-3.0-or-later`). Full text: [`LICENSE`](LICENSE).
SPDX identifier: `GPL-3.0-or-later`.

PyQt6 is distributed under GPLv3, which is why GPLv3 was chosen. Licenses of
the third-party components and compatibility notes:
[`THIRD_PARTY.md`](THIRD_PARTY.md).

Security model and disclosure process: [`SECURITY.md`](SECURITY.md).

---

# MacroStat (Türkçe)

Linux için düşük gecikmeli, tamamen çevrimdışı makro motoru.
Rust motoru Linux `evdev` + `uinput` kullanır; arayüz PyQt6 tabanlıdır.
Ubuntu, Debian, Fedora ve Arch/CachyOS desteklenir.

| Dağıtım | Asgari sürüm | Kurulum dosyası |
|---|---|---|
| Ubuntu | 24.04 | `install_ubuntu.sh` |
| Debian | 13 (trixie) | `install_debian.sh` |
| Fedora | 41 | `install_fedora.sh` |
| Arch / CachyOS | rolling | `install_arch.sh` |

`install_all.sh` dağıtımı algılayıp doğru dosyayı çalıştırır. Daha eski
sürümler desteklenmez (PyQt6 ve/veya Rust paketleri eksik ya da eski).

## Dizin yapısı

```
Cargo.toml / Cargo.lock        Rust bağımlılıkları
src/main.rs                    Tek motor kaynağı
gui.py                         İnce giriş noktası
macrostat/                     PyQt6 arayüzü: app, common, settings, theme, widgets,
                               nav, core, macros, editor, recorder, system,
                               onboarding, logpanel, transfer, kwin, sanitize, i18n
assets/macrostat.svg           Uygulama simgesi
assets/default_profile.json    Tek varsayılan profil şablonu (demolar kapalı)
profile.json                   Şablonun eski yol için sembolik bağlantısı
macrostat-daemon               Derlenmiş motor (yerel; cargo build --release)
install_all.sh                 Dağıtımı algılayıp doğru kurulumu çağırır
install_{ubuntu,debian,fedora,arch}.sh  Dağıtıma özel kurulumlar
uninstall.sh                   Yalnızca MacroStat'ın kurduğu dosyaları kaldırır
PKGBUILD                       Yerel Arch/CachyOS paketi (`makepkg -si`)
packaging/install-common.sh    Ortak kurulum kütüphanesi (paket, udev, kısayol)
packaging/                     Paket başlatıcısı, .desktop ve udev kuralı
start-macrostat.sh             Arayüzü başlatır
tests/                         Python birim testleri (unittest)
requirements.txt               Python bağımlılığı (PyQt6)
SECURITY.md / THIRD_PARTY.md   Güvenlik modeli ve üçüncü taraf lisansları
.github/workflows/             CI ve sürüm arşivi iş akışları
```

Kullanıcı profili: `~/.config/macrostat/profile.json` (ilk açılışta depo
şablonundan tohumlanır). Eski tekil profiller açılışta otomatik taşınır.

## Hızlı başlangıç

```bash
git clone https://github.com/ensargtz/Macro-Stat.git
cd Macro-Stat
./install_all.sh          # dağıtımı algılar: paketler + udev + derleme + kısayol
./start-macrostat.sh
```

Dağıtıma özel dosyayı doğrudan da çalıştırabilirsiniz (ör. `./install_ubuntu.sh`).
Kurulum sonunda uygulama menüsüne ve masaüstüne **MacroStat** kısayolu eklenir;
masaüstü simgesine çift tıklayarak arayüzü açabilirsiniz. Masaüstü kısayolu
istenmiyorsa `--no-desktop-shortcut`, paket kurulumu atlanacaksa
`--skip-packages` kullanın. Var olan ve MacroStat'a ait olmayan
`MacroStat.desktop` dosyası asla ezilmez.

> **GNOME notu:** GNOME masaüstü simgeleri varsayılan olarak göstermez; kısayol
> yine de oluşturulur ve uygulama menüsünden erişilebilir. KDE/XFCE/Cinnamon
> gibi masaüstlerinde çift tıklama doğrudan çalışır.

İlk açılışta **kurulum sihirbazı** kendiliğinden açılır: sistem durumu (✓/✗),
dar kapsamlı udev izni ve motoru başlatma. Sihirbaz onaylanmadan hiçbir yetki
komutu çalışmaz; sonraki açılışlarda motor otomatik başlar. Sihirbazı daha sonra
**Sistem & Kılavuz → Kurulumu yeniden çalıştır** ile tekrar açabilirsiniz.

Gereksinimler: Python **3.10+**, PyQt6 **6.5+**, Rust **1.75+** (release derlemesi
için). Sistemde ayrıca `libevdev` veya `pkg-config` gerekmez; `evdev` crate'i saf
Rust'tır. CI Python 3.12 ile çalışır. Varsayılan profil şablonundaki demo makrolar güvenlik
için **kapalı** gelir; etkinleştirmeden önce tetikleyiciyi kontrol edin.

Arch/CachyOS'ta paket olarak kurmak için (depo kökünde):

```bash
makepkg -si
```

Kural yalnızca `TAG+="uaccess"` + `MODE="0660"` kullanır; geniş `input` grubu
üyeliği veya `chmod 666` gerekmez. Alternatif olarak arayüzdeki
**Donanım İzinlerini Otomatik Düzelt (udev)** düğmesi dar kapsamlı `pkexec`
ile aynı kuralı kurar.

## Motor davranışı

- Tetikleyiciler açılışta derlenir; her tuş olayında yeniden ayrıştırılmaz.
- Sol/sağ Ctrl, Shift, Alt, Meta eşdeğer kabul edilir.
- Kombinasyonlar, tuşlardan biri bırakılıp yeniden basılmadıkça tekrar ateşlenmez.
- Aynı anda çalışan makrolar tek yürütme kilidiyle serileştirilir; tuş durumu karışmaz.
- `TEXT` eylemi yalnızca **US-ASCII** karakterleri yazar; desteklenmeyen karakterler
  (ç, ğ, ı, ö, ş, ü gibi) atlanır ve günlüğe bir kez uyarı düşülür. Klavye düzeni
  eşlemesi kompozitöre ait olduğundan bu sınırlama bilinçlidir.
- `SIGTERM`/`SIGINT` ve pencere kapanışında basılı sanal tuşlar serbest bırakılır.
- Aynı kullanıcı için ikinci motor `flock` kilidiyle engellenir.
- Aygıt ekleme/çıkarma `inotify` ile anında algılanır; 4 saniyelik yoklama
  yalnızca `inotify` kullanılamıyorsa yedek olarak devreye girer.
- Günlük dosyası özel çalışma dizininde (`$XDG_RUNTIME_DIR/macrostat.log`,
  yoksa `~/.cache/macrostat/`) tutulur, yalnızca sahibi okuyabilir (`0600`) ve
  1 MB'ta döndürülür; uzun süre açık motorda da kendi kendine kırpılır.

## Arayüz özellikleri

- **Gezinme:** Sol kenar çubuğundan **Makrolar**, **Makro Düzenleyici**,
  **Canlı Tuş Kaydedici** ve **Sistem & Kılavuz** sayfaları. Üst çubukta
  profil seçimi, motor durumu ve **STOP** düğmesi; **⋯** menüsünde dil, tema,
  günlük ve yeniden başlatma.
- **İlk kurulum sihirbazı:** Üç adım — Sistem Durumu (yenilenebilir ✓/✗
  denetimleri), İzinleri Düzelt (onay kutusu olmadan kurulum kapalı, yalnızca
  yalnızca `uaccess` kuralı) ve Hazır (özet + motoru başlatma seçeneği).
  Sonuç `settings.json` içindeki `onboarding_completed` ile saklanır.
- **Canlı günlük paneli:** **⋯ → Günlüğü İncele** ile alt panelde açılır.
  Metin filtresi, otomatik kaydırma, duraklat/devam, temizle ve kapat; panel
  görünürlüğü `settings.json` içindeki `log_panel_visible` ile korunur. Günlük
  sıfırlanır veya döndürülürse panel kendini toparlar; en fazla 5000 satır tutar.
- **Bas-bırak çift eylemi:** Düzenleyicide **Bırakma Eylemleri** grubu, tuş
  bırakıldığında çalışacak ikinci eylem sırasını düzenler
  (`PRESS_AND_RELEASE` modunda geçerlidir).
- **Tema:** **⋯ → Tema** menüsünden **Sistem / Koyu / Açık**; varsayılan koyudur,
  seçim anında uygulanır ve `settings.json` içinde saklanır. Menüde her an
  yalnızca etkin temanın işareti görünür.
- **Dil:** **⋯ → Dil / Language** menüsünden Türkçe/English. Tercih
  `~/.config/macrostat/settings.json` dosyasında saklanır ve arayüz yeniden
  başlatılır; motor etkilenmez.
- **Profil yönetimi:** Üst çubuktaki **⋯** menüsünden yeni profil, yeniden
  adlandırma, silme ve içe/dışa aktarma. Son profil silinemez. Dışa aktarmada
  yalnızca aktif profil veya tüm profiller tek JSON olarak yazılır.
- **Yedek:** Her kayıtta `profile.json.bak` tutulur; sistem sekmesinden son yedek
  tek tıkla geri yüklenebilir.
- **Makroyu test et:** Düzenleyicideki test düğmesi, kaydedilmemiş eylemleri dâhil
  ederek motoru `--test-macro` modunda geçici olarak çalıştırır; gerçek profilinize
  dokunmaz. Test motoru ayrı bir `MacroStat Test Engine` sanal aygıtı kullanır.
- **Canlı kaydedici:** Klavye ve fare (düğme + tekerlek) olaylarını kaydeder.
- **Sistem geneli fare yolu:** Kaydedicideki onay kutusuyla fare hareketi tüm
  masaüstünde `evdev` üzerinden kaydedilir; `MOUSE_PATH` eylemi olarak saklanır ve
  göreli delta + zamanlama ile yeniden oynatılır. Kayıt 4 ms'te bir birleştirilir,
  Pause tuşu veya arayüz düğmesi durdurur; üst sınır 10 dakika / 200.000 noktadır.
  **X11** oturumunda ve **KDE Plasma Wayland**'da kaydın başladığı imleç konumu
  saklanır ve oynatma başında imleç oraya taşınır; böylece yol ekranda aynı
  noktadan başlar. KDE Wayland'da konum KWin betik arayüzünden okunur,
  hizalama ise KWin'in `org_kde_kwin_fake_input` arayüzüyle yapılır; ikisi de
  yoksa (ör. GNOME Wayland) başlangıç noktası kaydedilmez ve oynatma imlecin o
  anki konumundan başlar.

## Acil durdurma

Varsayılan STOP tuşu **Pause** (`KEY_PAUSE`). Profil başına `panicKey` ile
değiştirilebilir ve profille birlikte kalıcıdır. STOP sonrası motor, arayüzden
**Yeniden Başlat** düğmesine ya da atanmış yeniden başlatma tuşuna basılana
kadar kapalı kalır. Yeniden başlatma tuşu varsayılan **F12** (`KEY_F12`) olup
**⋯ → Yeniden Başlatma Tuşunu Ayarla** ile değiştirilir ve profil içinde
`restartKey` olarak saklanır; STOP sırasında yalnızca bu tuşu okuyan hafif bir
izleyici süreci çalışır.

## Sorun giderme

- **🔴 Motor Durduruldu / izin hatası:** `./install_all.sh` (veya dağıtımınıza
  özel `install_*.sh`), arayüzdeki udev düzeltme düğmesi ya da **Kurulumu
  yeniden çalıştır**; ardından oturumu yenileyin.
- **Motor bulunamadı:** `cargo build --release`; arayüz `target/release`
  çıktısını kök dizine kopyalar.
- **Günlük:** `$XDG_RUNTIME_DIR/macrostat.log` (veya `~/.cache/macrostat/`;
  1 MB üzerinde `.1` olarak döndürülür).
- **Yetim süreç/STOP sonrası takılı tuş:** Yeni motor `SIGTERM` ile temiz kapanır;
  arayüz `pkill -f` kullanmaz, yalnızca pidfile + `/proc/<pid>/exe` doğrular.

## Geliştirme

```bash
cargo build --release          # motor: target/release/macrostat-daemon
cargo test                     # Rust birim testleri
cargo fmt --check
cargo clippy --all-targets -- -D warnings
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests   # arayüz testleri
```

CI (`.github/workflows/ci.yml`) Rust biçim/clippy/test, Rust 1.75 MSRV
derlemesi ve dört dağıtım imajında (Ubuntu 24.04, Debian trixie, Fedora 41,
Arch) kurulum doğrulamasını çalıştırır. Sürüm `1.0.0` olarak sabittir.

## Kaldırma

```bash
./uninstall.sh                    # yalnızca kurulumun eklediklerini siler
./uninstall.sh --purge-profile    # kullanıcı profilini de siler
```

Kaldırma betiği yalnızca şunları siler: `X-MacroStat-Autogenerated=true`
işaretli menü/masaüstü kısayolları, kurulumla birebir aynı olan simge dosyası ve
içeriği bizimkiyle eşleşen udev kuralı. Kullanıcının kendi `.desktop`/simge
dosyaları, profil (bayrak verilmedikçe), günlükler, derleme çıktıları ve sistem
paketleri **silinmez**. `makepkg` ile kurulan sistem paketleri paket
yöneticisine aittir; onları `pacman -R macrostat` ile kaldırın.

## Lisans

Copyright (C) 2026 MacroStat contributors.

Bu proje **GNU General Public License v3.0 veya sonrası** (`GPL-3.0-or-later`)
koşulları altında dağıtılır. Tam metin: [`LICENSE`](LICENSE).
SPDX tanımlayıcısı: `GPL-3.0-or-later`.

PyQt6 GPLv3 altında dağıtıldığı için GPLv3 seçilmiştir. Kullanılan üçüncü taraf
bileşenlerin lisansları ve uyumluluk notları: [`THIRD_PARTY.md`](THIRD_PARTY.md).

Güvenlik modeli ve açık bildirim süreci: [`SECURITY.md`](SECURITY.md).
