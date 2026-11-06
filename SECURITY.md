# Security Policy

MacroStat is a local desktop application: the Rust engine uses Linux
`evdev`/`uinput`, and the interface is built with PyQt6. **There is no network
connection, server, database, API, cookie, authentication, or password
storage.** Web application security headers (CORS, XSS filters, session
management) therefore do not apply to this project; the model below defines the
actual attack surface.

## Threat model

| Asset | Protection |
| --- | --- |
| Profile (`~/.config/macrostat/profile.json`) and `.bak` | `0600`; atomic writes (`mkstemp` + `fsync` + `os.replace`); opened by the engine with `O_NOFOLLOW` |
| Log, pid, and lock files | Private runtime directory (`XDG_RUNTIME_DIR`, otherwise `~/.cache/macrostat` 0700); `O_NOFOLLOW`, `0600` |
| Recorder temporary files | `mkstemp` under `XDG_RUNTIME_DIR`; no predictable `/tmp` names |
| Exported backups | `mkstemp` with `0600` |
| Engine binary | Fixed candidate list; no `PATH` lookup |
| udev permission | Only `TAG+="uaccess"` + `MODE="0660"`; no broad `chmod 666` or `input` group membership |
| Profile/import text | Control characters, invisible bidi/zero-width characters, and `<`/`>` are stripped; length and numeric ranges are bounded |
| Imported identifiers | Macro/profile `id` values are restricted to `[A-Za-z0-9_-]{1,64}`; invalid ones are regenerated |
| Virtual device name | Control characters removed, limited to 80 characters |
| Installation scripts | Only the distribution's own package manager is used; user input is never embedded in a shell |

Administrator privileges are used only for the user-approved `pkexec`/`sudo`
udev installation. The authorization script is fully constant: no user name or
other external value is embedded in the shell script (the `input` group /
`usermod` approach was removed).

## Known limitations

- The engine runs as the same user as the session owner so it can read `input`
  devices. An attacker with access to the same user account already has all
  privileges of the session; the application adds no additional boundary
  against this scenario.
- The profile file can be edited manually by the user. The loader sanitizes
  malformed values, but macro behavior is determined by the user.
- Keys sent through `uinput` are treated as real system-wide input.

## Reporting a vulnerability

If you find a security issue, please notify the repository owner privately
before opening a public issue. Include the version, distribution, reproduction
steps, and potential impact. A response will be provided within a reasonable
time; an acknowledgment may be added after the fix is released.

---

# Güvenlik Politikası

MacroStat yerel bir masaüstü uygulamasıdır: Rust motoru Linux `evdev`/`uinput`
kullanır, arayüz PyQt6 tabanlıdır. **Ağ bağlantısı, sunucu, veritabanı, API,
çerez, kimlik doğrulama veya parola saklama yoktur.** Bu nedenle web uygulaması
güvenlik başlıkları (CORS, XSS filtreleri, oturum yönetimi) bu proje için
geçerli değildir; aşağıdaki model gerçek saldırı yüzeyini tanımlar.

## Tehdit modeli

| Varlık | Korunma biçimi |
| --- | --- |
| Profil (`~/.config/macrostat/profile.json`) ve `.bak` | `0600`; atomik yazma (`mkstemp` + `fsync` + `os.replace`); motor `O_NOFOLLOW` ile açar |
| Günlük, pid ve kilit dosyaları | Özel çalışma dizini (`XDG_RUNTIME_DIR`, yoksa `~/.cache/macrostat` 0700); `O_NOFOLLOW`, `0600` |
| Kaydedici geçici dosyaları | `XDG_RUNTIME_DIR` altında `mkstemp`; tahmin edilebilir `/tmp` adı yok |
| Dışa aktarılan yedekler | `mkstemp` ile `0600` |
| Motor ikilisi | Sabit aday listesi; `PATH` üzerinden arama yapılmaz |
| udev izni | Yalnızca `TAG+="uaccess"` + `MODE="0660"`; geniş `chmod 666` veya `input` grubu üyeliği yok |
| Profil/içe aktarma metinleri | Denetim karakterleri, görünmez bidi/zero-width karakterler ve `<`/`>` temizlenir, uzunluk ve sayı aralıkları sınırlanır |
| İçe aktarılan kimlikler | Makro/profil `id` değerleri `[A-Za-z0-9_-]{1,64}` ile sınırlanır; geçersizler yeniden üretilir |
| Sanal aygıt adı | Denetim karakterleri ayıklanır, 80 karakterle sınırlanır |
| Kurulum betikleri | Yalnızca dağıtımın kendi paket yöneticisi kullanılır; kullanıcı girdisi kabuğa gömülmez |

Yönetici izni yalnızca kullanıcının onayladığı `pkexec`/`sudo` udev kurulumunda
kullanılır. Yetkilendirme betiği tamamen sabittir: kullanıcı adı veya başka bir
dış değer kabuk betiğine gömülmez (`input` grubu / `usermod` kaldırıldı).

## Bilinen sınırlamalar

- Motor, `input` aygıtlarını okuyabilmek için oturum sahibiyle aynı kullanıcı
  olarak çalışır. Aynı kullanıcı hesabına erişen bir saldırgan zaten oturumun
  tüm yetkilerine sahiptir; uygulama bu senaryoya karşı ek bir sınır koymaz.
- Profil dosyası kullanıcı tarafından elle düzenlenebilir. Yükleyici bozuk
  değerleri temizler, ancak makro davranışını kullanıcı belirler.
- `uinput` ile gönderilen tuşlar sistem genelinde gerçek girdi sayılır.

## Güvenlik açığı bildirimi

Güvenlik sorunu bulduysanız lütfen herkese açık bir issue açmadan önce
depo sahibine özel mesajla bildirin. Bildirimde sürüm, dağıtım, yeniden üretme
adımları ve olası etkiyi belirtin. Makul bir süre içinde yanıt verilir; düzeltme
yayınlandıktan sonra teşekkür notu eklenebilir.
