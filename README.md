# MacroStat

CachyOS / Arch Linux için düşük gecikmeli, tamamen çevrimdışı makro motoru.
Rust motoru Linux `evdev` + `uinput` kullanır; arayüz PyQt6 tabanlıdır.

## Dizin yapısı

```
Cargo.toml / Cargo.lock        Rust bağımlılıkları
src/main.rs                    Tek motor kaynağı
gui.py                         İnce giriş noktası
macrostat/                     PyQt6 arayüzü: common, widgets, mixin modülleri, i18n
assets/macrostat.svg           Uygulama simgesi
assets/default_profile.json    Tek varsayılan profil şablonu (demolar kapalı)
profile.json                   Şablonun eski yol için sembolik bağlantısı
cachymacro-daemon              Derlenmiş motor (yerel; cargo build --release)
install_all.sh                 Paket/udev kontrolü + derleme + kısayol
PKGBUILD                       Yerel Arch/CachyOS paketi (`makepkg -si`)
packaging/                     Paket başlatıcısı, .desktop ve udev kuralı
baslat-arayuz.sh               Arayüzü başlatır
build_appimage.sh              AppImage paketleyici
tests/                         Python birim testleri (unittest)
```

Kullanıcı profili: `~/.config/cachymacro/profile.json` (ilk açılışta depo
şablonundan tohumlanır). Eski tekil profiller açılışta otomatik taşınır.

## Hızlı başlangıç

```bash
sudo ./install_all.sh     # paketler + udev kuralı + release derleme
./baslat-arayuz.sh
```

Gereksinimler: Python **3.10+**, PyQt6, Rust (release derlemesi için), `libevdev`.
CI Python 3.12 ile çalışır. Varsayılan profil şablonundaki demo makrolar güvenlik
için **kapalı** gelir; etkinleştirmeden önce tetikleyiciyi kontrol edin.

Arch/CachyOS'ta paket olarak kurmak için (depo kökünde):

```bash
makepkg -si
```

`input` grubuna ekleme yapıldıysa oturumu kapatıp açın. Alternatif olarak
arayüzdeki **🛡️ Donanım İzinlerini Otomatik Düzelt (udev)** düğmesi dar
kapsamlı `pkexec` ile aynı kuralı kurar.

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
- Günlük dosyası (`/tmp/cachymacro.log`) yalnızca sahibi tarafından okunabilir
  (`0600`) ve 1 MB'ta döndürülür; uzun süre açık motorda da kendi kendine kırpılır.

## Arayüz özellikleri

- **Dil:** Üst çubuktaki **🌐** menüsünden Türkçe/English. Tercih
  `~/.config/cachymacro/settings.json` dosyasında saklanır ve arayüz yeniden
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

## Acil durdurma

Varsayılan STOP tuşu **Pause** (`KEY_PAUSE`). Profil başına `panicKey` ile
değiştirilebilir ve profille birlikte kalıcıdır. STOP sonrası motor, arayüzden
**Yeniden Başlat** düğmesine basılana kadar kapalı kalır.

## Sorun giderme

- **🔴 Motor Durduruldu / izin hatası:** `sudo ./install_all.sh` veya arayüzdeki
  udev düzeltme düğmesi; ardından oturumu yenileyin.
- **Motor bulunamadı:** `cargo build --release`; arayüz `target/release`
  çıktısını kök dizine kopyalar.
- **Günlük:** `/tmp/cachymacro.log` (1 MB üzerinde `.1` olarak döndürülür).
- **Yetim süreç/STOP sonrası takılı tuş:** Yeni motor `SIGTERM` ile temiz kapanır;
  arayüz `pkill -f` kullanmaz, yalnızca pidfile + `/proc/<pid>/exe` doğrular.

## AppImage

```bash
./build_appimage.sh
```

PyQt6 AppImage içine gömülmez; sistemde `python-pyqt6` kurulu olmalıdır.
`appimagetool` indirmesini doğrulamak için `APPIMAGETOOL_SHA256` tanımlayın.

## Lisans

Copyright (C) 2026 MacroStat contributors.

Bu proje **GNU General Public License v3.0 veya sonrası** (`GPL-3.0-or-later`)
koşulları altında dağıtılır. Tam metin: [`LICENSE`](LICENSE).
SPDX tanımlayıcısı: `GPL-3.0-or-later`.

PyQt6 GPLv3 altında dağıtıldığı için GPLv3 seçilmiştir. Kullanılan üçüncü taraf
bileşenlerin lisansları ve uyumluluk notları: [`THIRD_PARTY.md`](THIRD_PARTY.md).
