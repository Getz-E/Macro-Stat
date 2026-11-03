# MacroStat - Kullanım Kılavuzu ve Sistem Çalışma Mantığı
**Hedef Sistem:** CachyOS (Arch Linux) | KDE Plasma (Wayland & X11)
**Motor Mimarisi:** Rust + Linux Kernel `evdev` & `uinput` (Sıfır Gecikme, %0 CPU, Tamamen Çevrimdışı)
**Masaüstü Arayüzü:** Python 3 + PyQt6 (Native Qt6 Bağımsız Penceresi - Web/Tarayıcı DEĞİL)

---

## 🔍 Makro Tetikleme Tuşuna Basıldığında Neden Çalışmıyordu ve Nasıl Düzeltildi?

Eski sürümde tuşa basıldığında makroların çalışmamasının **3 temel teknik sebebi** tespit edilmiş ve kalıcı olarak düzeltilmiştir:

1. **Wayland / Libinput Sanal Aygıt Sınıflandırma Hatası (Çözüldü):**
   - **Sorun:** Eski kodda sanal uinput aygıtına `1..576` aralığındaki tüm tuş kodları topluca kaydediliyordu. Bu aralık içinde joystick ve gamepad kodları (`BTN_JOYSTICK` [288], `BTN_GAMEPAD` [304]) yer alıyordu. Linux `udev-builtin-input_id` ve KDE Wayland `libinput` kütüphanesi bu aygıtı standart masaüstü klavyesi/faresi yerine **"Oyun Kolu / Joystick"** olarak işaretliyor ve masaüstündeki pencerelere (terminal, metin editörü, oyun vb.) klavye/fare olayı göndermesini engelliyordu.
   - **Düzeltme:** Sanal aygıt saf bir **Masaüstü Klavye (1..248)** ve **Fare (272..279)** olarak izole edildi; hiçbir joystick/gamepad kodu eklenmedi. Artık KDE Plasma (Wayland ve X11) her tuş vuruşunu ve tıklamayı anında kabul eder.

2. **Tuş Eşleme ve Sağ/Sol Tuş Esnekliği (Çözüldü):**
   - **Sorun:** Kullanıcı tetikleyici olarak "Shift", "Ctrl" veya "Alt" tanımladığında motor yalnızca `KEY_LEFTSHIFT` veya `KEY_LEFTCTRL` kodunu bekliyor, sağ taraftaki tuşa basıldığında tetikleyici çalışmıyordu. Ayrıca `MOUSE4`, `M4`, `MOUSE5`, `M5` gibi yan tuş isimlendirmeleri eşleşmiyordu.
   - **Düzeltme:** `keys_are_equivalent` fonksiyonu eklenerek genel Ctrl/Shift/Alt/Meta tanımlarında hem sol hem sağ donanım tuşları desteklendi. Fare yan butonları (`BTN_SIDE`, `BTN_EXTRA`, `MOUSE_4`, `MOUSE_5`) tam eşlendi.

3. **Wayland Zamanlama ve Minimum Gecikme Toleransı (Çözüldü):**
   - **Sorun:** Wayland kompozitörleri (KWin), 5-10 milisaniyeden daha kısa süren sanal bas-çek olaylarını arka arkaya geldiğinde birleştirebiliyor (coalesce) veya düşürebiliyordu.
   - **Düzeltme:** Tuş basma ile bırakma arasına Wayland standartlarına uygun minimum 25ms basılı kalma güvencesi eklendi.

---

## ⚡ Sırasıyla Uygulanması Gereken Komutlar (Adım Adım Çalıştırma)

### 📌 Adım 1: Kurulum Betiğini Çalıştırın
Dosyaları çıkardığınız klasörde şu komutları verin:
```bash
chmod +x install_all.sh
./install_all.sh
```
*Bu komut gerekli CachyOS paketlerini kurar, udev donanım kuralını yazar ve Rust motorunu ultra düşük gecikmeli release modunda derler.*

### 📌 Adım 2: Masaüstü Arayüzünü Başlatın
```bash
./baslat-arayuz.sh
```
*Kök dizin kanoniktir; `./baslat-arayuz.sh` arayüzü ve motoru otomatik başlatır.*

---

## 🛡️ Donanım İzinleri ve Kontroller

1. **"🟢 Aktif" Durumu:** Arayüz açıldığında üst çubukta yeşil renkli **"🟢 Aktif"** rozeti görünmelidir.
2. **"🔴 Motor Durduruldu" Görünüyorsa:**
   - Üst çubuktaki mavi **"🛡️ İzinleri Düzelt & Başlat"** butonuna tıklayın.
   - Polkit yetkilendirmesi açılarak `/dev/uinput` ve `/dev/input/event*` izinleri kullanıcı oturumunuza otomatik tanımlanır ve motor anında başlar.

---

## 🎯 Makroları Test Etme ve Günlük İnceleme

- **F8 Hızlı Metin Testi:** Terminal veya metin düzenleyici açıkken **F8** tuşuna basın. `uname -r` komutunun ve Enter tuşunun otomatik yazıldığını göreceksiniz.
- **Shift+Ctrl Çift Tuş Kombinasyonu:** **LeftShift + LeftCtrl** tuşlarına birlikte bastığınızda tanımlı makro derhal tetiklenir.
- **Mouse 5 (Yan Tuş) Tıklayıcı:** Farenizin yan ileri tuşuna bastığınızda hızlı sol tık simülasyonu çalışır.
- **Canlı Günlüğü İnceleme:** Arayüzün üst çubuğundaki **"📋 Günlük"** butonuna basarak hangi tuşların algılandığını ve makroların ne zaman tetiklendiğini anlık olarak okuyabilirsiniz (`/tmp/cachymacro.log`).

---

## 🌐 Dil Seçimi (Türkçe / English)

Başlık çubuğunun sağındaki **🌐** menüsünden dili değiştirebilirsiniz.
Onay verdikten sonra arayüz otomatik yeniden başlar; tercih
`~/.config/cachymacro/settings.json` dosyasında saklanır. Kaydedilmemiş
değişiklikler için uygulama yeniden başlamadan önce sorar.

## 💾 Profil Yönetimi, Dışa/İçe Aktarma ve Yedek

- **✏️ Yeniden adlandır / 🗑️ Sil:** Üst çubuktaki **⋯** profil menüsünden.
  Son kalan profil silinemez; tüm eylemler onay ister.
- **📤 Dışa aktar:** Yalnızca aktif profili veya tüm profilleri tek JSON dosyası
  olarak kaydeder.
- **📥 İçe aktar:** Çoklu profil dosyasındaki profiller yeni kimliklerle eklenir;
  güvenlik için içe aktarılan makrolar **devre dışı** başlar. Profil sarmalayıcısı
  olmayan eski tekil makro dosyaları aktif profile birleştirilir.
- **Geri yükle:** Her kayıtta `~/.config/cachymacro/profile.json.bak` yedeği
  tutulur. **Sistem** sekmesindeki düğmeyle son yedek tek tıkla geri yüklenir;
  ardından arayüz profili yeniden yükler.

## 🧪 Tek Makroyu Test Etme

Makro düzenleyicide **▶ Makroyu Test Et** düğmesi, ekrandaki (kaydedilmemiş) eylemleri
ayrı bir `MacroStat Test Engine` sanal aygıtıyla hemen çalıştırır. Gerçek profiliniz
ve çalışan ana motor etkilenmez. Testin çalışması için `/dev/uinput` yazılabilir
olmalıdır.

---

## 🔒 Metin Yazdırırken ve Makroları Ayarlarken Durdurma (Otomatik İzolasyon)

Tetikleyici tuş ayarlarken, metin yazdırırken (`TEXT` eylemi) veya makro yapılandırması yaparken klavyenizdeki herhangi bir tuşa bastığınızda başka bir makronun devreye girip çakışmaması için **Otomatik İzolasyon Sistemi** entegre edilmiştir:
- **Makro Düzenleyiciye Girildiğinde & Metin Yazarken:** Arka plandaki Rust makro motoru (`cachymacro-daemon`) geçici olarak tamamen durdurulur (`stop_daemon`).
- **Tuş & Metin Girişi:** Düzenleme esnasında hangi harflere, tuşlara veya kombinasyonlara basarsanız basın hiçbir makro çalıştırılmaz.
- **Düzenlemeden Çıkıldığında:** Ayarları kaydedip makro listesine döndüğünüzde motor güncel profilinizle otomatik olarak yeniden başlatılır.

---

## 🛑 Acil Durdurma Anahtarı (Panic Key: KEY_PAUSE)
Herhangi bir acil durumda klavyenizden **KEY_PAUSE** tuşuna (veya arayüzdeki büyük kırmızı **🛑 STOP** butonuna) bastığınız anda:
- Tüm makrolar anında durdurulur ve basılı kalan tüm sanal klavye/fare tuşları serbest bırakılır.
- **Kritik Güvenlik İlkesi:** STOP tuşuna basıldığında motor arayüzden **"🔄 Yeniden Başlat"** butonuna basılana dek **KAPALI KALIR**; hiçbir makro çalıştırılmaz.
- Üst çubukta kırmızı harflerle **DURDURULDU** uyarısı yanar.

---

## 🛡️ Çoklu Profil Yönetimi ve Katı Profil İzolasyonu (Profil 1 vs Profil 2)

Sistem artık çoklu profil desteğine ve katı donanım düzeyinde izolasyona sahiptir:
- **Profil İzolasyon Garantisi:** **Profil 1** seçildiğinde, **Profil 2 veya diğer profillerdeki hiçbir makro arka planda dinlenmez ve asla çalıştırılamaz.**
- **Ayrı Tuş Haritaları:** Farklı profiller aynı tetikleyici tuşları kullansalar bile birbirleriyle asla çakışmaz; yalnızca aktif olan profilin kuralları geçerlidir.
- **Kalıcı Çoklu Yapılandırma:** `profile.json` dosyası hem bağımsız tek profili hem de `activeProfileId` içeren çoklu profil kümesini destekler. Arayüzden profil değiştirdiğiniz anda Rust motoru yeni profili anında yükler.

---

## ⚡ Çift Eylemli Tetikleyiciler (Dual-Action Triggers)

Oyunlarda ve masaüstü otomasyonunda sıradan klavye tuşlarına çift işlev kazandıran mantıklı tetikleme modları eklenmiştir:

1. **✌️ Çift Dokunma (Double-Tap):**
   - Tuşa belirlenen zaman penceresinde (örn. 300 ms) 2 kez seri basıldığında makro tetiklenir.
   - *Örnek:* Normal 'W' tuşuna bir kez basıldığında standart yürüme yapılır; 'W'ye iki kez hızlı dokunulduğunda depar ve kayma kombosu patlar.
2. **⏳ Uzun Basım (Hold / Long Press):**
   - Tuşa hızlı basıp çekildiğinde normal tuş çalışır; ancak tuşa belirlenen süreden (örn. 300 ms) uzun basılı tutulduğunda özel makro veya kombo devreye girer.
   - *Örnek:* 'E' tuşuna kısa basıldığında kapı açılır; 'E' basılı tutulduğunda ağır yetenek iksiri ve ulti kombosu devreye girer.
3. **🎭 Basarken & Bırakırken Çift Eylem (Press & Release):**
   - Tuşa basıldığı anda (Key Down) 1. eylem sırası, tuş serbest bırakıldığı anda (Key Up) 2. eylem sırası otomatik icra edilir.
   - *Örnek (Sniper):* Farenin yan tuşuna basarken dürbün açılıp nefes tutulur (`Shift`); parmak çekildiği anda nefes bırakılır ve otomatik 1. silaha dönülür.

---

## 🔁 Tetikleyici Tuşa Tekrar Basıldığında Makroyu Durdurma (Aç/Kapa & Tekrar Modu)

Döngüsel makrolarda (`TOGGLE_LOOP`) veya tekrarlayan eylemlerde (`REPEAT_COUNT`), makroyu başlatan **tetikleyici tuşa ikinci kez basıldığında**:
- Rust motoru atomik bayrağı (`AtomicBool`) derhal `false` durumuna çeker.
- Eylemler arasındaki mikro gecikmeler (`cancellable_sleep`) **4 milisaniyeden kısa sürede** uyanarak eylemi derhal yarıda keser.
- Makro tarafından basılmış olabilecek tüm sanal klavye ve fare tuşları (`release_all_keys`) temizlenir, hiçbir tuş basılı takılı kalmaz.
- Terminal veya günlüğe `[DÖNGÜ KAPATILDI] Tetikleyiciye tekrar basıldı, makro durduruldu` kaydı düşülür.

---

## 📦 AppImage Olarak Kutudan Çıktığı Gibi Çalıştırma

Tüm sistemi bağımsız, taşınabilir bir **AppImage** paketi olarak derleyip tek dosyayla çalıştırmak için:
```bash
chmod +x build_appimage.sh
./build_appimage.sh
```
- Bu komut Rust motorunu derler ve `MacroStat-x86_64.AppImage` dosyasını üretir. **PyQt6 AppImage içine gömülmez**; sistemde `python-pyqt6` kurulu olmalıdır.
- **İlk Açılış:** AppImage çift tıklandığında `/dev/uinput` yazma iznini denetler (eksikse uyarır) ve kullanıcı profilini `~/.config/cachymacro/profile.json` konumuna tohumlar. Masaüstü kısayolu otomatik oluşturulmaz; isterseniz `.desktop` dosyasını kendiniz ekleyebilirsiniz.

---

## 🚪 Güvenli Kapatma Garantisi
Uygulama penceresini kapattığınızda:
- Linux çekirdeği `PR_SET_PDEATHSIG` ve PyQt6 `closeEvent` kancaları devreye girer.
- Arka plandaki Rust makro motoru (`cachymacro-daemon`) hiçbir yetim (zombie) süreç bırakmadan **TAMAMEN KAPANIR**.

---

## 📄 Lisans
MacroStat, **GPL-3.0-or-later** (GNU General Public License v3.0 veya sonrası) altında dağıtılır.
Tam metin `LICENSE` dosyasındadır; üçüncü taraf bileşenler ve lisansları `THIRD_PARTY.md` içinde listelenmiştir.

