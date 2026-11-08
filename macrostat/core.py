# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Pencere kurulumu, profil yaşam döngüsü, dil ve sekme yönetimi."""

import json
import sys
import time

from PyQt6.QtGui import QAction, QActionGroup

from . import common, theme
from .common import *  # noqa: F401,F403
from .logpanel import LogPanel
from .nav import PageStack
from .widgets import SlidingSwitch, KeyCaptureDialog  # noqa: F401

#: Profil dosyası dışarıdan düzenlenebilir; görünen metinler ve sayılar
#: yüklenirken doğrulanır ki bozuk bir dosya arayüzü kilitlemesin.
_NAME_LIMIT = 200
_DESCRIPTION_LIMIT = 4000
#: Aralıklar düzenleyicideki QSpinBox sınırlarıyla aynıdır; aksi hâlde geçerli
#: bir profil değeri arayüzde açıldığında sessizce kırpılırdı.
_MACRO_NUMBERS = {
    "repeatCount": (1, 1, 9999),
    "doubleTapTimeoutMs": (300, 50, 5_000),
    "holdDurationMs": (300, 50, 10_000),
}


def build_exclusive_menu(menu, choices, current, on_pick):
    """Birbirini dışlayan işaretli menü öğeleri ekler.

    ``QActionGroup`` kullanılmazsa Qt her işaretli öğeyi bağımsız yönetir:
    yeni tema seçildiğinde eski temanın işareti kalkmaz. Grup, seçim
    değiştiğinde önceki öğeyi kendiliğinden temizler.
    """
    group = QActionGroup(menu)
    group.setExclusive(True)
    for value, label in choices:
        action = menu.addAction(label)
        action.setCheckable(True)
        action.setChecked(value == current)
        group.addAction(action)
        action.triggered.connect(
            lambda _checked=False, picked=value: on_pick(picked))
    return group


def _fresh_id(prefix, used):
    """``used`` kümesiyle çakışmayan, motorun kabul ettiği bir kimlik üretir."""
    base = "{}-{}".format(prefix, time.time_ns() // 1_000_000)
    candidate = base
    suffix = 1
    while candidate in used:
        candidate = "{}-{}".format(base, suffix)
        suffix += 1
    used.add(candidate)
    return candidate


def _valid_plain_or_evdev_key(value, allow_button=False):
    """``KEY_*`` biçimini veya motorun düz tuş adı biçimini doğrular.

    Motor ``F9``/``PAUSE`` gibi adları da çözer; bu yüzden geçerli bir
    profil yalnızca ``KEY_`` öneki yok diye bozulmamalıdır. Her iki biçim
    de denetim karakteri ve boşluk içermez.
    """
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    if common.is_valid_key_name(candidate, allow_button=allow_button):
        return True
    return common.is_plain_key_name(candidate)


def _normalize_loaded_trigger(value):
    """Geçerli tetikleyiciyi büyük harfli kanonik biçime çevirir."""
    if not isinstance(value, str) or not common.is_valid_trigger(value):
        return ""
    return "+".join(part.strip().upper() for part in value.split("+"))


def _sanitize_loaded_actions(macro, field, used_ids):
    actions = macro.get(field)
    if not isinstance(actions, list):
        if field in macro:
            macro[field] = []
        return
    clean = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_id = action.get("id")
        if (not isinstance(action_id, str) or not common.is_valid_id(action_id)
                or action_id in used_ids):
            action_id = _fresh_id("act", used_ids)
        else:
            used_ids.add(action_id)
        action["id"] = action_id
        clean.append(action)
    macro[field] = clean


def sanitize_loaded_profile(profile, used_profile_ids=None):
    """Yüklenen profil sözlüğünü yerinde doğrular ve temizler.

    Motorla aynı güvenlik sınırlarını uygular: kimlikler, tetikleyiciler ve
    STOP/yeniden başlatma tuşları güvenli biçimde sınırlandırılır; görünen
    metinler Qt zengin metin yorumlamasına izin vermeyecek şekilde
    temizlenir. Geçerli alanlar olduğu gibi korunur; eksik alanlar
    eklenmez (motorun serde varsayılanları geçerlidir).
    """
    if not isinstance(profile, dict):
        return profile
    if used_profile_ids is None:
        used_profile_ids = set()

    profile_id = profile.get("id")
    if (not isinstance(profile_id, str) or not common.is_valid_id(profile_id)
            or profile_id in used_profile_ids):
        profile_id = _fresh_id("profile", used_profile_ids)
    else:
        used_profile_ids.add(profile_id)
    profile["id"] = profile_id

    for field, limit in (("name", _NAME_LIMIT),
                         ("description", _DESCRIPTION_LIMIT),
                         ("virtualDeviceName", _NAME_LIMIT)):
        if field in profile and not isinstance(profile[field], str):
            profile[field] = ""
        if isinstance(profile.get(field), str):
            profile[field] = common.sanitize_display_text(
                profile[field], max_len=limit)

    # virtualDeviceName motorda 80 karakterle sınırlıdır.
    if isinstance(profile.get("virtualDeviceName"), str):
        profile["virtualDeviceName"] = common.sanitize_display_text(
            profile["virtualDeviceName"], max_len=80)

    panic = profile.get("panicKey")
    if isinstance(panic, str) and _valid_plain_or_evdev_key(panic):
        profile["panicKey"] = panic.strip().upper()
    else:
        profile.pop("panicKey", None)

    restart = profile.get("restartKey")
    if (isinstance(restart, str)
            and common.is_valid_key_name(restart.strip().upper(),
                                         allow_button=False)):
        profile["restartKey"] = restart.strip().upper()
    else:
        profile.pop("restartKey", None)

    macros = profile.get("macros")
    if isinstance(macros, list):
        used_macro_ids = set()
        clean_macros = []
        for macro in macros:
            if not isinstance(macro, dict):
                continue
            macro_id = macro.get("id")
            if (not isinstance(macro_id, str)
                    or not common.is_valid_id(macro_id)
                    or macro_id in used_macro_ids):
                macro_id = _fresh_id("macro", used_macro_ids)
            else:
                used_macro_ids.add(macro_id)
            macro["id"] = macro_id

            for field, limit in (("name", _NAME_LIMIT),
                                 ("description", _DESCRIPTION_LIMIT)):
                if isinstance(macro.get(field), str):
                    macro[field] = common.sanitize_display_text(
                        macro[field], max_len=limit)
                elif field in macro:
                    macro[field] = ""

            if "enabled" in macro and not isinstance(macro["enabled"], bool):
                macro["enabled"] = False
            if "triggerKey" in macro:
                macro["triggerKey"] = _normalize_loaded_trigger(
                    macro.get("triggerKey"))
            if "triggerMode" in macro:
                mode = macro.get("triggerMode")
                macro["triggerMode"] = (
                    mode if isinstance(mode, str)
                    and mode in common.TRIGGER_MODES else "ONCE")

            for field, (default, low, high) in _MACRO_NUMBERS.items():
                if field in macro:
                    macro[field] = common.coerce_int(
                        macro[field], default, low, high)

            used_action_ids = set()
            _sanitize_loaded_actions(macro, "actions", used_action_ids)
            _sanitize_loaded_actions(macro, "releaseActions", used_action_ids)
            clean_macros.append(macro)
        profile["macros"] = clean_macros
    elif "macros" in profile:
        profile["macros"] = []
    return profile


class CoreMixin:
    """Pencere kurulumu, profil yaşam döngüsü, dil ve sekme yönetimi."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MacroStat")
        self.resize(1100, 720)
        self.setMinimumSize(900, 600)

        self.profile_data = self.load_profile()
        # STOP tuşu aktif profilden yüklenir; varsayılan yalnızca yedektir.
        common.PANIC_KEY = self.profile_data.get("panicKey") or common.PANIC_KEY
        self.restart_key = common.normalize_restart_key(
            self.profile_data.get("restartKey"))
        self.restart_watch_proc = None
        self._editor_snapshot = None
        self.selected_macro_idx = 0
        self.recording_active = False
        self.recorded_events = []
        self.last_key_time = 0.0
        self.daemon_proc = None
        self.failed_status_checks = 0
        self.is_manually_stopped = False
        self.was_editor_daemon_running = False

        self.setup_ui()
        self._onboarding_pending = not load_settings().get("onboarding_completed", False)
        if not self._onboarding_pending:
            self.check_and_auto_start_daemon()

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_daemon_status)
        self.status_timer.start(1500)
        self.update_daemon_status()
        if self._onboarding_pending:
            # Pencere göründükten sonra ilk kurulum sihirbazı açılır.
            QTimer.singleShot(150, self.maybe_run_onboarding)

    def load_profile(self):
        self.all_profiles = []
        self.active_profile_id = ""
        if common.PROFILE_PATH.exists() or common.PROFILE_PATH.is_symlink():
            # Motorla aynı güvenli okuma: O_NOFOLLOW, yalnızca normal dosya,
            # 32 MiB sınırı. Profil dosyası başka bir hedefe işaret edemez.
            try:
                data = json.loads(
                    common.read_private_text_file(common.PROFILE_PATH))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
                print(f"[UYARI] profile.json okunamadı: {e}")
                data = None
            if isinstance(data, dict):
                used_profile_ids = set()
                profiles = data.get("profiles")
                if isinstance(profiles, list) and profiles:
                    self.all_profiles = [
                        sanitize_loaded_profile(p, used_profile_ids)
                        for p in profiles if isinstance(p, dict)]
                if self.all_profiles:
                    requested = data.get("activeProfileId")
                    if (isinstance(requested, str)
                            and any(p.get("id") == requested
                                    for p in self.all_profiles)):
                        self.active_profile_id = requested
                    else:
                        self.active_profile_id = self.all_profiles[0].get(
                            "id", "")
                    for p in self.all_profiles:
                        if p.get("id") == self.active_profile_id:
                            return p
                    return self.all_profiles[0]
                elif data.get("macros"):
                    loaded = sanitize_loaded_profile(data, used_profile_ids)
                    self.all_profiles = [loaded]
                    self.active_profile_id = loaded.get("id", "")
                    return loaded
        # Depodaki tek kanonik profil şablonu; gömülü JSON kopyası yok.
        default_p = None
        seed = DEFAULT_PROFILE_PATH
        if seed.exists() or seed.is_symlink():
            try:
                seed_data = json.loads(common.read_private_text_file(seed))
                profiles = (seed_data.get("profiles") or []
                            if isinstance(seed_data, dict) else [])
                profiles = [p for p in profiles if isinstance(p, dict)]
                if profiles:
                    default_p = sanitize_loaded_profile(profiles[0])
                elif isinstance(seed_data, dict) and seed_data.get("macros"):
                    default_p = sanitize_loaded_profile(seed_data)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
                print(f"[UYARI] Varsayılan profil şablonu okunamadı: {e}")
        if not default_p:
            default_p = {
                "id": "profile-default",
                "name": "MacroStat Varsayılan Profil",
                "panicKey": "KEY_PAUSE",
                "restartKey": common.DEFAULT_RESTART_KEY,
                "virtualDeviceName": "MacroStat Virtual Engine",
                "defaultJitterMs": 2,
                "macros": [],
            }
        self.active_profile_id = default_p["id"]
        return default_p

    def save_profile_to_disk(self, restart_daemon=True):
        try:
            # Profil kendi panicKey değerini korur; özel değer ezilmez.
            self.profile_data.setdefault("panicKey", common.PANIC_KEY)
            self.profile_data.setdefault(
                "restartKey", common.normalize_restart_key(
                    self.profile_data.get("restartKey")))
            # Makro ve eylemlerin geçerli ID ve alanlara sahip olduğundan emin ol
            for m in self.profile_data.get("macros", []):
                if not m.get("id"):
                    m["id"] = f"macro-{int(time.time() * 1000)}"
                for i, act in enumerate(m.get("actions", [])):
                    if not act.get("id"):
                        act["id"] = f"act-{i + 1}"

            # Güncel profili all_profiles içinde güncelle
            found = False
            for idx, p in enumerate(self.all_profiles):
                if p.get("id") == self.profile_data.get("id"):
                    self.all_profiles[idx] = self.profile_data
                    found = True
                    break
            if not found:
                self.all_profiles.append(self.profile_data)

            payload = {
                "schemaVersion": 1,
                "activeProfileId": self.profile_data.get("id", ""),
                "profiles": self.all_profiles,
            }

            target_save_path = common.PROFILE_PATH
            target_save_path.parent.mkdir(parents=True, exist_ok=True)

            # Atomik ve özel yazma: 0600 geçici dosya + fsync + os.replace.
            # Profil adları/makrolar kişisel veridir; başka kullanıcılar
            # okuyamaz. Yedek de sembolik bağlantı izlemeden kopyalanır;
            # yedek hatası profilin kendisini bozmaz.
            if target_save_path.exists() or target_save_path.is_symlink():
                backup_path = target_save_path.with_name(
                    target_save_path.name + ".bak")
                try:
                    common.backup_private_file(
                        target_save_path, backup_path)
                except OSError:
                    pass

            common.atomic_write_private(
                target_save_path,
                json.dumps(payload, indent=2,
                           ensure_ascii=False).encode("utf-8"))

            if restart_daemon:
                self.apply_profile_to_daemon()
            return True
        except Exception as e:
            QMessageBox.critical(self, T("Hata"), T("Profil kaydedilemedi: {}").format(e))
            return False

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Üst Çubuk
        header_frame = QFrame()
        header_frame.setObjectName("headerFrame")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(8)

        title_label = QLabel("MacroStat")
        title_label.setObjectName("appTitle")
        header_layout.addWidget(title_label)

        self.combo_profiles = QComboBox()
        self.combo_profiles.setObjectName("profileCombo")
        self.combo_profiles.setToolTip(T("Aktif profil"))
        header_layout.addWidget(self.combo_profiles)

        # Profil işlemleri tek menüde: yeni / yeniden adlandır / sil
        self.btn_profile_menu = QToolButton()
        self.btn_profile_menu.setObjectName("profileMenu")
        self.btn_profile_menu.setText("⋯")
        self.btn_profile_menu.setToolTip(T("Profil işlemleri"))
        self.btn_profile_menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        profile_menu = QMenu(self.btn_profile_menu)
        act_new = profile_menu.addAction(theme.icon("list-add"), T("Yeni Profil"))
        act_new.triggered.connect(self.create_new_profile_dialog)
        act_rename = profile_menu.addAction(theme.icon("edit-rename"), T("Yeniden Adlandır"))
        act_rename.triggered.connect(self.rename_current_profile)
        act_delete = profile_menu.addAction(theme.icon("edit-delete"), T("Profili Sil"))
        act_delete.triggered.connect(self.delete_current_profile)
        self.btn_profile_menu.setMenu(profile_menu)
        header_layout.addWidget(self.btn_profile_menu)

        icon_path = SCRIPT_DIR / "assets" / "macrostat.svg"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.populate_profile_combo()
        self.combo_profiles.currentIndexChanged.connect(self.on_profile_selection_changed)

        header_layout.addStretch()

        # STOP çalıştırıldığında üst kısımda kırmızı DURDURULDU rozeti
        self.lbl_stopped = QLabel(T("DURDURULDU"))
        self.lbl_stopped.setObjectName("stoppedLabel")
        self.lbl_stopped.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_stopped.hide()
        header_layout.addWidget(self.lbl_stopped)

        self.status_badge = QLabel(T("Kontrol ediliyor..."))
        self.status_badge.setObjectName("statusBadge")
        header_layout.addWidget(self.status_badge)

        self.btn_quick_fix = QPushButton(T("İzinleri Düzelt & Başlat"))
        self.btn_quick_fix.setIcon(theme.icon("security-high"))
        theme.set_variant(self.btn_quick_fix, "primary")
        self.btn_quick_fix.clicked.connect(self.fix_permissions)
        self.btn_quick_fix.hide()
        header_layout.addWidget(self.btn_quick_fix)

        self.btn_panic = QPushButton(T("STOP"))
        self.btn_panic.setIcon(theme.icon("process-stop"))
        theme.set_variant(self.btn_panic, "danger")
        self.btn_panic.setToolTip(T("Tüm makroları hemen durdur"))
        self.btn_panic.clicked.connect(self.trigger_panic)
        header_layout.addWidget(self.btn_panic)

        # STOP sonrası motoru yeniden başlatan düğme (STOP'un hemen yanında).
        self.btn_restart_after_stop = QPushButton(T("Yeniden Başlat"))
        self.btn_restart_after_stop.setIcon(theme.icon("view-refresh"))
        self.btn_restart_after_stop.setToolTip(T(
            "STOP sonrası motoru yeniden başlatır; atanmış tuş da aynı işi yapar"))
        self.btn_restart_after_stop.setEnabled(False)
        self.btn_restart_after_stop.clicked.connect(self.restart_after_stop)
        header_layout.addWidget(self.btn_restart_after_stop)

        # Taşma menüsü: günlük, yeniden başlat, dil, tema, STOP tuşu
        self.btn_overflow = QToolButton()
        self.btn_overflow.setObjectName("iconButton")
        self.btn_overflow.setText("⋯")
        self.btn_overflow.setToolTip(T("Diğer işlemler"))
        self.btn_overflow.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        overflow = QMenu(self.btn_overflow)

        self.act_view_log = QAction(theme.icon("document-preview"),
                                    T("Günlüğü İncele"), self)
        self.act_view_log.triggered.connect(self.show_log_panel)
        overflow.addAction(self.act_view_log)

        self.act_restart_daemon = QAction(theme.icon("view-refresh"),
                                          T("Motoru Yeniden Başlat"), self)
        self.act_restart_daemon.triggered.connect(
            lambda: self.restart_daemon(show_message=True, force=True))
        overflow.addAction(self.act_restart_daemon)

        overflow.addSeparator()

        lang_menu = overflow.addMenu(theme.icon("applications-internet"),
                                     T("Dil / Language"))
        build_exclusive_menu(lang_menu, list(LANGUAGES.items()),
                             get_language(), self.change_language)

        theme_menu = overflow.addMenu(theme.icon("preferences-desktop-theme"),
                                      T("Tema"))
        build_exclusive_menu(
            theme_menu,
            (("system", T("Sistem")), ("dark", T("Koyu")), ("light", T("Açık"))),
            load_settings().get("theme", "dark"), self.change_theme_mode)

        panic_action = overflow.addAction(theme.icon("preferences-desktop-keyboard"),
                                          T("STOP Tuşunu Ayarla"))
        panic_action.triggered.connect(self.configure_panic_key)

        self.act_configure_restart_key = overflow.addAction(
            theme.icon("preferences-desktop-keyboard"),
            T("Yeniden Başlatma Tuşunu Ayarla"))
        self.act_configure_restart_key.triggered.connect(
            self.configure_restart_key)
        self.btn_overflow.setMenu(overflow)
        header_layout.addWidget(self.btn_overflow)

        main_layout.addWidget(header_frame)

        # Sayfalar: sol kenar çubuğu + yığın
        self.tabs = PageStack()
        self.tab_macros = QWidget()
        self.tab_editor = QWidget()
        self.tab_recorder = QWidget()
        self.tab_system = QWidget()

        self.tabs.add_page(self.tab_macros, T("Makrolar"), "view-list-details")
        self.tabs.add_page(self.tab_editor, T("Makro Düzenleyici"), "document-edit")
        self.tabs.add_page(self.tab_recorder, T("Canlı Tuş Kaydedici"), "media-record")
        self.tabs.add_page(self.tab_system, T("Sistem & Kılavuz"), "configure")

        self.setup_macros_tab()
        self.setup_editor_tab()
        self.setup_recorder_tab()
        self.setup_system_tab()

        self.tabs.currentChanged.connect(self.on_tab_changed)
        main_layout.addWidget(self.tabs, 1)

        # Alt canlı günlük paneli: tüm sayfalarda görünür, durumu ayarlarda saklanır.
        self.log_panel = LogPanel()
        self.log_panel.closed.connect(self.hide_log_panel)
        main_layout.addWidget(self.log_panel)
        self.log_panel.setVisible(
            load_settings().get("log_panel_visible", False))

    def change_theme_mode(self, mode):
        """Tema modunu kaydeder ve anında uygular."""
        if mode not in ("system", "dark", "light"):
            return
        data = load_settings()
        data["theme"] = mode
        save_settings(data)
        app = QApplication.instance()
        if app is not None:
            theme.apply_theme(app, mode)

    def populate_profile_combo(self):
        self.combo_profiles.blockSignals(True)
        self.combo_profiles.clear()
        current_idx = 0
        for i, p in enumerate(self.all_profiles):
            self.combo_profiles.addItem(p.get("name", f"Profil {i+1}"), p.get("id"))
            if p.get("id") == self.profile_data.get("id"):
                current_idx = i
        self.combo_profiles.setCurrentIndex(current_idx)
        self.combo_profiles.blockSignals(False)

    def on_profile_selection_changed(self, index):
        if index < 0 or index >= len(self.all_profiles):
            return
        selected_p = self.all_profiles[index]
        if selected_p.get("id") == self.profile_data.get("id"):
            return
        if not self.prepare_profile_change():
            # Kullanıcı vazgeçti; birleşik kutuyu etkin profile geri al.
            self.populate_profile_combo()
            return
        self.profile_data = selected_p
        self.active_profile_id = selected_p.get("id")
        common.PANIC_KEY = selected_p.get("panicKey") or "KEY_PAUSE"
        self.restart_key = common.normalize_restart_key(selected_p.get("restartKey"))
        if getattr(self, "is_manually_stopped", False):
            self.start_restart_watch()
        self.save_profile_to_disk(restart_daemon=True)
        self.refresh_macro_table()
        self.show_autosave_banner(T("'{}' aktif edildi. Diğer profiller devre dışıdır.").format(selected_p.get('name')))

    def change_language(self, code):
        if not code or code == get_language():
            return
        answer = QMessageBox.question(
            self, T("Dil Değişikliği"),
            T("Dil değişikliğinin uygulanması için arayüz yeniden başlatılacak. Devam edilsin mi?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        settings = load_settings()
        settings["language"] = code
        save_settings(settings)
        self.restart_application()

    def restart_application(self):
        """Arayüzü yeni dil ayarıyla yeniden başlatır (motor temiz kapanır)."""
        from .app import acquire_gui_single_instance, release_gui_single_instance

        self._force_close = True
        # Yeni örnek, eski örnek çıkış yapmadan önce açılır; kilidi önce bırak.
        release_gui_single_instance()
        started, _pid = QProcess.startDetached(
            sys.executable, [str(SCRIPT_DIR / "gui.py")])
        if not started:
            acquire_gui_single_instance()
            QMessageBox.warning(
                self, T("Hata"),
                T("Arayüz yeniden başlatılamadı. Lütfen uygulamayı elle açın."))
            return
        self.close()

    def rename_current_profile(self):
        current_name = self.profile_data.get("name", "")
        name, ok = QInputDialog.getText(
            self, T("Profili Yeniden Adlandır"), T("Yeni profil adı:"), text=current_name)
        if not ok or not name.strip() or name.strip() == current_name:
            return
        self.profile_data["name"] = name.strip()
        self.profile_data["virtualDeviceName"] = f"{name.strip()} Virtual Engine"
        self.populate_profile_combo()
        self.save_profile_to_disk(restart_daemon=True)
        self.show_autosave_banner(T("Profil yeniden adlandırıldı."))

    def delete_current_profile(self):
        if len(self.all_profiles) <= 1:
            QMessageBox.information(
                self, T("Profili Sil"), T("Son profil silinemez."))
            return
        name = self.profile_data.get("name", "")
        answer = QMessageBox.question(
            self, T("Profili Sil"),
            T("'{}' profili silinsin mi? Bu işlem geri alınamaz.").format(name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not self.prepare_profile_change():
            return
        self.all_profiles = [p for p in self.all_profiles if p is not self.profile_data]
        self.profile_data = self.all_profiles[0]
        self.active_profile_id = self.profile_data.get("id", "")
        common.PANIC_KEY = self.profile_data.get("panicKey") or "KEY_PAUSE"
        self.restart_key = common.normalize_restart_key(
            self.profile_data.get("restartKey"))
        self.populate_profile_combo()
        self.save_profile_to_disk(restart_daemon=True)
        self.refresh_macro_table()
        self.show_autosave_banner(T("Profil silindi."))

    def create_new_profile_dialog(self):
        name, ok = QInputDialog.getText(self, T("Yeni Profil"), T("Yeni profil adını girin:"))
        if ok and name.strip():
            if not self.prepare_profile_change():
                return
            new_p = {
                "id": f"profile-{int(time.time()*1000)}",
                "name": name.strip(),
                "panicKey": common.PANIC_KEY,
                "restartKey": self.restart_key,
                "virtualDeviceName": f"{name.strip()} Virtual Engine",
                "defaultJitterMs": 2,
                "macros": []
            }
            self.all_profiles.append(new_p)
            self.profile_data = new_p
            self.active_profile_id = new_p["id"]
            self.populate_profile_combo()
            self.save_profile_to_disk(restart_daemon=True)
            self.refresh_macro_table()
            self.show_autosave_banner(T("'{}' profili oluşturuldu ve aktif edildi.").format(name.strip()))

    _MODE_REVERSE = ["ONCE", "WHILE_HELD", "TOGGLE_LOOP", "REPEAT_COUNT",
                     "DOUBLE_TAP", "HOLD_LONG_PRESS", "PRESS_AND_RELEASE"]

    def editor_has_unsaved_changes(self):
        if getattr(self, "_editor_snapshot", None) is None:
            return False
        idx = self.combo_mode.currentIndex()
        current = (
            self.edit_name.text().strip() or "İsimsiz Makro",
            self.combo_trigger_key.currentText().strip(),
            self._MODE_REVERSE[idx] if 0 <= idx < len(self._MODE_REVERSE) else "ONCE",
            self.spin_repeat.value(),
            self.spin_double_tap.value(),
            self.spin_hold.value(),
            json.dumps(getattr(self, "current_editing_actions", []),
                       sort_keys=True, ensure_ascii=False),
            json.dumps(getattr(self, "current_release_actions", []),
                       sort_keys=True, ensure_ascii=False),
        )
        return current != self._editor_snapshot

    def confirm_discard_editor_changes(self):
        """Düzenleyicideki kaydedilmemiş değişiklikler sessizce kaybolmasın."""
        if not self.editor_has_unsaved_changes():
            return True
        answer = QMessageBox.question(
            self, T("Kaydedilmemiş Değişiklikler"),
            T("Makro düzenleyicisinde kaydedilmemiş değişiklikler var.\nKaydetmek ister misiniz?"),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Save:
            self.save_macro_from_editor()
            return True
        return answer != QMessageBox.StandardButton.Cancel

    def prepare_profile_change(self):
        """Profil değişmeden önce kaydedilmemiş düzenleyici hâlini sorar.

        İptalde ``False`` döner ve çağıran işlem yapılmaz. Onayda düzenleyici
        kapatılır; aksi hâlde eski profile ait değerler yeni profile
        kaydedilebilirdi.
        """
        if not self.confirm_discard_editor_changes():
            return False
        self._editor_snapshot = None
        if getattr(self, "_editor_active", False):
            self._editor_active = False
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(0)
            self.tabs.blockSignals(False)
        return True

    def on_tab_changed(self, index):
        if index != 1 and getattr(self, "_editor_active", False):
            if not self.confirm_discard_editor_changes():
                self.tabs.blockSignals(True)
                self.tabs.setCurrentIndex(1)
                self.tabs.blockSignals(False)
                return
            self._editor_active = False

        if index == 1:
            self._editor_active = True
            # Makro düzenlerken ve metin yazarken diğer tüm makrolar durdurulsun
            if self.is_daemon_running() and not getattr(self, "is_manually_stopped", False):
                self.was_editor_daemon_running = True
                self.stop_daemon()
                self.show_autosave_banner(T("Düzenleme modu: Metin yazarken ve ayar yaparken makrolar durduruldu."))

            row = self.macro_table.currentRow()
            if 0 <= row < len(self.profile_data.get("macros", [])):
                self.selected_macro_idx = row
            if 0 <= self.selected_macro_idx < len(self.profile_data.get("macros", [])):
                self.load_macro_into_editor(self.selected_macro_idx)
        else:
            # Düzenleyiciden çıkıldığında motoru yeniden başlat (STOP tuşuna basılmamışsa)
            if getattr(self, "was_editor_daemon_running", False):
                self.was_editor_daemon_running = False
                if not getattr(self, "is_manually_stopped", False):
                    self.restart_daemon(show_message=False)
                    self.show_autosave_banner(T("Makro motoru tekrar aktif edildi."))

    def configure_panic_key(self):
        dialog = KeyCaptureDialog(self)
        dialog.setWindowTitle(T("STOP Tuşunu Ayarlayın"))
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.captured_key:
            common.PANIC_KEY = dialog.captured_key
            self.profile_data["panicKey"] = common.PANIC_KEY
            self.show_autosave_banner(T("STOP tuşu '{}' olarak güncellendi.").format(common.PANIC_KEY))
            self.save_profile_to_disk(restart_daemon=True)

    def configure_restart_key(self):
        dialog = KeyCaptureDialog(self)
        dialog.setWindowTitle(T("Yeniden Başlatma Tuşunu Ayarlayın"))
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.captured_key:
            return
        key = common.normalize_restart_key(dialog.captured_key)
        if key != dialog.captured_key.strip().upper():
            QMessageBox.warning(
                self, T("Geçersiz Tuş"),
                T("Yeniden başlatma tuşu bir klavye tuşu olmalıdır (ör. KEY_F12)."))
            return
        self.restart_key = key
        self.profile_data["restartKey"] = key
        self.show_autosave_banner(
            T("Yeniden başlatma tuşu '{}' olarak güncellendi.").format(key))
        self.save_profile_to_disk(restart_daemon=False)
        if getattr(self, "is_manually_stopped", False):
            self.start_restart_watch()

    def maybe_run_onboarding(self):
        """Yalnızca ilk açılışta sihirbazı gösterir."""
        if not getattr(self, "_onboarding_pending", False):
            return
        self._onboarding_pending = False
        if not self.run_onboarding_wizard():
            # İptal edilirse mevcut otomatik motor başlatma davranışı korunur.
            self.check_and_auto_start_daemon()

    def run_onboarding_wizard(self):
        """Kurulum sihirbazını açar; kabul edildiyse True döndürür."""
        from .onboarding import OnboardingWizard

        wizard = OnboardingWizard(self)
        accepted = wizard.exec() == QDialog.DialogCode.Accepted
        if (accepted and wizard.start_engine_requested()
                and not self.is_manually_stopped and not self.is_daemon_running()):
            self.restart_daemon(show_message=False)
        self.update_daemon_status()
        return accepted

    def show_log_panel(self):
        """Günlük panelini açar; tercih `settings.json`'a yazılır."""
        self.log_panel.show()
        self.log_panel.refresh_now()
        self._save_log_panel_visibility(True)

    def hide_log_panel(self):
        self.log_panel.hide()
        self._save_log_panel_visibility(False)

    def _save_log_panel_visibility(self, visible):
        data = load_settings()
        if data.get("log_panel_visible") != visible:
            data["log_panel_visible"] = visible
            save_settings(data)

    def show_autosave_banner(self, text):
        self.statusBar().showMessage(f"{text}", 3000)

    # SEKME 1: Makrolar
