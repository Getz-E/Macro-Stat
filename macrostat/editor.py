# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Makro düzenleyici, eylem tablosu ve test çalıştırma."""

from . import common, theme
from .common import *  # noqa: F401,F403
from .widgets import SlidingSwitch, KeyCaptureDialog  # noqa: F401

class EditorMixin:
    """Makro düzenleyici, eylem tablosu ve test çalıştırma."""

    def setup_editor_tab(self):
        layout = QVBoxLayout(self.tab_editor)
        layout.setSpacing(10)

        # Düzenleyici Üst Bilgi Rozeti (Makrolar Durduruldu Bildirimi)
        editor_banner = QFrame()
        editor_banner.setObjectName("infoBanner")
        eb_layout = QHBoxLayout(editor_banner)
        eb_layout.setContentsMargins(4, 2, 4, 2)
        lbl_eb = QLabel(T("🛑 Güvenli Düzenleme Modu: Metin yazarken veya makro ayarları yapılırken diğer makrolar durdurulur."))
        lbl_eb.setObjectName("bannerText")
        eb_layout.addWidget(lbl_eb)
        layout.addWidget(editor_banner)

        form_group = QGroupBox(T("Makro Yapılandırması"))
        form_layout = QFormLayout(form_group)

        self.edit_name = QLineEdit()
        form_layout.addRow(T("Makro Adı:"), self.edit_name)

        trig_row = QHBoxLayout()
        self.combo_trigger_key = QComboBox()
        self.combo_trigger_key.setEditable(True)
        self.combo_trigger_key.addItems([
            "KEY_LEFTSHIFT+KEY_LEFTCTRL", "KEY_LEFTCTRL+KEY_SPACE", "KEY_LEFTSHIFT+KEY_SPACE",
            "KEY_F1", "KEY_F2", "KEY_F3", "KEY_F4", "KEY_F5", "KEY_F6", "KEY_F7", "KEY_F8",
            "KEY_SPACE", "KEY_X", "KEY_C", "KEY_V", "BTN_SIDE", "BTN_EXTRA"
        ])
        trig_row.addWidget(self.combo_trigger_key)

        btn_capture = QPushButton(T("🎯 Tuşa / İkili Kombinasyona Basarak Ayarla"))
        theme.set_variant(btn_capture, "primary")
        btn_capture.clicked.connect(self.capture_trigger_key)
        trig_row.addWidget(btn_capture)
        form_layout.addRow(T("Tetikleyici Tuş:"), trig_row)

        self.combo_mode = QComboBox()
        self.combo_mode.addItems([
            T("Tek Seferlik (ONCE)"),
            T("Basılı Tutulduğu Sürece (WHILE_HELD)"),
            T("Aç / Kapa Döngüsü (TOGGLE_LOOP)"),
            T("Tekrar Sayısı (REPEAT_COUNT)"),
            T("Çift Dokunma (DOUBLE_TAP)"),
            T("Uzun Basım (HOLD_LONG_PRESS)"),
            T("Bas-Bırak Çift Eylemi (PRESS_AND_RELEASE)")
        ])
        form_layout.addRow(T("Çalışma Modu:"), self.combo_mode)

        self.spin_repeat = QSpinBox()
        self.spin_repeat.setRange(1, 9999)
        self.spin_repeat.setValue(1)
        form_layout.addRow(T("Tekrar Sayısı:"), self.spin_repeat)

        self.spin_double_tap = QSpinBox()
        self.spin_double_tap.setRange(50, 5000)
        self.spin_double_tap.setValue(300)
        self.spin_double_tap.setSuffix(" ms")
        self.spin_double_tap.setToolTip(T("Çift Dokunma modunda iki basış arasındaki en büyük süre"))
        form_layout.addRow(T("Çift Dokunma Aralığı:"), self.spin_double_tap)

        self.spin_hold = QSpinBox()
        self.spin_hold.setRange(50, 10000)
        self.spin_hold.setValue(300)
        self.spin_hold.setSuffix(" ms")
        self.spin_hold.setToolTip(T("Uzun Basım modunda makronun devreye girdiği basılı tutma süresi"))
        form_layout.addRow(T("Uzun Basım Eşiği:"), self.spin_hold)

        layout.addWidget(form_group)

        # Basış / Bırakış eylem listesi seçimi
        list_row = QHBoxLayout()
        list_row.addWidget(QLabel(T("Düzenlenen liste:")))
        self.combo_action_list = QComboBox()
        self.combo_action_list.addItems([
            T("Basış Eylemleri"),
            T("Bırakış Eylemleri (PRESS_AND_RELEASE)"),
        ])
        self.combo_action_list.currentIndexChanged.connect(
            lambda _idx: self.refresh_editor_actions_table()
        )
        list_row.addWidget(self.combo_action_list)
        list_row.addStretch()
        layout.addLayout(list_row)

        # Eylemler Tablosu
        self.action_table = QTableWidget()
        self.action_table.setColumnCount(3)
        self.action_table.setHorizontalHeaderLabels([T("Sıra"), T("Eylem Tipi"), T("Parametreler")])
        self.action_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.action_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.action_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        # Makro eylemlerini DEL tuşuyla silme desteği
        def action_table_keyPressEvent(event):
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self.delete_editor_action()
                return
            QTableWidget.keyPressEvent(self.action_table, event)
        self.action_table.keyPressEvent = action_table_keyPressEvent

        self.action_table.cellDoubleClicked.connect(lambda r, c: self.edit_selected_editor_action())
        layout.addWidget(self.action_table)

        # 1. Sıra Eylem Ekleme Butonları (Klavye & Fare Basılı Tutma / Bırakma Dahil)
        act_row1 = QHBoxLayout()
        btn_add_tap = QPushButton(T("➕ Tuş Bas-Çek"))
        theme.set_variant(btn_add_tap, "primary")
        btn_add_tap.clicked.connect(lambda: self.add_editor_action("KEY_TAP"))
        act_row1.addWidget(btn_add_tap)

        btn_add_down = QPushButton(T("➕ Tuşa Bas (Basılı Tut)"))
        theme.set_variant(btn_add_down, "primary")
        btn_add_down.setToolTip(T("Belirtilen tuşu basılı bırakır (Tuşun basılı kalması)"))
        btn_add_down.clicked.connect(lambda: self.add_editor_action("KEY_DOWN"))
        act_row1.addWidget(btn_add_down)

        btn_add_up = QPushButton(T("➕ Tuşu Bırak"))
        theme.set_variant(btn_add_up, "muted")
        btn_add_up.setToolTip(T("Basılı tutulan tuşu serbest bırakır"))
        btn_add_up.clicked.connect(lambda: self.add_editor_action("KEY_UP"))
        act_row1.addWidget(btn_add_up)

        btn_add_mclick = QPushButton(T("➕ Fare Tıkla"))
        theme.set_variant(btn_add_mclick, "warning")
        btn_add_mclick.clicked.connect(lambda: self.add_editor_action("MOUSE_CLICK"))
        act_row1.addWidget(btn_add_mclick)

        btn_add_mdown = QPushButton(T("➕ Fare Basılı Tut"))
        theme.set_variant(btn_add_mdown, "warning")
        btn_add_mdown.setToolTip(T("Fare tuşunu basılı bırakır"))
        btn_add_mdown.clicked.connect(lambda: self.add_editor_action("MOUSE_DOWN"))
        act_row1.addWidget(btn_add_mdown)

        btn_add_mup = QPushButton(T("➕ Fare Bırak"))
        theme.set_variant(btn_add_mup, "muted")
        btn_add_mup.setToolTip(T("Basılı fare tuşunu serbest bırakır"))
        btn_add_mup.clicked.connect(lambda: self.add_editor_action("MOUSE_UP"))
        act_row1.addWidget(btn_add_mup)

        layout.addLayout(act_row1)

        # 2. Sıra: Gecikme, Metin, Eylem Düzenleme, Silme ve Kaydetme Butonları
        act_row2 = QHBoxLayout()
        btn_add_del = QPushButton(T("➕ Gecikme"))
        btn_add_del.clicked.connect(lambda: self.add_editor_action("DELAY"))
        act_row2.addWidget(btn_add_del)

        btn_add_text = QPushButton(T("➕ Metin Yazdır"))
        btn_add_text.clicked.connect(lambda: self.add_editor_action("TEXT"))
        act_row2.addWidget(btn_add_text)

        btn_add_move = QPushButton(T("➕ Fare Hareketi"))
        btn_add_move.setToolTip(T("İmleci belirtilen piksel kadar göreli hareket ettirir"))
        btn_add_move.clicked.connect(lambda: self.add_editor_action("MOUSE_MOVE"))
        act_row2.addWidget(btn_add_move)

        btn_add_scroll = QPushButton(T("➕ Fare Tekerleği"))
        btn_add_scroll.clicked.connect(lambda: self.add_editor_action("MOUSE_SCROLL"))
        act_row2.addWidget(btn_add_scroll)

        btn_edit_act = QPushButton(T("🎯 Eylem Tuşunu Ayarla / Düzenle"))
        theme.set_variant(btn_edit_act, "accent")
        btn_edit_act.clicked.connect(self.edit_selected_editor_action)
        act_row2.addWidget(btn_edit_act)

        btn_del_act = QPushButton(T("❌ Eylemi Sil (Del)"))
        btn_del_act.clicked.connect(self.delete_editor_action)
        act_row2.addWidget(btn_del_act)

        btn_clear_all = QPushButton(T("🗑️ Tüm Eylemleri Sil"))
        theme.set_variant(btn_clear_all, "ghostDanger")
        btn_clear_all.clicked.connect(self.clear_all_editor_actions)
        act_row2.addWidget(btn_clear_all)

        act_row2.addStretch()

        self.btn_test_macro = QPushButton(T("▶ Makroyu Test Et"))
        self.btn_test_macro.setToolTip(T(
            "Test sırasında diğer makrolar etkilenmez; yalnızca bu makronun eylemleri çalıştırılır."))
        theme.set_variant(self.btn_test_macro, "violet")
        self.btn_test_macro.clicked.connect(self.test_current_macro)
        act_row2.addWidget(self.btn_test_macro)

        self.btn_save_macro = QPushButton(T("Kaydet"))
        theme.set_variant(self.btn_save_macro, "success")
        self.btn_save_macro.clicked.connect(self.save_macro_from_editor)
        act_row2.addWidget(self.btn_save_macro)

        layout.addLayout(act_row2)

    def capture_trigger_key(self):
        dlg = KeyCaptureDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.captured_key:
            self.combo_trigger_key.setEditText(dlg.captured_key)

    def load_macro_into_editor(self, idx):
        macros = self.profile_data.get("macros", [])
        if 0 <= idx < len(macros):
            m = macros[idx]
            self.edit_name.setText(m.get("name", ""))
            self.combo_trigger_key.setEditText(m.get("triggerKey", m.get("trigger_key", "")))
            mode_map = {
                "ONCE": 0,
                "WHILE_HELD": 1,
                "TOGGLE_LOOP": 2,
                "REPEAT_COUNT": 3,
                "DOUBLE_TAP": 4,
                "HOLD_LONG_PRESS": 5,
                "PRESS_AND_RELEASE": 6,
            }
            m_mode = m.get("triggerMode", m.get("trigger_mode", "ONCE"))
            self.combo_mode.setCurrentIndex(mode_map.get(m_mode, 0))
            self.spin_repeat.setValue(int(m.get("repeatCount", m.get("repeat_count", 1))))
            self.current_editing_actions = copy.deepcopy(m.get("actions", []))
            self.current_release_actions = copy.deepcopy(m.get("release_actions", []))
            self.spin_double_tap.setValue(int(
                m.get("doubleTapTimeoutMs", m.get("double_tap_timeout_ms", 300))))
            self.spin_hold.setValue(int(
                m.get("holdDurationMs", m.get("hold_duration_ms", 300))))
            self.combo_action_list.blockSignals(True)
            self.combo_action_list.setCurrentIndex(0)
            self.combo_action_list.blockSignals(False)
            self.refresh_editor_actions_table()
            idx_mode = self.combo_mode.currentIndex()
            self._editor_snapshot = (
                self.edit_name.text().strip() or "İsimsiz Makro",
                self.combo_trigger_key.currentText().strip(),
                self._MODE_REVERSE[idx_mode] if 0 <= idx_mode < len(self._MODE_REVERSE) else "ONCE",
                self.spin_repeat.value(),
                self.spin_double_tap.value(),
                self.spin_hold.value(),
                json.dumps(self.current_editing_actions, sort_keys=True, ensure_ascii=False),
                json.dumps(self.current_release_actions, sort_keys=True, ensure_ascii=False),
            )

    def _active_actions(self):
        """Seçili listeyi döndürür: 0 = basış, 1 = bırakış eylemleri."""
        combo = getattr(self, "combo_action_list", None)
        if combo is not None and combo.currentIndex() == 1:
            return getattr(self, "current_release_actions", [])
        return getattr(self, "current_editing_actions", [])

    def refresh_editor_actions_table(self):
        actions = self._active_actions()
        self.action_table.setRowCount(len(actions))
        type_labels = {
            "KEY_TAP": T("Tuş Bas-Çek"),
            "KEY_DOWN": T("Tuşa Bas (Basılı Tut)"),
            "KEY_UP": T("Tuşu Bırak"),
            "MOUSE_CLICK": T("Fare Tıkla"),
            "MOUSE_DOWN": T("Fare Basılı Tut"),
            "MOUSE_UP": T("Fare Bırak"),
            "MOUSE_MOVE": T("Fare Hareketi"),
            "MOUSE_SCROLL": T("Fare Tekerleği"),
            "DELAY": T("Gecikme Bekle"),
            "TEXT": T("Metin Yazdır")
        }
        for i, act in enumerate(actions):
            self.action_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            a_type = act.get("type", "")
            disp_type = type_labels.get(a_type, a_type)
            self.action_table.setItem(i, 1, QTableWidgetItem(disp_type))
            if a_type == "TEXT":
                params = repr(act.get("text", ""))
            elif a_type == "DELAY":
                params = f"{act.get('delayMs', 50)} ms (±{act.get('jitterMs', 2)}ms)"
            elif a_type == "KEY_DOWN":
                params = T("Tuş: {} (Basılı Kalır)").format(act.get('key', '-'))
            elif a_type == "KEY_UP":
                params = T("Tuş: {} (Serbest Bırakılır)").format(act.get('key', '-'))
            elif a_type == "KEY_TAP":
                params = T("Tuş: {} (Basma: {}ms)").format(act.get('key', '-'), act.get('delayMs', 20))
            elif a_type == "MOUSE_DOWN":
                params = T("Fare: {} (Basılı Kalır)").format(act.get('mouseButton', 'BTN_LEFT'))
            elif a_type == "MOUSE_UP":
                params = T("Fare: {} (Serbest Bırakılır)").format(act.get('mouseButton', 'BTN_LEFT'))
            elif a_type == "MOUSE_CLICK":
                params = f"Fare: {act.get('mouseButton', 'BTN_LEFT')}"
            elif a_type == "MOUSE_MOVE":
                params = f"dx={act.get('dx', 0)}, dy={act.get('dy', 0)}"
            elif a_type == "MOUSE_SCROLL":
                params = T("Yukarı") if int(act.get("scrollDelta", 1)) > 0 else T("Aşağı")
            else:
                params = act.get("key") or "-"
            self.action_table.setItem(i, 2, QTableWidgetItem(params))

    def add_editor_action(self, act_type):
        actions = self._active_actions()
        if act_type in ("KEY_TAP", "KEY_DOWN", "KEY_UP"):
            dlg = KeyCaptureDialog(self)
            dlg.setWindowTitle(T("Makronun Basacağı Tuşu Seçin (Klavyeden Tuşa Basın)"))
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.captured_key:
                selected_key = dlg.captured_key.split("+")[-1]
            else:
                selected_key = "KEY_A"

            if act_type == "KEY_TAP":
                actions.append({"type": "KEY_TAP", "key": selected_key, "delayMs": 20})
            elif act_type == "KEY_DOWN":
                actions.append({"type": "KEY_DOWN", "key": selected_key})
            elif act_type == "KEY_UP":
                actions.append({"type": "KEY_UP", "key": selected_key})

        elif act_type in ("MOUSE_CLICK", "MOUSE_DOWN", "MOUSE_UP"):
            btn_options = ["BTN_LEFT", "BTN_RIGHT", "BTN_MIDDLE", "BTN_SIDE", "BTN_EXTRA"]
            chosen, ok = QInputDialog.getItem(self, T("Fare Tuşu Seç"), T("Makro fare tuşu:"), btn_options, 0, False)
            btn_name = chosen if ok else "BTN_LEFT"
            if act_type == "MOUSE_CLICK":
                actions.append({"type": "MOUSE_CLICK", "mouseButton": btn_name, "delayMs": 15})
            elif act_type == "MOUSE_DOWN":
                actions.append({"type": "MOUSE_DOWN", "mouseButton": btn_name})
            elif act_type == "MOUSE_UP":
                actions.append({"type": "MOUSE_UP", "mouseButton": btn_name})

        elif act_type == "DELAY":
            ms, ok = QInputDialog.getInt(self, T("Gecikme Süresi"), T("Milisaniye (ms):"), 50, 1, 60000)
            if ok:
                actions.append({"type": "DELAY", "delayMs": ms, "jitterMs": 2})

        elif act_type == "TEXT":
            text, ok = QInputDialog.getText(self, T("Metin Makrosu"), T("Yazdırılacak metni girin:"))
            if ok and text:
                actions.append({"type": "TEXT", "text": text})
            elif ok:
                actions.append({"type": "TEXT", "text": T("Selam CachyOS!")})

        elif act_type == "MOUSE_MOVE":
            dx, ok = QInputDialog.getInt(self, T("Fare Hareketi"), T("X ekseni (piksel, sağ +):"), 0, -5000, 5000)
            if ok:
                dy, ok2 = QInputDialog.getInt(self, T("Fare Hareketi"), T("Y ekseni (piksel, aşağı +):"), 0, -5000, 5000)
                if ok2:
                    actions.append({"type": "MOUSE_MOVE", "dx": dx, "dy": dy})

        elif act_type == "MOUSE_SCROLL":
            options = [T("Yukarı"), T("Aşağı")]
            chosen, ok = QInputDialog.getItem(self, T("Fare Tekerleği"), T("Kaydırma yönü:"), options, 0, False)
            if ok:
                actions.append({"type": "MOUSE_SCROLL", "scrollDelta": 1 if chosen == T("Yukarı") else -1})

        self.refresh_editor_actions_table()
        if actions:
            self.action_table.selectRow(len(actions) - 1)

    def edit_selected_editor_action(self):
        r = self.action_table.currentRow()
        actions = self._active_actions()
        if not (0 <= r < len(actions)):
            return
        act = actions[r]
        act_type = act.get("type", "")

        if act_type in ("KEY_TAP", "KEY_DOWN", "KEY_UP"):
            dlg = KeyCaptureDialog(self)
            dlg.setWindowTitle(T("Yeni Tuşa Basın"))
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.captured_key:
                act["key"] = dlg.captured_key.split("+")[-1]
            if act_type == "KEY_TAP":
                cur_del = act.get("delayMs", 20)
                ms, ok = QInputDialog.getInt(self, T("Tuş Basma Süresi"), T("Tuş basılı kalma süresi (ms):"), cur_del, 1, 10000)
                if ok:
                    act["delayMs"] = ms

        elif act_type in ("MOUSE_CLICK", "MOUSE_DOWN", "MOUSE_UP"):
            btn_options = ["BTN_LEFT", "BTN_RIGHT", "BTN_MIDDLE", "BTN_SIDE", "BTN_EXTRA"]
            cur_btn = act.get("mouseButton", "BTN_LEFT")
            cur_idx = btn_options.index(cur_btn) if cur_btn in btn_options else 0
            chosen, ok = QInputDialog.getItem(self, T("Fare Tuşu Değiştir"), T("Fare tuşu:"), btn_options, cur_idx, False)
            if ok:
                act["mouseButton"] = chosen

        elif act_type == "DELAY":
            cur_del = act.get("delayMs", 50)
            ms, ok = QInputDialog.getInt(self, T("Gecikme Süresi"), T("Milisaniye (ms):"), cur_del, 1, 60000)
            if ok:
                act["delayMs"] = ms

        elif act_type == "TEXT":
            cur_txt = act.get("text", "")
            text, ok = QInputDialog.getText(self, T("Metin Düzenle"), T("Yazdırılacak metin:"), text=cur_txt)
            if ok:
                act["text"] = text

        elif act_type == "MOUSE_MOVE":
            dx, ok = QInputDialog.getInt(self, T("Fare Hareketi"), T("X ekseni (piksel):"), int(act.get("dx", 0)), -5000, 5000)
            if ok:
                dy, ok2 = QInputDialog.getInt(self, T("Fare Hareketi"), T("Y ekseni (piksel):"), int(act.get("dy", 0)), -5000, 5000)
                if ok2:
                    act["dx"], act["dy"] = dx, dy

        elif act_type == "MOUSE_SCROLL":
            options = [T("Yukarı"), T("Aşağı")]
            cur_idx = 0 if int(act.get("scrollDelta", 1)) > 0 else 1
            chosen, ok = QInputDialog.getItem(self, T("Fare Tekerleği"), T("Kaydırma yönü:"), options, cur_idx, False)
            if ok:
                act["scrollDelta"] = 1 if chosen == T("Yukarı") else -1

        self.refresh_editor_actions_table()
        self.action_table.selectRow(r)

    def clear_all_editor_actions(self):
        actions = self._active_actions()
        if actions:
            reply = QMessageBox.question(
                self,
                T("Tüm Eylemleri Sil"),
                T("Bu makrodaki tüm eylemleri silmek istediğinizden emin misiniz?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                actions.clear()
                self.refresh_editor_actions_table()

    def delete_editor_action(self):
        r = self.action_table.currentRow()
        actions = self._active_actions()
        if 0 <= r < len(actions):
            del actions[r]
            self.refresh_editor_actions_table()
        elif actions:
            del actions[-1]
            self.refresh_editor_actions_table()

    def save_macro_from_editor(self):
        macros = self.profile_data.get("macros", [])
        if 0 <= self.selected_macro_idx < len(macros):
            m = macros[self.selected_macro_idx]
            m["name"] = self.edit_name.text().strip() or "İsimsiz Makro"
            new_key = self.combo_trigger_key.currentText().strip()
            m["triggerKey"] = new_key
            mode_reverse = ["ONCE", "WHILE_HELD", "TOGGLE_LOOP", "REPEAT_COUNT", "DOUBLE_TAP", "HOLD_LONG_PRESS", "PRESS_AND_RELEASE"]
            c_idx = self.combo_mode.currentIndex()
            m["triggerMode"] = mode_reverse[c_idx] if 0 <= c_idx < len(mode_reverse) else "ONCE"
            m["repeatCount"] = self.spin_repeat.value()
            m["doubleTapTimeoutMs"] = self.spin_double_tap.value()
            m["holdDurationMs"] = self.spin_hold.value()
            m["actions"] = getattr(self, "current_editing_actions", [])
            m["releaseActions"] = getattr(self, "current_release_actions", [])
            self.save_profile_to_disk(restart_daemon=True)
            self.refresh_macro_table()
            self._editor_snapshot = None

            self.btn_save_macro.setText(T("Kaydedildi..."))
            self.btn_save_macro.setEnabled(False)
            QTimer.singleShot(500, lambda: (
                self.btn_save_macro.setText(T("Kaydet")),
                self.btn_save_macro.setEnabled(True),
                self.tabs.setCurrentIndex(0)
            ))

    def _editor_macro_copy(self):
        """Düzenleyicideki güncel (kaydedilmemiş) alanlarla makronun kopyasını üretir."""
        macros = self.profile_data.get("macros", [])
        if not (0 <= self.selected_macro_idx < len(macros)):
            return None
        m = copy.deepcopy(macros[self.selected_macro_idx])
        m["name"] = self.edit_name.text().strip() or m.get("name", "Makro")
        m["triggerKey"] = self.combo_trigger_key.currentText().strip()
        c_idx = self.combo_mode.currentIndex()
        m["triggerMode"] = self._MODE_REVERSE[c_idx] if 0 <= c_idx < len(self._MODE_REVERSE) else "ONCE"
        m["repeatCount"] = self.spin_repeat.value()
        m["doubleTapTimeoutMs"] = self.spin_double_tap.value()
        m["holdDurationMs"] = self.spin_hold.value()
        m["actions"] = copy.deepcopy(getattr(self, "current_editing_actions", []))
        m["releaseActions"] = copy.deepcopy(getattr(self, "current_release_actions", []))
        m["enabled"] = True
        return m

    def test_current_macro(self):
        """Geçici bir profille motoru bir kez çalıştırıp yalnızca bu makroyu dener."""
        if not common.DAEMON_BIN or not common.DAEMON_BIN.exists():
            QMessageBox.warning(self, T("Motor Bulunamadı"),
                                T("Test için motor ikilisi bulunamadı."))
            return
        macro = self._editor_macro_copy()
        if not macro:
            return
        if not macro.get("actions"):
            QMessageBox.information(self, T("Makro Test Ediliyor..."),
                                    T("Bu makroda eylem yok."))
            return

        temp_path = Path(f"/tmp/cachymacro-test-{os.getpid()}.json")
        payload = {
            "schemaVersion": 2,
            "activeProfileId": "profile-test",
            "profiles": [{
                "id": "profile-test",
                "name": "Test",
                "panicKey": common.PANIC_KEY,
                "virtualDeviceName": "MacroStat Test Engine",
                "macros": [macro],
            }],
        }
        try:
            temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
            proc = QProcess(self)
            proc.start(str(common.DAEMON_BIN.resolve()),
                       ["--test-macro", macro.get("id", ""), str(temp_path)])
            if not proc.waitForStarted(3000):
                raise RuntimeError(proc.errorString())
            proc.waitForFinished(20000)
            stderr = bytes(proc.readAllStandardError()).decode("utf-8", "ignore").strip()
            if proc.exitStatus() != QProcess.ExitStatus.NormalExit or proc.exitCode() != 0:
                if proc.state() != QProcess.ProcessState.NotRunning:
                    proc.kill()
                detail = stderr[-800:] if stderr else proc.errorString()
                QMessageBox.warning(self, T("Makro testi başarısız."), detail)
            else:
                self.show_autosave_banner(T("▶ Makro başarıyla test edildi."))
        except Exception as e:
            QMessageBox.warning(self, T("Makro testi başarısız."), str(e))
        finally:
            try:
                temp_path.unlink()
            except OSError:
                pass

    # SEKME 3: Canlı Kaydedici
