# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Basit sözlük tabanlı TR/EN çeviri katmanı.

Türkçe metinler kaynak anahtar olarak kullanılır; İngilizce karşılıkları
``_EN`` sözlüğünde tutulur. Çeviri, arayüz kurulmadan önce seçilir; dil
değişiminde arayüz yeniden başlatılır (Qt widget metinleri yeniden üretilir).
"""

LANGUAGES = {"tr": "Türkçe", "en": "English"}
DEFAULT_LANGUAGE = "tr"

_current = DEFAULT_LANGUAGE

#: Türkçe kaynak metin -> İngilizce karşılık
_EN = {
    # --- Genel / üst çubuk ---
    "DURDURULDU": "STOPPED",
    "● Kontrol ediliyor...": "● Checking...",
    "İzinleri Düzelt & Başlat": "Fix Permissions & Start",
    "Günlüğü İncele": "View Log",
    "Yeniden Başlat": "Restart",
    "Makrolar": "Macros",
    "Makro Düzenleyici": "Macro Editor",
    "Canlı Tuş Kaydedici": "Live Key Recorder",
    "Sistem & Kılavuz": "System & Guide",
    "Profil:": "Profile:",
    "+ Profil": "+ Profile",
    "Yeniden Adlandır": "Rename",
    "Profili Sil": "Delete Profile",
    "Dil:": "Language:",
    "Dil Değişikliği": "Language Change",
    "Dil değişikliğinin uygulanması için arayüz yeniden başlatılacak. Devam edilsin mi?": (
        "The interface will restart to apply the language change. Continue?"
    ),
    "Profil Profili": "Profile",
    # --- Profil yönetimi ---
    "Yeni Profil": "New Profile",
    "Yeni profil adını girin:": "Enter the new profile name:",
    "Profili Yeniden Adlandır": "Rename Profile",
    "Yeni profil adı:": "New profile name:",
    "Profili Sil": "Delete Profile",
    "'{}' profili silinsin mi? Bu işlem geri alınamaz.": (
        "Delete profile '{}'? This cannot be undone."
    ),
    "Son profil silinemez.": "The last profile cannot be deleted.",
    "'{}' profili oluşturuldu ve aktif edildi.": (
        "Profile '{}' was created and activated."
    ),
    "'{}' aktif edildi. Diğer profiller devre dışıdır.": (
        "Profile '{}' activated. Other profiles are inactive."
    ),
    "{} profili aktif edildi. Diğer profiller devre dışıdır.": (
        "Profile {} activated. Other profiles are inactive."
    ),
    "Profil yeniden adlandırıldı.": "Profile renamed.",
    "Profil silindi.": "Profile deleted.",
    "Profil kaydedilemedi: ": "Could not save profile: ",
    "Hata": "Error",
    "Başarılı": "Success",
    # --- Makro listesi ---
    "Sıra": "#",
    "Aç / Kapat": "On / Off",
    "Makro Adı": "Macro Name",
    "Tetikleyici Tuş": "Trigger Key",
    "Çalışma Modu": "Mode",
    "Eylemler": "Actions",
    "Sil": "Delete",
    "Yeni Makro": "New Macro",
    "Düzenle": "Edit",
    "Klonla": "Duplicate",
    "Sil (Del)": "Delete (Del)",
    "Dışa Aktar": "Export",
    "İçe Aktar": "Import",
    "Kaydet": "Save",
    "Profili Dışa Aktar": "Export Profile",
    "Makro / Profil İçe Aktar": "Import Macro / Profile",
    "Dışa Aktarma Hatası": "Export Error",
    "İçe Aktarma Hatası": "Import Error",
    "Dışa Aktarım Kapsamı": "Export Scope",
    "Yalnızca aktif profili mi, tüm profilleri mi dışa aktarmak istersiniz?": (
        "Export only the active profile, or all profiles?"
    ),
    "Aktif Profil": "Active Profile",
    "Tüm Profiller": "All Profiles",
    "İptal": "Cancel",
    "Tüm profiller dışa aktarıldı: ": "All profiles exported: ",
    "Profil dışa aktarıldı: ": "Profile exported: ",
    "Dosyada içe aktarılabilir makro/profil bulunamadı.": (
        "No importable macro or profile found in the file."
    ),
    " (İçe Aktarıldı)": " (Imported)",
    " makro içe aktarıldı (güvenlik için devre dışı).": (
        " macro(s) imported (disabled for safety)."
    ),
    " profil içe aktarıldı (makroları devre dışı).": (
        " profile(s) imported (macros disabled)."
    ),
    "Yukarı Taşı (Yukarı Ok)": "Move Up (Up Arrow)",
    "Aşağı Taşı (Aşağı Ok)": "Move Down (Down Arrow)",
    "AÇIK": "ON",
    "KAPALI": "OFF",
    "Makroyu Sil (Kırmızı X)": "Delete Macro (Red X)",
    "Kullanıcı tanımlı makro": "User-defined macro",
    # --- Düzenleyici ---
    "Güvenli Düzenleme Modu: Metin yazarken veya makro ayarları yapılırken diğer makrolar durdurulur.": (
        "Safe Editing Mode: other macros are paused while typing or editing macro settings."
    ),
    "Düzenleme modu: Metin yazarken ve ayar yaparken makrolar durduruldu.": (
        "Editing mode: macros are paused while typing and configuring."
    ),
    "Makro Yapılandırması": "Macro Configuration",
    "Makro Adı:": "Macro Name:",
    "Tuşa / İkili Kombinasyona Basarak Ayarla": "Capture Key / Key Combination",
    "Tetikleyici Tuş:": "Trigger Key:",
    "Tek Seferlik (ONCE)": "Single Shot (ONCE)",
    "Basılı Tutulduğu Sürece (WHILE_HELD)": "While Held (WHILE_HELD)",
    "Aç / Kapa Döngüsü (TOGGLE_LOOP)": "Toggle Loop (TOGGLE_LOOP)",
    "Tekrar Sayısı (REPEAT_COUNT)": "Repeat Count (REPEAT_COUNT)",
    "Çift Dokunma (DOUBLE_TAP)": "Double Tap (DOUBLE_TAP)",
    "Uzun Basım (HOLD_LONG_PRESS)": "Long Press (HOLD_LONG_PRESS)",
    "Bas-Bırak Çift Eylemi (PRESS_AND_RELEASE)": "Press & Release (PRESS_AND_RELEASE)",
    "Çalışma Modu:": "Mode:",
    "Tekrar Sayısı:": "Repeat Count:",
    "Çift Dokunma modunda iki basış arasındaki en büyük süre": (
        "Maximum interval between two taps in Double Tap mode"
    ),
    "Çift Dokunma Aralığı:": "Double Tap Interval:",
    "Uzun Basım modunda makronun devreye girdiği basılı tutma süresi": (
        "Hold duration that activates the macro in Long Press mode"
    ),
    "Uzun Basım Eşiği:": "Long Press Threshold:",
    "Düzenlenen liste:": "Editing list:",
    "Basış Eylemleri": "Press Actions",
    "Bırakış Eylemleri (PRESS_AND_RELEASE)": "Release Actions (PRESS_AND_RELEASE)",
    "Eylem Tipi": "Action Type",
    "Parametreler": "Parameters",
    "Tuş Bas-Çek": "Key Tap",
    "Tuşa Bas (Basılı Tut)": "Key Down (Hold)",
    "Belirtilen tuşu basılı bırakır (Tuşun basılı kalması)": (
        "Holds the specified key down"
    ),
    "Tuşu Bırak": "Key Up",
    "Basılı tutulan tuşu serbest bırakır": "Releases the held key",
    "Fare Tıkla": "Mouse Click",
    "Fare Basılı Tut": "Mouse Down (Hold)",
    "Fare tuşunu basılı bırakır": "Holds the mouse button down",
    "Fare Bırak": "Mouse Up",
    "Basılı fare tuşunu serbest bırakır": "Releases the held mouse button",
    "Gecikme": "Delay",
    "Metin Yazdır": "Type Text",
    "Fare Hareketi": "Mouse Move",
    "İmleci belirtilen piksel kadar göreli hareket ettirir": (
        "Moves the cursor by the given relative pixels"
    ),
    "Fare Tekerleği": "Mouse Wheel",
    "Eylem Tuşunu Ayarla / Düzenle": "Set / Edit Action Key",
    "Eylemi Sil (Del)": "Delete Action (Del)",
    "Tüm Eylemleri Sil": "Clear All Actions",
    "Makroyu Test Et": "Test Macro",
    "Makro Test Ediliyor...": "Testing Macro...",
    "Makro testi başarısız.": "Macro test failed.",
    "Test sırasında diğer makrolar etkilenmez; yalnızca bu makronun eylemleri çalıştırılır.": (
        "Other macros are unaffected during the test; only this macro's actions run."
    ),
    "Tuş Bas-Çek": "Key Tap",
    "Tuşa Bas (Basılı Tut)": "Key Down (Hold)",
    "Tuşu Bırak": "Key Up",
    "Fare Tıkla": "Mouse Click",
    "Fare Basılı Tut": "Mouse Down (Hold)",
    "Fare Bırak": "Mouse Up",
    "Fare Hareketi": "Mouse Move",
    "Fare Tekerleği": "Mouse Wheel",
    "Gecikme Bekle": "Wait (Delay)",
    "Metin Yazdır": "Type Text",
    " (Basılı Kalır)": " (Held)",
    " (Serbest Bırakılır)": " (Released)",
    " (Basma: {}ms)": " (Tap: {}ms)",
    "Tuş: {}": "Key: {}",
    "Fare: {}": "Mouse: {}",
    "{} ms (±{} ms)": "{} ms (±{} ms)",
    "{} ms (±{}ms)": "{} ms (±{}ms)",
    "dx={}, dy={}": "dx={}, dy={}",
    "Makronun Basacağı Tuşu Seçin (Klavyeden Tuşa Basın)": (
        "Choose the Key the Macro Will Press (Press a Key)"
    ),
    "Fare Tuşu Seç": "Choose Mouse Button",
    "Makro fare tuşu:": "Macro mouse button:",
    "Gecikme Süresi": "Delay Duration",
    "Milisaniye (ms):": "Milliseconds (ms):",
    "Metin Makrosu": "Text Macro",
    "Yazdırılacak metni girin:": "Enter the text to type:",
    "Merhaba MacroStat!": "Hello MacroStat!",
    "Metin çok uzun; en fazla {} bayt olabilir.": (
        "The text is too long; it may be at most {} bytes."
    ),
    "X ekseni (piksel, sağ +):": "X axis (pixels, right +):",
    "Y ekseni (piksel, aşağı +):": "Y axis (pixels, down +):",
    "Yukarı": "Up",
    "Aşağı": "Down",
    "Kaydırma yönü:": "Scroll direction:",
    "Yeni Tuşa Basın": "Press a New Key",
    "Tuş Basma Süresi": "Key Hold Duration",
    "Tuş basılı kalma süresi (ms):": "Key hold duration (ms):",
    "Fare Tuşu Değiştir": "Change Mouse Button",
    "Fare tuşu:": "Mouse button:",
    "Metin Düzenle": "Edit Text",
    "Yazdırılacak metin:": "Text to type:",
    "X ekseni (piksel):": "X axis (pixels):",
    "Y ekseni (piksel):": "Y axis (pixels):",
    "Tüm Eylemleri Sil": "Clear All Actions",
    "Bu makrodaki tüm eylemleri silmek istediğinizden emin misiniz?": (
        "Are you sure you want to delete all actions in this macro?"
    ),
    "Kaydedildi...": "Saved...",
    # --- Tuş yakalama ---
    "Tetikleyici Tuş veya İkili Kombinasyon Ayarla": (
        "Set Trigger Key or Key Combination"
    ),
    "Tuş ayarlanırken makrolar durduruldu.": (
        "Macros paused while capturing a key."
    ),
    "Makrolar Durduruldu: Tuş ayarlarken diğer makrolar çalıştırılmaz.": (
        "Macros Stopped: other macros will not run while capturing a key."
    ),
    "Klavyenizden bir tuşa basın veya LeftShift+LeftCtrl gibi iki tuşa aynı anda basın:": (
        "Press a key, or press two keys together such as LeftShift+LeftCtrl:"
    ),
    "Tuşa veya ikili kombinasyona basın...": "Press a key or key combination...",
    "Bu Tuşu / Kombinasyonu Kullan": "Use This Key / Combination",
    "Makro motoru tekrar aktif edildi.": "Macro engine re-activated.",
    "Algılandı: {}": "Detected: {}",
    "İkili Kombinasyon: {}": "Key Combination: {}",
    "Bu Tuşu Kullan ({})": "Use This Key ({})",
    "{}": "{}",
    "STOP Tuşunu Ayarlayın": "Set the STOP Key",
    "STOP tuşu '{}' olarak güncellendi.": "STOP key updated to '{}'.",
    # --- Kaydedici ---
    "Olay": "Event",
    "Tuş / Buton": "Key / Button",
    "Gecikme (ms)": "Delay (ms)",
    "Kaydı Başlat": "Start Recording",
    "Temizle": "Clear",
    "Kaydı Yeni Makro Olarak Ekle": "Add Recording as New Macro",
    "Kaydı Durdur": "Stop Recording",
    "Canlı kayıt modu: Diğer tüm makrolar durduruldu.": (
        "Live recording mode: all other macros are paused."
    ),
    "Kayıtlı Makro ({} adım)": "Recorded Macro ({} steps)",
    "Canlı kaydedici ile oluşturuldu": "Created with the live recorder",
    # --- Sistem ---
    "Donanım İzinlerini Otomatik Düzelt (udev)": (
        "Auto-Fix Hardware Permissions (udev)"
    ),
    "Durumu Yenile": "Refresh Status",
    "Motor derleniyor...": "Building engine...",
    "Motor Bulunamadı": "Engine Not Found",
    "Lütfen terminalde 'cargo build --release' komutunu çalıştırın.": (
        "Run 'cargo build --release' in a terminal."
    ),
    "Makro motoru başlatıldı.": "Macro engine started.",
    "STOP Tetiklendi! Motor 'Yeniden Başlat' düğmesine veya {} tuşuna basılana dek kapalı kalacaktır.": (
        "STOP triggered! The engine stays off until 'Restart' is pressed or {} is hit."
    ),
    "STOP sonrası motoru yeniden başlatır; atanmış tuş da aynı işi yapar":
        "Restarts the engine after STOP; the assigned key does the same",
    "Yeniden Başlatma Tuşunu Ayarla": "Set Restart Key",
    "Yeniden Başlatma Tuşunu Ayarlayın": "Set the Restart Key",
    "Geçersiz Tuş": "Invalid Key",
    "Yeniden başlatma tuşu bir klavye tuşu olmalıdır (ör. KEY_F12).":
        "The restart key must be a keyboard key (e.g. KEY_F12).",
    "Yeniden başlatma tuşu '{}' olarak güncellendi.":
        "Restart key updated to '{}'.",
    "Yeniden başlatma tuşuna basıldı; makro motoru açılıyor.":
        "Restart key pressed; starting the macro engine.",
    "Yeniden başlatma tuşu dinlenemedi (kod {}).":
        "Could not listen for the restart key (code {}).",
    "Makro motoru yeniden başlatıldı.": "Macro engine restarted.",
    "İzinler Düzeltildi": "Permissions Fixed",
    "udev kuralı kuruldu ve motor başlatıldı.\nKural yeni oturumda etkinleşir; sorun sürerse oturumu kapatıp açın.": (
        "udev rule installed and engine started.\nThe rule becomes active in a new session; log out and back in if the problem persists."
    ),
    "Yetkilendirme başarısız (çıkış kodu {})": "Authorization failed (exit code {})",
    "[HATA] PyQt6 kütüphanesi eksik!": "[ERROR] PyQt6 library is missing!",
    "Kurulum için: dağıtımınıza uygun install_ubuntu.sh / install_debian.sh / "
    "install_fedora.sh / install_arch.sh betiğini çalıştırın.": (
        "Install it with the installer for your distribution: install_ubuntu.sh / "
        "install_debian.sh / install_fedora.sh / install_arch.sh"
    ),
    "MacroStat zaten çalışıyor. Mevcut pencereyi kullanın.": (
        "MacroStat is already running. Use the existing window."
    ),
    "Motor Durduruldu (STOP)": "Engine Stopped (STOP)",
    "Düzenleme Modu (Beklemede)": "Edit Mode (Idle)",
    "Aktif": "Active",
    "Bırakma Eylemleri (tetiş bırakılınca)": "Release Actions (on trigger release)",
    "Yalnızca 'Bas-Bırak Çift Eylemi (PRESS_AND_RELEASE)' modunda çalışır.":
        "Only used in 'Press & Release (PRESS_AND_RELEASE)' mode.",
    "Bırakma Anında Basılacak Tuşu Seçin": "Select Key to Press on Release",
    "{} eylem": "{} action(s)",
    "Aktif profil": "Active profile",
    "Kontrol ediliyor...": "Checking...",
    "Diğer işlemler": "More actions",
    "STOP": "STOP",
    "Tüm makroları hemen durdur": "Stop all macros immediately",
    "STOP Tuşunu Ayarla": "Set STOP Key",
    "Tema": "Theme",
    "Sistem": "System",
    "Koyu": "Dark",
    "Açık": "Light",
    "Günlük": "Log",
    "Motor Çöktü (kod {})": "Engine Crashed (code {})",
    "Motor Durduruldu": "Engine Stopped",
    "Hatayı İncele": "Inspect Error",
    "Makro motoru yeniden başlatılmadan güncellendi.": (
        "Macro engine reloaded without restart."
    ),
    "Makro başarıyla test edildi.": "Macro tested successfully.",
    "Bu makroda eylem yok.": "This macro has no actions.",
    "=== MacroStat Donanım ve Sistem Tanılama ===\nKernel /dev/uinput: {}\nMotor İkili Dosyası: {}\nProfil Dosyası: {}\nAcil Durdurma Tuşu (STOP): {}\nLog Dosyası: {}\n": (
        "=== MacroStat Hardware and System Diagnostics ===\nKernel /dev/uinput: {}\n"
        "Engine Binary: {}\nProfile File: {}\nEmergency Stop Key (STOP): {}\nLog File: {}\n"
    ),
    # --- Yedek geri yükleme ---
    "Son Yedeği Geri Yükle": "Restore Last Backup",
    "Yedek Geri Yükleme": "Restore Backup",
    "Yedek dosyası bulunamadı.": "Backup file not found.",
    "Yedek geri yüklensin mi? Mevcut profil bu yedekle değiştirilecek.": (
        "Restore the backup? The current profile will be replaced."
    ),
    "Profil yedeği geri yüklendi.": "Profile backup restored.",
    "Yedek okunamadı: ": "Could not read backup: ",
    # --- Üst çubuk menüleri ve düzenleyici ---
    "Profil işlemleri": "Profile actions",
    "Dil / Language": "Language",
    "Yeni Profil": "New Profile",
    "Motoru Yeniden Başlat": "Restart Engine",
    "Acil durdurma tuşunu ayarla": "Set emergency stop key",
    "Kaydedilmemiş Değişiklikler": "Unsaved Changes",
    "Makro düzenleyicisinde kaydedilmemiş değişiklikler var.\nKaydetmek ister misiniz?": (
        "There are unsaved changes in the macro editor.\nSave them?"
    ),
    "Tuş: {} (Basılı Kalır)": "Key: {} (Stays Held)",
    "Tuş: {} (Serbest Bırakılır)": "Key: {} (Released)",
    "Tuş: {} (Basma: {}ms)": "Key: {} (Hold: {}ms)",
    "Fare: {} (Basılı Kalır)": "Mouse: {} (Stays Held)",
    "Fare: {} (Serbest Bırakılır)": "Mouse: {} (Released)",
    "{} makro içe aktarıldı (güvenlik için devre dışı).": (
        "{} macros imported (disabled for safety)."
    ),
    "{} profil içe aktarıldı (makroları devre dışı).": (
        "{} profiles imported (macros disabled)."
    ),
    "Milisaniye hassasiyetinde klavye, fare tuşları ve tekerlek olaylarını kaydeder.": (
        "Records keyboard, mouse button and wheel events with millisecond precision."
    ),
    "Wayland oturumu: kayıt yalnızca bu pencere odaktayken çalışır; sistem genelinde tuş dinleme kısıtlıdır.": (
        "Wayland session: recording only works while this window is focused; "
        "system-wide key capture is restricted."
    ),
    "Profil kaydedilemedi: {}": "Could not save profile: {}",
    "Arayüz yeniden başlatılamadı. Lütfen uygulamayı elle açın.": (
        "The interface could not be restarted. Please open the app manually."
    ),
    # --- Varsayılan profil şablonu (veri alanları) ---
    "MacroStat Varsayılan Profil": "MacroStat Default Profile",
    "Donanım tabanlı sıfır gecikmeli makrolar. Varsayılan demolar güvenlik için devre dışıdır.": (
        "Hardware-based zero-latency macros. Default demos are disabled for safety."
    ),
    "Hızlı Tıklama (Demo)": "Rapid Click (Demo)",
    "Etkinleştirildiğinde tetikleyici tuşta sol tık bas-çek yapar. Varsayılan olarak kapalıdır.": (
        "When enabled, performs a left click on each trigger. Disabled by default."
    ),
    "X Tuşu (Demo)": "X Key (Demo)",
    "Etkinleştirildiğinde X tuşuna basıp 50 ms bekler. Varsayılan olarak kapalıdır.": (
        "When enabled, presses X and waits 50 ms. Disabled by default."
    ),
    # --- İçe/dışa aktarma ve yedekleme ---
    "Dışa Aktar…": "Export…",
    "İçe Aktar…": "Import…",
    "Dışa Aktarma": "Export",
    "Dışa Aktarma Hatası": "Export Error",
    "Dışa Aktarılacak Profiller": "Profiles to Export",
    "Dışa aktarılacak profilleri seçin:": "Select the profiles to export:",
    "Dışa aktarılacak profil bulunamadı.": "No profile to export.",
    "Profilleri Dışa Aktar": "Export Profiles",
    "Profili Dışa Aktar": "Export Profile",
    "{} profil dışa aktarıldı: {}": "{} profile(s) exported: {}",
    "İçe Aktarmayı Onayla": "Confirm Import",
    "İçe aktarılacak: {} makro, {} profil.": "To import: {} macro(s), {} profile(s).",
    "{} uyarı:": "{} warning(s):",
    "Mevcut makro ve profiller silinmez; içe aktarılan makrolar güvenlik için devre dışı eklenir.": (
        "Existing macros and profiles are kept; imported macros are added disabled for safety."
    ),
    "{} makro ve {} profil içe aktarıldı (makrolar devre dışı).": (
        "{} macro(s) and {} profile(s) imported (macros disabled)."
    ),
    "Yedekle…": "Back up…",
    "Geri Yükle…": "Restore…",
    "Yedekleme": "Backup",
    "Yedekleme Hatası": "Backup Error",
    "Profilleri Yedekle": "Back Up Profiles",
    "Yedeklenecek profil bulunamadı.": "No profile to back up.",
    "{} profil yedeklendi: {}": "{} profile(s) backed up: {}",
    "Yedeği Geri Yükle": "Restore Backup",
    "Yedek Geri Yükleme": "Restore Backup",
    "Bu dosyada geri yüklenecek profil yok. Makroları Makrolar sekmesindeki 'İçe Aktar…' ile ekleyin.": (
        "This file has no profile to restore. Add macros with 'Import…' on the Macros tab."
    ),
    "{} profil geri yüklenecek. Aynı adlı profiller '(2)', '(3)' ekleriyle eklenir; mevcut profiller silinmez. Devam edilsin mi?": (
        "{} profile(s) will be restored. Duplicate names get '(2)', '(3)' suffixes; "
        "existing profiles are kept. Continue?"
    ),
    "{} profil geri yüklendi.": "{} profile(s) restored.",
    "Profil": "Profile",
    # --- Aktarma doğrulama/uyarıları ---
    "Geçersiz eylem atlandı.": "Invalid action skipped.",
    "Türü olmayan eylem atlandı.": "Action without a type skipped.",
    "Geçersiz tuş eylemi atlandı: {}": "Invalid key action skipped: {}",
    "Çok uzun metin eylemi atlandı.": "Text action too long; skipped.",
    "Geçersiz fare yolu eylemi atlandı.": "Invalid mouse path action skipped.",
    "Boş fare yolu eylemi atlandı.": "Empty mouse path action skipped.",
    "Bilinmeyen eylem türü atlandı: {}": "Unknown action type skipped: {}",
    "Geçersiz makro atlandı.": "Invalid macro skipped.",
    "Makro olmayan öğe atlandı.": "Non-macro item skipped.",
    "İçe Aktarılan Makro": "Imported Macro",
    "İçe Aktarılan Profil": "Imported Profile",
    "Geçersiz tetikleyici boşaltıldı.": "Invalid trigger cleared.",
    "Eylem sınırı aşıldı; kalanlar atlandı.": "Action limit exceeded; remaining items skipped.",
    "Geçersiz profil atlandı.": "Invalid profile skipped.",
    "Makro sınırı aşıldı; kalanlar atlandı.": "Macro limit exceeded; remaining items skipped.",
    "Profil sınırı aşıldı; kalanlar atlandı.": "Profile limit exceeded; remaining items skipped.",
    "Dosyada içe aktarılabilir makro veya profil bulunamadı.": (
        "No importable macro or profile found in the file."
    ),
    "Dosya çok büyük (en fazla 5 MB).": "File is too large (5 MB maximum).",
    "Dosya okunamadı: {}": "Could not read file: {}",
    "Geçersiz JSON: {}": "Invalid JSON: {}",
    "Dışa aktarılacak profil seçilmedi.": "No profile selected for export.",
    "Dışa aktarma başarısız: {}": "Export failed: {}",
    "(İçe Aktarıldı)": " (Imported)",
    "Canlı Günlük": "Live Log",
    "Günlükte ara…": "Search log…",
    "Otomatik kaydır": "Auto-scroll",
    "Duraklat": "Pause",
    "Devam et": "Resume",
    "Temizle": "Clear",
    "Günlük panelini kapat": "Close log panel",
    "Günlük henüz yok.": "No log yet.",
    "MacroStat Kurulum": "MacroStat Setup",
    "Geri": "Back",
    "İleri": "Next",
    "Bitir": "Finish",
    "Sistem Durumu": "System Status",
    "Kuruluma başlamadan önce ortamınızı kontrol edelim.": (
        "Let's check your environment before setting up."
    ),
    "Donanım Erişimi (/dev/uinput)": "Hardware Access (/dev/uinput)",
    "Motorun tuş gönderebilmesi için /dev/uinput yazılabilir olmalıdır.": (
        "The engine needs write access to /dev/uinput to send keys."
    ),
    "Oturum izni (uaccess)": "Session permission (uaccess)",
    "udev kuralı yalnızca oturum sahibine yazma izni verir; "
    "geniş 'input' grubu gerekmez.": (
        "The udev rule grants write access only to the session owner; "
        "the broad 'input' group is not required."
    ),
    "udev kuralı kurulu": "udev rule installed",
    "Giriş aygıtlarına dar kapsamlı izinler tanımlar (chmod 666 kullanılmaz).": (
        "Defines narrow permissions for input devices (no chmod 666)."
    ),
    "Motor ikilisi bulundu": "Engine binary found",
    "'cargo build --release' ile derlenmiş motor ikilisi gerekir.": (
        "An engine binary built with 'cargo build --release' is required."
    ),
    "İzinleri Düzelt": "Fix Permissions",
    "Yalnızca giriş aygıtları için udev kuralı kurulur; geniş chmod 666 kullanılmaz.": (
        "Only an udev rule for input devices is installed; broad chmod 666 is never used."
    ),
    "Kurulacak kural /dev/uinput ve event aygıtlarına yalnızca oturum "
    "sahibine erişim verir (MODE=0660, uaccess). Geniş 'input' grubu "
    "üyeliği gerekmez; kural sonraki oturumda da geçerlidir.": (
        "The rule grants access to /dev/uinput and event devices only to the "
        "session owner (MODE=0660, uaccess). Broad 'input' group membership "
        "is not required; the rule remains valid in later sessions."
    ),
    "udev kuralını kurmak için yönetici izni istemini onaylıyorum.": (
        "I approve the administrator permission prompt to install the udev rule."
    ),
    "İzinleri Kur": "Install Permissions",
    "Kural zaten kurulu; bu adımı atlayabilirsiniz.": (
        "The rule is already installed; you can skip this step."
    ),
    "İzinleri şimdilik atla; daha sonra Sistem sayfasından kurabilirim "
    "(izin kurulana kadar motor çalışmaz).": (
        "Skip permissions for now; I can install them later from the System "
        "page (the engine will not run until they are installed)."
    ),
    "İzinler başarıyla kuruldu. Kural yeni oturumda etkinleşir.": (
        "Permissions installed successfully. The rule takes effect in a new session."
    ),
    "Kurulum başarısız: {}": "Installation failed: {}",
    "Hazır": "Ready",
    "Kurulum tamamlandı. Motoru şimdi başlatabilirsiniz.": (
        "Setup is complete. You can start the engine now."
    ),
    "Motoru şimdi başlat": "Start the engine now",
    "Eksik görünen adımlar: {}": "Steps that still look incomplete: {}",
    "Tüm kontroller başarılı.": "All checks passed.",
    "Kurulumu yeniden çalıştır": "Run setup again",
    "İzinler kurulamadı: {}": "Could not install permissions: {}",
}

#: Tanılama metni (çok satırlı, yer tutuculu)
_DIAGNOSTICS_EN = {
    "=== MacroStat Donanım ve Sistem Tanılama ===\nKernel /dev/uinput: ": (
        "=== MacroStat Hardware and System Diagnostics ===\nKernel /dev/uinput: "
    ),
    "\nMotor İkili Dosyası: ": "\nEngine Binary: ",
    "\nProfil Dosyası: ": "\nProfile File: ",
    "\nAcil Durdurma Tuşu (STOP): ": "\nEmergency Stop Key (STOP): ",
    "\nLog Dosyası: ": "\nLog File: ",
    "Erişilebilir (Yazma İzni Var)": "Accessible (Writable)",
    "Erişim Yok (İzin Gerekli)": "No Access (Permission Required)",
    "İkili Dosya Bulunamadı (cargo build --release çalıştırın)": (
        "Binary Not Found (run cargo build --release)"
    ),
    "Bulunamadı": "Not found",
    # --- Sistem geneli fare yolu kaydı ---
    "Fare hareketini sistem genelinde kaydet": "Record mouse movement system-wide",
    "Kayıt sırasında fare hareketleri evdev üzerinden tüm masaüstünde izlenir. "
    "Kayıt yalnızca göreli hareketi saklar; Pause tuşu kaydı bitirir.":
        "Mouse movement is captured across the whole desktop via evdev during "
        "recording. Only relative motion is stored; Pause stops the recording.",
    "Sistem geneli fare kaydı: durdurmak için Pause tuşuna basın veya düğmeyi kullanın.":
        "System-wide mouse recording: press Pause or use the button to stop.",
    "Kayıt bitiriliyor...": "Finishing recording...",
    "Motor ikilisi bulunamadı. Önce cargo build --release çalıştırın.":
        "Engine binary not found. Run cargo build --release first.",
    "Fare kaydı başlatılamadı: {}": "Could not start mouse recording: {}",
    "Durdur ({} sn)": "Stop ({} s)",
    "bilinmeyen hata": "unknown error",
    "Fare kaydı hatası: {}": "Mouse recording error: {}",
    "Fare kaydı okunamadı: {}": "Could not read mouse recording: {}",
    "{} nokta kaydedildi ({} ms).": "Recorded {} points ({} ms).",
    "{} nokta, {} fare olayı kaydedildi ({} ms).":
        "Recorded {} points and {} mouse events ({} ms).",
    "Fare kaydı boş; hareket algılanmadı.": "Mouse recording is empty; no movement detected.",
    "{} nokta": "{} points",
    "Fare Yolu (Kayıt)": "Mouse Path (Recording)",
    "{} nokta, {} ms": "{} points, {} ms",
    "Fare Yolu": "Mouse Path",
    "Kaydedilmiş fare yolu {} nokta ve {} ms içeriyor. "
    "Noktalar tek tek düzenlenemez; gerekirse eylemi silip yeniden kaydedin.":
        "The recorded mouse path contains {} points and {} ms. Points cannot be "
        "edited individually; delete the action and record it again if needed.",
}
_EN.update(_DIAGNOSTICS_EN)


def available_languages():
    """Desteklenen dilleri (kod, ad) çiftleri olarak döndürür."""
    return list(LANGUAGES.items())


def set_language(code):
    """Aktif arayüz dilini ayarlar; bilinmeyen kodlarda varsayılana döner."""
    global _current
    _current = code if code in LANGUAGES else DEFAULT_LANGUAGE
    return _current


def get_language():
    return _current


def T(text):
    """Türkçe kaynak metni aktif dile çevirir; bilinmeyen metin aynen döner."""
    if _current == "en":
        return _EN.get(text, text)
    return text
