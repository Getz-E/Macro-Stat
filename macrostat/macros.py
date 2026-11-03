# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Makro listesi, içe/dışa aktarma ve profil yönetimi."""

from . import common, theme
from .common import *  # noqa: F401,F403
from .widgets import SlidingSwitch, KeyCaptureDialog  # noqa: F401

class MacrosMixin:
    """Makro listesi, içe/dışa aktarma ve profil yönetimi."""

    def setup_macros_tab(self):
        layout = QVBoxLayout(self.tab_macros)
        layout.setSpacing(10)

        self.macro_table = QTableWidget()
        self.macro_table.setColumnCount(7)
        self.macro_table.setHorizontalHeaderLabels([T("Sıra"), T("Aç / Kapat"), T("Makro Adı"), T("Tetikleyici Tuş"), T("Çalışma Modu"), T("Eylemler"), T("Sil")])
        self.macro_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.macro_table.horizontalHeader().resizeSection(0, 95)
        self.macro_table.horizontalHeader().resizeSection(1, 120)
        self.macro_table.horizontalHeader().resizeSection(3, 140)
        self.macro_table.horizontalHeader().resizeSection(4, 130)
        self.macro_table.horizontalHeader().resizeSection(5, 75)
        self.macro_table.horizontalHeader().resizeSection(6, 50)
        self.macro_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.macro_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.macro_table.itemDoubleClicked.connect(self.edit_selected_macro)

        def macro_table_keyPressEvent(event):
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self.delete_selected_macro()
                return
            QTableWidget.keyPressEvent(self.macro_table, event)
        self.macro_table.keyPressEvent = macro_table_keyPressEvent

        layout.addWidget(self.macro_table)

        btn_layout = QHBoxLayout()
        self.btn_add_macro = QPushButton(T("➕ Yeni Makro"))
        self.btn_add_macro.clicked.connect(self.create_new_macro)
        btn_layout.addWidget(self.btn_add_macro)

        self.btn_edit_macro = QPushButton(T("✏️ Düzenle"))
        self.btn_edit_macro.clicked.connect(self.edit_selected_macro)
        btn_layout.addWidget(self.btn_edit_macro)

        self.btn_dup_macro = QPushButton(T("📑 Klonla"))
        self.btn_dup_macro.clicked.connect(self.duplicate_selected_macro)
        btn_layout.addWidget(self.btn_dup_macro)

        self.btn_del_macro = QPushButton(T("✕ Sil (Del)"))
        theme.set_variant(self.btn_del_macro, "ghostDanger")
        self.btn_del_macro.clicked.connect(self.delete_selected_macro)
        btn_layout.addWidget(self.btn_del_macro)

        self.btn_export = QPushButton(T("📤 Dışa Aktar"))
        self.btn_export.clicked.connect(self.export_profile)
        btn_layout.addWidget(self.btn_export)

        self.btn_import = QPushButton(T("📥 İçe Aktar"))
        self.btn_import.clicked.connect(self.import_profile)
        btn_layout.addWidget(self.btn_import)

        btn_layout.addStretch()

        self.btn_save_all = QPushButton(T("Kaydet"))
        theme.set_variant(self.btn_save_all, "success")
        self.btn_save_all.clicked.connect(lambda: self.save_profile_to_disk(restart_daemon=True))
        btn_layout.addWidget(self.btn_save_all)

        layout.addLayout(btn_layout)
        self.refresh_macro_table()

    def export_profile(self):
        box = QMessageBox(self)
        box.setWindowTitle(T("Dışa Aktarım Kapsamı"))
        box.setText(T("Yalnızca aktif profili mi, tüm profilleri mi dışa aktarmak istersiniz?"))
        btn_active = box.addButton(T("Aktif Profil"), QMessageBox.ButtonRole.AcceptRole)
        btn_all = box.addButton(T("Tüm Profiller"), QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked is btn_active:
            profiles = [self.profile_data]
            default_name = f"macrostat-{self.profile_data.get('id', 'profil')}.json"
        elif clicked is btn_all:
            profiles = self.all_profiles
            default_name = "macrostat-tum-profiller.json"
        else:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, T("Profili Dışa Aktar"), str(Path.home() / default_name), "JSON (*.json)")
        if not path:
            return
        payload = {
            "schemaVersion": 1,
            "exportedAt": int(time.time() * 1000),
            "activeProfileId": self.active_profile_id,
            "profiles": profiles,
        }
        tmp = Path(path).with_name(Path(path).name + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp, path)
            prefix = T("Tüm profiller dışa aktarıldı: ") if clicked is btn_all \
                else T("Profil dışa aktarıldı: ")
            self.show_autosave_banner(prefix + str(path))
        except Exception as e:
            QMessageBox.critical(self, T("Dışa Aktarma Hatası"), str(e))

    def import_profile(self):
        path, _ = QFileDialog.getOpenFileName(
            self, T("Makro / Profil İçe Aktar"), str(Path.home()), "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            base = int(time.time() * 1000)
            profiles = data.get("profiles") if isinstance(data, dict) else None
            if isinstance(profiles, list) and profiles:
                # Sarmalayıcı dosya: profilleri ayrı profiller olarak ekle.
                imported_profiles = []
                for i, profile in enumerate(profiles):
                    if not isinstance(profile, dict):
                        continue
                    imported_p = copy.deepcopy(profile)
                    imported_p["id"] = f"profile-{base}-{i}"
                    imported_p["name"] = (
                        (imported_p.get("name") or "Profil") + T(" (İçe Aktarıldı)"))
                    for j, macro in enumerate(imported_p.get("macros", [])):
                        macro["id"] = f"macro-{base}-{i}-{j}"
                        macro["enabled"] = False
                        for k, action in enumerate(macro.get("actions", [])):
                            action["id"] = f"act-{base}-{i}-{j}-{k}"
                        for k, action in enumerate(macro.get("releaseActions", [])):
                            action["id"] = f"rel-{base}-{i}-{j}-{k}"
                    imported_profiles.append(imported_p)
                if not imported_profiles:
                    raise ValueError(T("Dosyada içe aktarılabilir makro/profil bulunamadı."))
                self.all_profiles.extend(imported_profiles)
                self.populate_profile_combo()
                self.save_profile_to_disk(restart_daemon=True)
                self.refresh_macro_table()
                self.show_autosave_banner(
                    T("📥 {} profil içe aktarıldı (makroları devre dışı).").format(
                        len(imported_profiles)))
                return

            macros = []
            if isinstance(data, list):
                macros = [m for m in data if isinstance(m, dict)
                          and ("triggerKey" in m or "trigger_key" in m)]
            elif isinstance(data, dict) and isinstance(data.get("macros"), list):
                macros = data["macros"]

            if not macros:
                raise ValueError(T("Dosyada içe aktarılabilir makro/profil bulunamadı."))

            for i, macro in enumerate(macros):
                imported = copy.deepcopy(macro)
                imported["id"] = f"macro-{base}-{i}"
                imported["name"] = (imported.get('name') or 'Makro') + T(" (İçe Aktarıldı)")
                # Güvenlik: içe aktarılan makrolar kullanıcı onaylayana dek kapalıdır.
                imported["enabled"] = False
                for j, action in enumerate(imported.get("actions", [])):
                    action["id"] = f"act-{base}-{i}-{j}"
                for j, action in enumerate(imported.get("releaseActions", [])):
                    action["id"] = f"rel-{base}-{i}-{j}"
                self.profile_data.setdefault("macros", []).append(imported)

            self.save_profile_to_disk(restart_daemon=True)
            self.refresh_macro_table()
            self.show_autosave_banner(
                T("📥 {} makro içe aktarıldı (güvenlik için devre dışı).").format(len(macros)))
        except Exception as e:
            QMessageBox.critical(self, T("İçe Aktarma Hatası"), str(e))

    def refresh_macro_table(self):
        macros = self.profile_data.get("macros", [])
        self.macro_table.setRowCount(len(macros))
        for row, m in enumerate(macros):
            is_active = m.get("enabled", True)

            # Sıra numarası ve hemen yanında yukarı ok, aşağı ok butonları (1 ↑ ↓)
            seq_container = QWidget()
            seq_layout = QHBoxLayout(seq_container)
            seq_layout.setContentsMargins(4, 2, 4, 2)
            seq_layout.setSpacing(4)
            seq_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            lbl_seq = QLabel(str(row + 1))
            lbl_seq.setObjectName("sequenceLabel")
            seq_layout.addWidget(lbl_seq)

            btn_up = QPushButton("↑")
            btn_up.setFixedSize(22, 22)
            btn_up.setProperty("compact", "true")
            btn_up.setToolTip(T("Yukarı Taşı (Yukarı Ok)"))
            btn_up.setEnabled(row > 0)
            btn_up.clicked.connect(lambda _, r=row: self.move_macro_up_index(r))
            seq_layout.addWidget(btn_up)

            btn_down = QPushButton("↓")
            btn_down.setFixedSize(22, 22)
            btn_down.setProperty("compact", "true")
            btn_down.setToolTip(T("Aşağı Taşı (Aşağı Ok)"))
            btn_down.setEnabled(row < len(macros) - 1)
            btn_down.clicked.connect(lambda _, r=row: self.move_macro_down_index(r))
            seq_layout.addWidget(btn_down)

            self.macro_table.setCellWidget(row, 0, seq_container)

            # Switch
            switch_container = QWidget()
            s_layout = QHBoxLayout(switch_container)
            s_layout.setContentsMargins(6, 2, 6, 2)
            s_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            switch_w = SlidingSwitch(checked=is_active)
            lbl_s = QLabel(T("AÇIK") if is_active else T("KAPALI"))
            lbl_s.setObjectName("stateLabel")
            theme.set_state(lbl_s, "on" if is_active else "off")

            def make_toggle(r_idx, label):
                def cb(checked):
                    label.setText(T("AÇIK") if checked else T("KAPALI"))
                    theme.set_state(label, "on" if checked else "off")
                    self.on_macro_toggle_switch(r_idx, checked)
                return cb

            switch_w.toggled.connect(make_toggle(row, lbl_s))
            s_layout.addWidget(switch_w)
            s_layout.addWidget(lbl_s)
            self.macro_table.setCellWidget(row, 1, switch_container)

            self.macro_table.setItem(row, 2, QTableWidgetItem(m.get("name", "İsimsiz Makro")))
            self.macro_table.setItem(row, 3, QTableWidgetItem(m.get("triggerKey", m.get("trigger_key", ""))))
            self.macro_table.setItem(row, 4, QTableWidgetItem(m.get("triggerMode", m.get("trigger_mode", "ONCE"))))
            self.macro_table.setItem(row, 5, QTableWidgetItem(str(len(m.get("actions", [])))))

            # Kırmızı X (Kırmızı Çarpı) şeklinde silme butonu
            del_container = QWidget()
            del_layout = QHBoxLayout(del_container)
            del_layout.setContentsMargins(4, 2, 4, 2)
            del_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            btn_x = QPushButton("✕")
            btn_x.setFixedSize(26, 24)
            theme.set_variant(btn_x, "ghostDanger")
            btn_x.setProperty("compact", "true")
            btn_x.setToolTip(T("Makroyu Sil (Kırmızı X)"))
            btn_x.clicked.connect(lambda _, r=row: self.delete_macro_by_index(r))
            del_layout.addWidget(btn_x)
            self.macro_table.setCellWidget(row, 6, del_container)

    def on_macro_toggle_switch(self, row, checked):
        macros = self.profile_data.get("macros", [])
        if 0 <= row < len(macros):
            macros[row]["enabled"] = checked
            self.save_profile_to_disk(restart_daemon=True)

    def move_macro_up_index(self, row):
        macros = self.profile_data.get("macros", [])
        if 1 <= row < len(macros):
            macros[row - 1], macros[row] = macros[row], macros[row - 1]
            self.save_profile_to_disk(restart_daemon=True)
            self.refresh_macro_table()
            self.macro_table.selectRow(row - 1)

    def move_macro_down_index(self, row):
        macros = self.profile_data.get("macros", [])
        if 0 <= row < len(macros) - 1:
            macros[row + 1], macros[row] = macros[row], macros[row + 1]
            self.save_profile_to_disk(restart_daemon=True)
            self.refresh_macro_table()
            self.macro_table.selectRow(row + 1)

    def delete_macro_by_index(self, index):
        macros = self.profile_data.get("macros", [])
        if 0 <= index < len(macros):
            del macros[index]
            self.save_profile_to_disk(restart_daemon=True)
            self.refresh_macro_table()

    def delete_selected_macro(self):
        row = self.macro_table.currentRow()
        if row >= 0:
            self.delete_macro_by_index(row)

    def create_new_macro(self):
        new_m = {
            "id": f"macro-{int(time.time() * 1000)}",
            "name": "Yeni Makro",
            "description": "Kullanıcı tanımlı makro",
            "enabled": True,
            "triggerKey": "KEY_LEFTSHIFT+KEY_LEFTCTRL",
            "triggerMode": "ONCE",
            "repeatCount": 1,
            "actions": [
                {"type": "KEY_TAP", "key": "KEY_X"},
                {"type": "DELAY", "delayMs": 50, "jitterMs": 2}
            ]
        }
        self.profile_data.setdefault("macros", []).append(new_m)
        self.save_profile_to_disk(restart_daemon=True)
        self.selected_macro_idx = len(self.profile_data["macros"]) - 1
        self.refresh_macro_table()
        self.load_macro_into_editor(self.selected_macro_idx)
        self.tabs.setCurrentWidget(self.tab_editor)

    def edit_selected_macro(self):
        row = self.macro_table.currentRow()
        if row >= 0:
            self.selected_macro_idx = row
            self.load_macro_into_editor(row)
            self.tabs.setCurrentWidget(self.tab_editor)

    def duplicate_selected_macro(self):
        row = self.macro_table.currentRow()
        if row >= 0:
            m = dict(self.profile_data["macros"][row])
            m["id"] = f"macro-{int(time.time() * 1000)}"
            m["name"] = m.get("name", "") + " (Kopya)"
            m["triggerKey"] = ""
            m["enabled"] = False
            self.profile_data["macros"].append(m)
            self.save_profile_to_disk(restart_daemon=True)
            self.refresh_macro_table()

    # SEKME 2: Makro Düzenleyici
