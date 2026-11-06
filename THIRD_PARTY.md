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
| `wayland-client` | 0.31 | MIT |
| `wayland-scanner` | 0.31 | MIT |

## Protocol tanımı

| Dosya | Kaynak | Lisans |
|---|---|---|
| `protocols/fake-input.xml` | `plasma-wayland-protocols` (`org_kde_kwin_fake_input`) | LGPL-2.1-or-later |

Bu protokol yalnızca KDE Wayland'da imleci mutlak konuma taşımak için kullanılır;
LGPL-2.1 metni GPL-3.0-or-later ile uyumludur (LGPLv2.1 §3 ile GPLv3'e yükseltilebilir).

## Dolaylı Rust bağımlılıkları

`Cargo.lock` içindeki tüm geçişli paketler şu lisans ailelerinden birini kullanır:
**MIT**, **Apache-2.0**, **BSD-2-Clause**, **Unlicense**, **Unicode-3.0** veya
**Apache-2.0 WITH LLVM-exception**. Tam liste ve sürümler `Cargo.lock` içinde sabitlenmiştir;
lisans metinleri `cargo about` / `cargo deny` ile üretilebilir.

## Arayüz ve sistem bileşenleri

| Bileşen | Lisans | Not |
|---|---|---|
| PyQt6 / PyQt6-Qt6 | GPL-3.0 | PyQt6 GPLv3 altında dağıtılır; bu nedenle MacroStat GPL-3.0-or-later'dır. Ticari PyQt lisansı kullanılıyorsa bu kısıt kalkar. |
| Qt 6 (sistem kütüphaneleri) | LGPL-3.0 / GPL-3.0 | Sistemde dinamik olarak bağlanır; MacroStat ile birlikte paketlenmez. |
| Linux çekirdeği `evdev` / `uinput` | GPL-2.0 (çekirdek) | Yalnızca çekirdek API'si kullanılır; çekirdek kodu dağıtılmaz. |

## Paketleme notu

Kurulum betikleri yalnızca MacroStat'ın kendi ikilisini ve betiklerini kurar.
PyQt6 ve Qt6 sistem paketi olarak kurulur; MacroStat ile birlikte paketlenmez ve
kendi lisansları altında dağıtılmaya devam eder.
