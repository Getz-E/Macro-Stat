# Güvenlik Politikası

MacroStat yerel bir masaüstü uygulamasıdır: Rust motoru Linux `evdev`/`uinput`
kullanır, arayüz PyQt6 tabanlıdır. **Ağ bağlantısı, sunucu, veritabanı, API,
çerez, kimlik doğrulama veya parola saklama yoktur.** Bu nedenle web uygulaması
güvenlik başlıkları (CORS, XSS filtreleri, oturum yönetimi) bu proje için
geçerli değildir; aşağıdaki model gerçek saldırı yüzeyini tanımlar.

## Tehdit modeli

| Varlık | Korunma biçimi |
| --- | --- |
| Profil (`~/.config/macrostat/profile.json`) ve `.bak` | `0600`; atomik yazma (`mkstemp` + `fsync` + `os.replace`) |
| Günlük, pid ve kilit dosyaları | Özel çalışma dizini (`XDG_RUNTIME_DIR`, yoksa `~/.cache/macrostat` 0700); `O_NOFOLLOW`, `0600` |
| Kaydedici geçici dosyaları | `XDG_RUNTIME_DIR` altında `mkstemp`; tahmin edilebilir `/tmp` adı yok |
| Dışa aktarılan yedekler | `mkstemp` ile `0600` |
| Motor ikilisi | Sabit aday listesi; `PATH` üzerinden arama yapılmaz |
| udev izni | Yalnızca `TAG+="uaccess"` + `MODE="0660"`; geniş `chmod 666` veya `input` grubu üyeliği yok |
| Profil/içe aktarma metinleri | Denetim karakterleri ve `<`/`>` temizlenir, uzunluk ve sayı aralıkları sınırlanır |
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
