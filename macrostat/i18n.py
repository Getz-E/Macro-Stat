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
    "🛡️ İzinleri Düzelt & Başlat": "🛡️ Fix Permissions & Start",
    "📋 Günlüğü İncele": "📋 View Log",
    "🔄 Yeniden Başlat": "🔄 Restart",
    "📋 Makrolar": "📋 Macros",
    "🛠️ Makro Düzenleyici": "🛠️ Macro Editor",
    "🔴 Canlı Tuş Kaydedici": "🔴 Live Key Recorder",
    "⚙️ Sistem & Kılavuz": "⚙️ System & Guide",
    "Profil:": "Profile:",
    "+ Profil": "+ Profile",
    "✏️ Yeniden Adlandır": "✏️ Rename",
    "🗑️ Profili Sil": "🗑️ Delete Profile",
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
    "➕ Yeni Makro": "➕ New Macro",
    "✏️ Düzenle": "✏️ Edit",
    "📑 Klonla": "📑 Duplicate",
    "✕ Sil (Del)": "✕ Delete (Del)",
    "📤 Dışa Aktar": "📤 Export",
    "📥 İçe Aktar": "📥 Import",
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
    "🛑 Güvenli Düzenleme Modu: Metin yazarken veya makro ayarları yapılırken diğer makrolar durdurulur.": (
        "🛑 Safe Editing Mode: other macros are paused while typing or editing macro settings."
    ),
    "🛑 Düzenleme modu: Metin yazarken ve ayar yaparken makrolar durduruldu.": (
        "🛑 Editing mode: macros are paused while typing and configuring."
    ),
    "Makro Yapılandırması": "Macro Configuration",
    "Makro Adı:": "Macro Name:",
    "🎯 Tuşa / İkili Kombinasyona Basarak Ayarla": "🎯 Capture Key / Key Combination",
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
    "➕ Tuş Bas-Çek": "➕ Key Tap",
    "➕ Tuşa Bas (Basılı Tut)": "➕ Key Down (Hold)",
    "Belirtilen tuşu basılı bırakır (Tuşun basılı kalması)": (
        "Holds the specified key down"
    ),
    "➕ Tuşu Bırak": "➕ Key Up",
    "Basılı tutulan tuşu serbest bırakır": "Releases the held key",
    "➕ Fare Tıkla": "➕ Mouse Click",
    "➕ Fare Basılı Tut": "➕ Mouse Down (Hold)",
    "Fare tuşunu basılı bırakır": "Holds the mouse button down",
    "➕ Fare Bırak": "➕ Mouse Up",
    "Basılı fare tuşunu serbest bırakır": "Releases the held mouse button",
    "➕ Gecikme": "➕ Delay",
    "➕ Metin Yazdır": "➕ Type Text",
    "➕ Fare Hareketi": "➕ Mouse Move",
    "İmleci belirtilen piksel kadar göreli hareket ettirir": (
        "Moves the cursor by the given relative pixels"
    ),
    "➕ Fare Tekerleği": "➕ Mouse Wheel",
    "🎯 Eylem Tuşunu Ayarla / Düzenle": "🎯 Set / Edit Action Key",
    "❌ Eylemi Sil (Del)": "❌ Delete Action (Del)",
    "🗑️ Tüm Eylemleri Sil": "🗑️ Clear All Actions",
    "▶ Makroyu Test Et": "▶ Test Macro",
    "Makro Test Ediliyor...": "Testing Macro...",
    "Makro testi başarısız.": "Macro test failed.",
    "Test için motor ikilisi bulunamadı.": "Engine binary not found for testing.",
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
    "Selam CachyOS!": "Hello CachyOS!",
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
    "🎯 Tetikleyici Tuş veya İkili Kombinasyon Ayarla": (
        "🎯 Set Trigger Key or Key Combination"
    ),
    "🛑 Tuş ayarlanırken makrolar durduruldu.": (
        "🛑 Macros paused while capturing a key."
    ),
    "🛑 Makrolar Durduruldu: Tuş ayarlarken diğer makrolar çalıştırılmaz.": (
        "🛑 Macros Stopped: other macros will not run while capturing a key."
    ),
    "Klavyenizden bir tuşa basın veya LeftShift+LeftCtrl gibi iki tuşa aynı anda basın:": (
        "Press a key, or press two keys together such as LeftShift+LeftCtrl:"
    ),
    "⏳ Tuşa veya ikili kombinasyona basın...": "⏳ Press a key or key combination...",
    "✔ Bu Tuşu / Kombinasyonu Kullan": "✔ Use This Key / Combination",
    "▶ Makro motoru tekrar aktif edildi.": "▶ Macro engine re-activated.",
    "✔ Algılandı: {}": "✔ Detected: {}",
    "✔ İkili Kombinasyon: {}": "✔ Key Combination: {}",
    "✔ Bu Tuşu Kullan ({})": "✔ Use This Key ({})",
    "💾 {}": "💾 {}",
    "⚙️ STOP Tuşunu Ayarlayın": "⚙️ Set the STOP Key",
    "STOP tuşu '{}' olarak güncellendi.": "STOP key updated to '{}'.",
    # --- Kaydedici ---
    "Olay": "Event",
    "Tuş / Buton": "Key / Button",
    "Gecikme (ms)": "Delay (ms)",
    "⏺️ Kaydı Başlat": "⏺️ Start Recording",
    "🗑️ Temizle": "🗑️ Clear",
    "💾 Kaydı Yeni Makro Olarak Ekle": "💾 Add Recording as New Macro",
    "⏹️ Kaydı Durdur": "⏹️ Stop Recording",
    "🛑 Canlı kayıt modu: Diğer tüm makrolar durduruldu.": (
        "🛑 Live recording mode: all other macros are paused."
    ),
    "Kayıtlı Makro ({} adım)": "Recorded Macro ({} steps)",
    "Canlı kaydedici ile oluşturuldu": "Created with the live recorder",
    # --- Sistem ---
    "🛡️ Donanım İzinlerini Otomatik Düzelt (udev)": (
        "🛡️ Auto-Fix Hardware Permissions (udev)"
    ),
    "🔄 Durumu Yenile": "🔄 Refresh Status",
    "⚙️ Motor derleniyor...": "⚙️ Building engine...",
    "Motor Bulunamadı": "Engine Not Found",
    "Lütfen terminalde 'cargo build --release' komutunu çalıştırın.": (
        "Run 'cargo build --release' in a terminal."
    ),
    "Makro motoru başlatıldı.": "Macro engine started.",
    "🛑 STOP Tetiklendi! Motor 'Yeniden Başlat' butonuna basılana dek kapalı kalacaktır.": (
        "🛑 STOP triggered! The engine stays off until 'Restart' is pressed."
    ),
    "Log dosyası henüz oluşmadı.": "Log file has not been created yet.",
    "Log okunamadı: ": "Could not read log: ",
    "Motor Günlüğü": "Engine Log",
    "İzinler Düzeltildi": "Permissions Fixed",
    "udev kuralı kuruldu ve motor başlatıldı.\nGrup üyeliği yeni oturumda etkinleşir; sorun sürerse oturumu kapatıp açın.": (
        "udev rule installed and engine started.\nGroup membership becomes active in a new session; log out and back in if the problem persists."
    ),
    "Geçersiz kullanıcı adı": "Invalid username",
    "Yetkilendirme başarısız (çıkış kodu {})": "Authorization failed (exit code {})",
    "[HATA] PyQt6 kütüphanesi eksik!": "[ERROR] PyQt6 library is missing!",
    "Kurulum için: sudo pacman -S python-pyqt6": "Install it with: sudo pacman -S python-pyqt6",
    "MacroStat zaten çalışıyor. Mevcut pencereyi kullanın.": (
        "MacroStat is already running. Use the existing window."
    ),
    "🔴 Motor Durduruldu (STOP)": "🔴 Engine Stopped (STOP)",
    "🛑 Düzenleme Modu (Beklemede)": "🛑 Edit Mode (Idle)",
    "🟢 Aktif": "🟢 Active",
    "📋 Günlük": "📋 Log",
    "🔴 Motor Çöktü (kod {})": "🔴 Engine Crashed (code {})",
    "🔴 Motor Durduruldu": "🔴 Engine Stopped",
    "⚠️ Hatayı İncele": "⚠️ Inspect Error",
    "♻️ Makro motoru yeniden başlatılmadan güncellendi.": (
        "♻️ Macro engine reloaded without restart."
    ),
    "▶ Makro başarıyla test edildi.": "▶ Macro tested successfully.",
    "Bu makroda eylem yok.": "This macro has no actions.",
    "=== MacroStat Donanım ve Sistem Tanılama ===\nKernel /dev/uinput: {}\nMotor İkili Dosyası: {}\nProfil Dosyası: {}\nAcil Durdurma Tuşu (STOP): {}\nLog Dosyası: {}\n": (
        "=== MacroStat Hardware and System Diagnostics ===\nKernel /dev/uinput: {}\n"
        "Engine Binary: {}\nProfile File: {}\nEmergency Stop Key (STOP): {}\nLog File: {}\n"
    ),
    # --- Yedek geri yükleme ---
    "⏪ Son Yedeği Geri Yükle": "⏪ Restore Last Backup",
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
    "➕ Yeni Profil": "➕ New Profile",
    "🔄 Motoru Yeniden Başlat": "🔄 Restart Engine",
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
    "📥 {} makro içe aktarıldı (güvenlik için devre dışı).": (
        "📥 {} macros imported (disabled for safety)."
    ),
    "📥 {} profil içe aktarıldı (makroları devre dışı).": (
        "📥 {} profiles imported (macros disabled)."
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
    "✔ Erişilebilir (Yazma İzni Var)": "✔ Accessible (Writable)",
    "❌ Erişim Yok (İzin Gerekli)": "❌ No Access (Permission Required)",
    "İkili Dosya Bulunamadı (cargo build --release çalıştırın)": (
        "Binary Not Found (run cargo build --release)"
    ),
    "Bulunamadı": "Not found",
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
