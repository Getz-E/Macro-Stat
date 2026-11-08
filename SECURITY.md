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
| Engine binary | Fixed candidate list; no `PATH` lookup; only a trusted user/root-owned binary with safe ancestors is selected |
| Privileged helpers (`pkexec`/`sudo`, `sh`, `modprobe`, `cat`, `udevadm`) | Fixed root-owned directories; no `PATH` lookup; every path and symlink component plus POSIX ACL write grants are checked |
| udev permission | Only `TAG+="uaccess"` + `MODE="0660"`; no broad `chmod 666` or `input` group membership |
| Profile/import text | Control characters, invisible bidi/zero-width characters, and `<`/`>` are stripped; length and numeric ranges are bounded |
| Imported identifiers | Macro/profile `id` values are restricted to `[A-Za-z0-9_-]{1,64}`; invalid ones are regenerated |
| Virtual device name | Control characters removed, limited to 80 characters |
| Installation scripts | Only the distribution's own package manager is used; user input is never embedded in a shell |

Administrator privileges are used only for the user-approved `pkexec`/`sudo`
udev installation. The authorization script is fully constant: no user name or
other external value is embedded in the shell script (the `input` group /
`usermod` approach was removed).

### Filesystem and execution assumptions

Executable paths are validated component by component, without `PATH` lookup:
the file, its direct parent, every higher directory, and every intermediate
symlink container must be owned by the trusted user or root and must not be
group/world-writable (sticky higher directories such as `/tmp` are accepted
only above the direct parent). POSIX ACLs are read through
`system.posix_acl_access`; an effective write grant to an untrusted named user
or group is rejected. Missing POSIX ACL support is treated as "no ACL", while
unreadable or malformed ACL data fails closed.

These checks rely on kernel-reported ownership, mode bits, and the POSIX ACL
xattr. On FUSE or network filesystems (for example NFSv4, whose ACLs are not
exposed as `system.posix_acl_access`) this metadata may be synthetic,
incomplete, or absent, so the same trust guarantee cannot be established;
trusted executable paths are assumed to reside on a local, kernel-backed
filesystem, and validation fails closed when the metadata cannot be read.

The final symlink target is fully resolved when its basename is preserved. If
resolution would change the requested basename (`/bin/sh` -> `bash`), the
validated original name is kept so shell and `argv[0]`-sensitive behaviour does
not change; the complete symlink chain is still validated. `pkexec`/`sudo`
receive path arguments and cannot be given an already-open file descriptor, so
execution remains path-based. Validation and execution are separate operations;
a non-root attacker cannot change a validated root-owned, non-writable path,
but a same-user attacker or root can still race the path. Direct fd-based
execution (`execveat`) was not introduced because it is not portable to the
`pkexec`/`sudo` command model and would change process-start semantics.

## Release integrity

Release archives are produced by GitHub Actions only after the Rust format,
lint, and test checks, the Python unit/offscreen GUI tests, and a RustSec audit
pass on the tagged commit. Actions are pinned to immutable commit SHAs, the
default workflow token is read-only, and write permissions exist only in the
build and publish jobs. Each release ships a SHA-256 checksum and Sigstore-based
build provenance (GitHub artifact attestation). Verification commands are
documented in README under **Release verification**. The attestation proves the
workflow and commit that produced an archive; it is not a maintainer GPG
signature.

## Known limitations

- **The udev `uaccess` permission is user-wide, not application-wide.** udev
  applies the ACL to the logged-in user, so every process running under that
  account can read all `input/event*` devices (including keystrokes intended
  for other applications) and can write to `/dev/uinput` to inject system-wide
  input. The rule is still narrower than `MODE="0666"` or permanent `input`
  group membership — the access disappears at logout and other users are not
  granted it — but it does not isolate MacroStat from other programs of the
  same user. Restricting a single process would require a privileged broker or
  a dedicated system service; udev alone cannot express it. Users who do not
  trust all code running as their own account should not install the rule.
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
| Motor ikilisi | Sabit aday listesi; `PATH` üzerinden arama yapılmaz; yalnızca güvenilir kullanıcı/kök sahipli ve üst dizinleri güvenli ikili seçilir |
| Ayrıcalıklı yardımcılar (`pkexec`/`sudo`, `sh`, `modprobe`, `cat`, `udevadm`) | Sabit kök sahipli dizinler; `PATH` aranmaz; her yol ve symlink bileşeni ile POSIX ACL yazma izinleri denetlenir |
| udev izni | Yalnızca `TAG+="uaccess"` + `MODE="0660"`; geniş `chmod 666` veya `input` grubu üyeliği yok |
| Profil/içe aktarma metinleri | Denetim karakterleri, görünmez bidi/zero-width karakterler ve `<`/`>` temizlenir, uzunluk ve sayı aralıkları sınırlanır |
| İçe aktarılan kimlikler | Makro/profil `id` değerleri `[A-Za-z0-9_-]{1,64}` ile sınırlanır; geçersizler yeniden üretilir |
| Sanal aygıt adı | Denetim karakterleri ayıklanır, 80 karakterle sınırlanır |
| Kurulum betikleri | Yalnızca dağıtımın kendi paket yöneticisi kullanılır; kullanıcı girdisi kabuğa gömülmez |

Yönetici izni yalnızca kullanıcının onayladığı `pkexec`/`sudo` udev kurulumunda
kullanılır. Yetkilendirme betiği tamamen sabittir: kullanıcı adı veya başka bir
dış değer kabuk betiğine gömülmez (`input` grubu / `usermod` kaldırıldı).

### Dosya sistemi ve yürütme varsayımları

Çalıştırılabilir yollar `PATH` kullanılmadan bileşen bileşen doğrulanır: dosya,
doğrudan üst dizini, tüm üst dizinleri ve aradaki her symlink kabı güvenilir
kullanıcıya veya köke ait olmalı ve grup/dünya tarafından yazılamamalıdır
(`/tmp` gibi sticky üst dizinler yalnızca doğrudan üst dizinin üzerinde kabul
edilir). POSIX ACL'leri `system.posix_acl_access` üzerinden okunur; güvenilmeyen
adlandırılmış kullanıcı veya gruba etkin yazma izni reddedilir. POSIX ACL
desteğinin bulunmaması "ACL yok" sayılır; okunamayan veya bozuk ACL verisi
fail-closed davranır.

Bu denetimler çekirdeğin bildirdiği sahiplik, mod bitleri ve POSIX ACL
özniteliğine dayanır. FUSE veya ağ dosya sistemlerinde (örneğin ACL'leri
`system.posix_acl_access` olarak sunmayan NFSv4) bu üstveri yapay, eksik veya
hiç bulunmayabilir; dolayısıyla aynı güven garantisi kurulamaz. Güvenilir
çalıştırılabilir yolların yerel, çekirdek destekli bir dosya sisteminde
bulunduğu varsayılır; üstveri okunamadığında doğrulama fail-closed davranır.

Son symlink hedefi, son ad korunuyorsa tamamen çözümlenir. Çözümleme istenen
adı değiştirecekse (`/bin/sh` -> `bash`) doğrulanmış özgün ad korunur; böylece
kabuk ve `argv[0]` davranışı değişmez, ancak symlink zincirinin tamamı yine
doğrulanır. `pkexec`/`sudo` yol argümanı aldığı için önceden açılmış bir dosya
tanıtıcısı verilemez; yürütme yol tabanlı kalır. Doğrulama ile yürütme ayrı
işlemlerdir; kök olmayan bir saldırgan doğrulanmış kök sahipli, yazılamaz yolu
değiştiremez, ancak aynı kullanıcı veya kök yarış koşuluna devam edebilir.
Doğrudan fd tabanlı yürütme (`execveat`) `pkexec`/`sudo` komut modeline
taşınamadığı ve süreç başlatma semantiğini değiştireceği için eklenmedi.

## Sürüm bütünlüğü

Sürüm arşivleri GitHub Actions tarafından ancak etiketlenen commit üzerinde Rust
biçim, lint ve test denetimleri, Python birim/offscreen arayüz testleri ve
RustSec denetimi geçtikten sonra üretilir. Eylemler değişmez commit SHA'larına
sabitlenir, varsayılan iş akışı belirteci salt okunurdur; yazma izinleri yalnızca
derleme ve yayın işlerinde bulunur. Her sürüm bir SHA-256 sağlama dosyası ve
Sigstore tabanlı derleme kökeni (GitHub yapıt kanıtı) ile yayınlanır. Doğrulama
komutları README'deki **Sürüm doğrulama** bölümündedir. Kanıt, arşivi hangi iş
akışının ve commit'in ürettiğini kanıtlar; bakımcı GPG imzası değildir.

## Bilinen sınırlamalar

- **udev `uaccess` izni kullanıcı genelindedir, uygulama genelinde değildir.**
  udev ACL'i oturum açmış kullanıcıya uygular; bu hesap altında çalışan her
  süreç tüm `input/event*` aygıtlarını (başka uygulamalara yönelik tuşlar
  dahil) okuyabilir ve `/dev/uinput` üzerine yazarak sistem genelinde girdi
  üretebilir. Kural yine de `MODE="0666"` veya kalıcı `input` grubu üyeliğinden
  dardır — erişim oturum kapanınca sona erer ve diğer kullanıcılara verilmez —
  ancak MacroStat'ı aynı kullanıcının diğer programlarından yalıtmaz. Tek bir
  süreci kısıtlamak ayrıcalıklı bir aracı (broker) veya ayrı bir sistem servisi
  gerektirir; udev tek başına bunu ifade edemez. Kendi hesabı altında çalışan
  tüm koda güvenmeyen kullanıcılar kuralı kurmamalıdır.
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
