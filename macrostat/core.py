# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Pencere kurulumu, profil yaşam döngüsü, dil ve sekme yönetimi."""

from . import common, theme
from .common import *  # noqa: F401,F403
from .widgets import SlidingSwitch, KeyCaptureDialog  # noqa: F401

class CoreMixin:
    """Pencere kurulumu, profil yaşam döngüsü, dil ve sekme yönetimi."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MacroStat")
        self.resize(1000, 680)
        self.setMinimumSize(850, 550)

        self.profile_data = self.load_profile()
        # STOP tuşu aktif profilden yüklenir; varsayılan yalnızca yedektir.
        common.PANIC_KEY = self.profile_data.get("panicKey") or common.PANIC_KEY
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
        self.check_and_auto_start_daemon()

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.update_daemon_status)
        self.status_timer.start(1500)
        self.update_daemon_status()

    def load_profile(self):
        self.all_profiles = []
        self.active_profile_id = ""
        if common.PROFILE_PATH.exists():
            try:
                with open(common.PROFILE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("profiles") and isinstance(data["profiles"], list) and len(data["profiles"]) > 0:
                        self.all_profiles = data["profiles"]
                        self.active_profile_id = data.get("activeProfileId", self.all_profiles[0].get("id", ""))
                        for p in self.all_profiles:
                            if p.get("id") == self.active_profile_id:
                                return p
                        return self.all_profiles[0]
                    elif data.get("macros"):
                        self.all_profiles = [data]
                        self.active_profile_id = data.get("id", "profile-cachy")
                        return data
            except Exception as e:
                print(f"[UYARI] profile.json okunamadı: {e}")
        # Depodaki tek kanonik profil şablonu; gömülü JSON kopyası yok.
        default_p = None
        seed = SCRIPT_DIR / "profile.json"
        if seed.exists():
            try:
                with open(seed, "r", encoding="utf-8") as f:
                    seed_data = json.load(f)
                profiles = seed_data.get("profiles") or []
                if profiles:
                    default_p = profiles[0]
                elif seed_data.get("macros"):
                    default_p = seed_data
            except Exception as e:
                print(f"[UYARI] Varsayılan profil şablonu okunamadı: {e}")
        if not default_p:
            default_p = {
                "id": "profile-cachy-default",
                "name": "MacroStat Varsayılan Profil",
                "panicKey": "KEY_PAUSE",
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

            # Atomik yazma: geçici dosya + fsync + os.replace, önceki sürüm .bak olarak korunur.
            tmp_path = target_save_path.with_name(target_save_path.name + ".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            if target_save_path.exists():
                try:
                    shutil.copy2(target_save_path, target_save_path.with_name(target_save_path.name + ".bak"))
                except OSError:
                    pass
            os.replace(tmp_path, target_save_path)

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
        header_layout.setContentsMargins(14, 10, 14, 10)

        title_label = QLabel("MacroStat")
        title_label.setObjectName("appTitle")
        header_layout.addWidget(title_label)

        lbl_prof = QLabel(T("Profil:"))
        lbl_prof.setObjectName("fieldLabel")
        header_layout.addWidget(lbl_prof)

        self.combo_profiles = QComboBox()
        self.combo_profiles.setObjectName("profileCombo")
        header_layout.addWidget(self.combo_profiles)

        # Profil işlemleri tek menüde: yeni / yeniden adlandır / sil / dışa-içe aktar
        self.btn_profile_menu = QToolButton()
        self.btn_profile_menu.setObjectName("profileMenu")
        self.btn_profile_menu.setText("⋯")
        self.btn_profile_menu.setToolTip(T("Profil işlemleri"))
        self.btn_profile_menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        profile_menu = QMenu(self.btn_profile_menu)
        act_new = profile_menu.addAction(T("➕ Yeni Profil"))
        act_new.triggered.connect(self.create_new_profile_dialog)
        act_rename = profile_menu.addAction(T("✏️ Yeniden Adlandır"))
        act_rename.triggered.connect(self.rename_current_profile)
        act_delete = profile_menu.addAction(T("🗑️ Profili Sil"))
        act_delete.triggered.connect(self.delete_current_profile)
        profile_menu.addSeparator()
        act_export = profile_menu.addAction(T("📤 Dışa Aktar"))
        act_export.triggered.connect(self.export_profile)
        act_import = profile_menu.addAction(T("📥 İçe Aktar"))
        act_import.triggered.connect(self.import_profile)
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

        self.status_badge = QLabel(T("● Kontrol ediliyor..."))
        self.status_badge.setObjectName("statusBadge")
        header_layout.addWidget(self.status_badge)

        self.btn_quick_fix = QPushButton(T("🛡️ İzinleri Düzelt & Başlat"))
        theme.set_variant(self.btn_quick_fix, "primary")
        self.btn_quick_fix.clicked.connect(self.fix_permissions)
        self.btn_quick_fix.hide()
        header_layout.addWidget(self.btn_quick_fix)

        self.btn_lang = QToolButton()
        self.btn_lang.setObjectName("iconButton")
        self.btn_lang.setText("🌐")
        self.btn_lang.setToolTip(T("Dil / Language"))
        self.btn_lang.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        lang_menu = QMenu(self.btn_lang)
        current_lang = get_language()
        for code, label in LANGUAGES.items():
            action = lang_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(code == current_lang)
            action.triggered.connect(
                lambda _checked=False, lang=code: self.change_language(lang))
        self.btn_lang.setMenu(lang_menu)
        header_layout.addWidget(self.btn_lang)

        self.btn_view_log = QToolButton()
        self.btn_view_log.setObjectName("iconButton")
        self.btn_view_log.setText("📋")
        self.btn_view_log.setToolTip(T("📋 Günlüğü İncele"))
        self.btn_view_log.clicked.connect(self.show_daemon_log)
        header_layout.addWidget(self.btn_view_log)

        self.btn_restart_daemon = QToolButton()
        self.btn_restart_daemon.setObjectName("iconButton")
        self.btn_restart_daemon.setText("🔄")
        self.btn_restart_daemon.setToolTip(T("🔄 Motoru Yeniden Başlat"))
        self.btn_restart_daemon.clicked.connect(
            lambda: self.restart_daemon(show_message=True, force=True))
        header_layout.addWidget(self.btn_restart_daemon)

        # STOP Butonu + Çark Butonu
        panic_box = QWidget()
        p_layout = QHBoxLayout(panic_box)
        p_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.setSpacing(3)

        self.btn_panic = QPushButton("🛑 STOP")
        theme.set_variant(self.btn_panic, "danger")
        self.btn_panic.clicked.connect(self.trigger_panic)
        p_layout.addWidget(self.btn_panic)

        self.btn_panic_settings = QToolButton()
        self.btn_panic_settings.setObjectName("iconButton")
        self.btn_panic_settings.setText("⚙")
        self.btn_panic_settings.setToolTip(T("Acil durdurma tuşunu ayarla"))
        theme.set_variant(self.btn_panic_settings, "muted")
        self.btn_panic_settings.clicked.connect(self.configure_panic_key)
        p_layout.addWidget(self.btn_panic_settings)

        header_layout.addWidget(panic_box)
        main_layout.addWidget(header_frame)

        # Sekmeler
        self.tabs = QTabWidget()
        self.tab_macros = QWidget()
        self.tab_editor = QWidget()
        self.tab_recorder = QWidget()
        self.tab_system = QWidget()

        self.tabs.addTab(self.tab_macros, T("📋 Makrolar"))
        self.tabs.addTab(self.tab_editor, T("🛠️ Makro Düzenleyici"))
        self.tabs.addTab(self.tab_recorder, T("🔴 Canlı Tuş Kaydedici"))
        self.tabs.addTab(self.tab_system, T("⚙️ Sistem & Kılavuz"))

        self.setup_macros_tab()
        self.setup_editor_tab()
        self.setup_recorder_tab()
        self.setup_system_tab()

        self.tabs.currentChanged.connect(self.on_tab_changed)
        main_layout.addWidget(self.tabs)

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
        self.profile_data = selected_p
        self.active_profile_id = selected_p.get("id")
        common.PANIC_KEY = selected_p.get("panicKey") or "KEY_PAUSE"
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
        self.all_profiles = [p for p in self.all_profiles if p is not self.profile_data]
        self.profile_data = self.all_profiles[0]
        self.active_profile_id = self.profile_data.get("id", "")
        common.PANIC_KEY = self.profile_data.get("panicKey") or "KEY_PAUSE"
        self.populate_profile_combo()
        self.save_profile_to_disk(restart_daemon=True)
        self.refresh_macro_table()
        self.show_autosave_banner(T("Profil silindi."))

    def create_new_profile_dialog(self):
        name, ok = QInputDialog.getText(self, T("Yeni Profil"), T("Yeni profil adını girin:"))
        if ok and name.strip():
            new_p = {
                "id": f"profile-{int(time.time()*1000)}",
                "name": name.strip(),
                "panicKey": common.PANIC_KEY,
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
                self.show_autosave_banner(T("🛑 Düzenleme modu: Metin yazarken ve ayar yaparken makrolar durduruldu."))

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
                    self.show_autosave_banner(T("▶ Makro motoru tekrar aktif edildi."))

    def configure_panic_key(self):
        dialog = KeyCaptureDialog(self)
        dialog.setWindowTitle(T("⚙️ STOP Tuşunu Ayarlayın"))
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.captured_key:
            common.PANIC_KEY = dialog.captured_key
            self.profile_data["panicKey"] = common.PANIC_KEY
            self.show_autosave_banner(T("STOP tuşu '{}' olarak güncellendi.").format(common.PANIC_KEY))
            self.save_profile_to_disk(restart_daemon=True)

    def show_autosave_banner(self, text):
        self.statusBar().showMessage(f"💾 {text}", 3000)

    # SEKME 1: Makrolar
