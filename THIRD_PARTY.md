# Üçüncü Taraf Bileşenler ve Lisansları

MacroStat'ın kendi kaynak kodu **GPL-3.0-or-later** ile lisanslanmıştır (bkz. `LICENSE`).
Aşağıdaki bileşenler bu lisansla uyumludur; hiçbiri GPLv3 ile çelişen bir koşul taşımaz.

## Doğrudan Rust bağımlılıkları

| Paket | Sürüm | Lisans |
|---|---|---|
| `evdev` | 0.12.2 | Apache-2.0 OR MIT |
| `libc` | 0.2.191 | MIT OR Apache-2.0 |
| `rand` | 0.8.8 | MIT OR Apache-2.0 |
| `serde` | 1.0.229 | MIT OR Apache-2.0 |
| `serde_json` | 1.0.154 | MIT OR Apache-2.0 |

## Dolaylı Rust bağımlılıkları

`Cargo.lock` içindeki tüm geçişli paketler şu lisans ailelerinden birini kullanır:
**MIT**, **Apache-2.0**, **BSD-2-Clause**, **Unlicense**, **Unicode-3.0** veya
**Apache-2.0 WITH LLVM-exception**. Tam liste ve sürümler `Cargo.lock` içinde sabitlenmiştir;
lisans metinleri `cargo about` / `cargo deny` ile üretilebilir.

## Arayüz ve sistem bileşenleri

| Bileşen | Lisans | Not |
|---|---|---|
| PyQt6 / PyQt6-Qt6 | GPL-3.0 | PyQt6 GPLv3 altında dağıtılır; bu nedenle MacroStat GPL-3.0-or-later'dır. Ticari PyQt lisansı kullanılıyorsa bu kısıt kalkar. |
| Qt 6 (sistem kütüphaneleri) | LGPL-3.0 / GPL-3.0 | Sistemde dinamik olarak bağlanır; AppImage içine gömülmez. |
| Linux çekirdeği `evdev` / `uinput` | GPL-2.0 (çekirdek) | Yalnızca çekirdek API'si kullanılır; çekirdek kodu dağıtılmaz. |

## Paketleme notu

`build_appimage.sh` yalnızca MacroStat'ın kendi ikilisini ve betiklerini paketler.
PyQt6 ve Qt6 sistemde kurulu olmalıdır; bu bağımlılıklar AppImage'a gömülmez ve
kendi lisansları altında dağıtılmaya devam eder.
