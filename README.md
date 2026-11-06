# MacroStat

[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab.svg)](https://www.python.org/)
[![Rust 1.75+](https://img.shields.io/badge/rust-1.75%2B-orange.svg)](https://www.rust-lang.org/)
![Platform: Linux x86_64](https://img.shields.io/badge/platform-Linux%20x86__64-lightgrey.svg)

Linux için düşük gecikmeli, tamamen çevrimdışı makro motoru.
Rust motoru Linux `evdev` + `uinput` kullanır; arayüz PyQt6 tabanlıdır.
Ubuntu, Debian, Fedora ve Arch/CachyOS desteklenir.

> **English summary:** MacroStat is a low-latency, fully offline macro engine
> for Linux. The Rust core reads and injects input through `evdev`/`uinput`;
> the PyQt6 interface manages profiles, the visual editor, the live recorder
> and the engine lifecycle. No network access, no telemetry, no third-party
> services. Install with `./install_all.sh` and start with
> `./start-macrostat.sh`. Licensed GPL-3.0-or-later.

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
