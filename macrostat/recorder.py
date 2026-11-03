# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Canlı kaydedici ve klavye/fare olayları."""

from . import common, theme
from .common import *  # noqa: F401,F403
from .widgets import SlidingSwitch, KeyCaptureDialog  # noqa: F401

class RecorderMixin:
    """Canlı kaydedici ve klavye/fare olayları."""

    def setup_recorder_tab(self):
        layout = QVBoxLayout(self.tab_recorder)
        layout.addWidget(QLabel(T(
            "Milisaniye hassasiyetinde klavye, fare tuşları ve tekerlek olaylarını kaydeder."
        )))

        if (os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
                or os.environ.get("WAYLAND_DISPLAY")):
            wayland_banner = QFrame()
            wayland_banner.setObjectName("dangerBanner")
            wb_layout = QHBoxLayout(wayland_banner)
            wb_layout.setContentsMargins(8, 4, 8, 4)
            lbl_wb = QLabel(T(
                "Wayland oturumu: kayıt yalnızca bu pencere odaktayken çalışır; "
                "sistem genelinde tuş dinleme kısıtlıdır."
            ))
            lbl_wb.setObjectName("bannerText")
            lbl_wb.setWordWrap(True)
            wb_layout.addWidget(lbl_wb)
            layout.addWidget(wayland_banner)

        self.rec_table = QTableWidget()
        self.rec_table.setColumnCount(4)
        self.rec_table.setHorizontalHeaderLabels([T("Sıra"), T("Olay"), T("Tuş / Buton"), T("Gecikme (ms)")])
        self.rec_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.rec_table)

        b_box = QHBoxLayout()
        self.btn_start_rec = QPushButton(T("⏺️ Kaydı Başlat"))
        theme.set_variant(self.btn_start_rec, "primary")
        self.btn_start_rec.clicked.connect(self.toggle_recording)
        b_box.addWidget(self.btn_start_rec)

        btn_clear = QPushButton(T("🗑️ Temizle"))
        btn_clear.clicked.connect(self.clear_recorded)
        b_box.addWidget(btn_clear)

        btn_conv = QPushButton(T("💾 Kaydı Yeni Makro Olarak Ekle"))
        btn_conv.clicked.connect(self.convert_recording_to_macro)
        b_box.addWidget(btn_conv)

        layout.addLayout(b_box)

    def toggle_recording(self):
        self.recording_active = not self.recording_active
        if self.recording_active:
            # Kayıt esnasında makroların devreye girmemesi için motoru durdur
            if self.is_daemon_running():
                self.was_recording_daemon_running = True
                self.stop_daemon()
            else:
                self.was_recording_daemon_running = False

            self.btn_start_rec.setText(T("⏹️ Kaydı Durdur"))
            theme.set_variant(self.btn_start_rec, "danger")
            self.last_key_time = time.time()
            self.grabKeyboard()
            self.show_autosave_banner(T("🛑 Canlı kayıt modu: Diğer tüm makrolar durduruldu."))
        else:
            self.btn_start_rec.setText(T("⏺️ Kaydı Başlat"))
            theme.set_variant(self.btn_start_rec, "primary")
            self.releaseKeyboard()
            if getattr(self, "was_recording_daemon_running", False):
                self.was_recording_daemon_running = False
                self.restart_daemon(show_message=False)
                self.show_autosave_banner(T("▶ Makro motoru tekrar aktif edildi."))

    _REC_MOUSE_MAP = {
        Qt.MouseButton.LeftButton: "BTN_LEFT",
        Qt.MouseButton.RightButton: "BTN_RIGHT",
        Qt.MouseButton.MiddleButton: "BTN_MIDDLE",
        Qt.MouseButton.BackButton: "BTN_SIDE",
        Qt.MouseButton.ForwardButton: "BTN_EXTRA",
    }

    def _recording_add_delay(self):
        now = time.time()
        delta = int((now - self.last_key_time) * 1000)
        self.last_key_time = now
        if delta > 10 and self.recorded_events:
            self.recorded_events.append({"type": "DELAY", "delayMs": delta, "jitterMs": 2})

    def map_qt_key_to_evdev(self, qt_key, text):
        return KeyCaptureDialog.map_qt_key_to_evdev(self, qt_key, text)

    def _record_mouse_button(self, button, is_down):
        name = self._REC_MOUSE_MAP.get(button)
        if not name:
            return False
        self._recording_add_delay()
        self.recorded_events.append({
            "type": "MOUSE_DOWN" if is_down else "MOUSE_UP",
            "mouseButton": name,
        })
        self.refresh_rec_table()
        return True

    def mousePressEvent(self, event):
        if self.recording_active and self._record_mouse_button(event.button(), True):
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.recording_active and self._record_mouse_button(event.button(), False):
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if self.recording_active:
            delta = event.angleDelta().y()
            if delta != 0:
                self._recording_add_delay()
                self.recorded_events.append({
                    "type": "MOUSE_SCROLL",
                    "scrollDelta": 1 if delta > 0 else -1,
                })
                self.refresh_rec_table()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event):
        # STOP kontrolü (motorun kabul ettiği KEY_* adlarıyla karşılaştırılır)
        pressed_key = self.map_qt_key_to_evdev(event.key(), event.text())
        if pressed_key == common.PANIC_KEY or event.key() == Qt.Key.Key_Pause:
            self.trigger_panic()
            return

        if event.key() == Qt.Key.Key_Escape and not self.recording_active:
            self.tabs.setCurrentIndex(0)
            return

        if self.recording_active:
            key_code = self.map_qt_key_to_evdev(event.key(), event.text())
            if not key_code:
                key_code = f"KEY_CODE_{int(event.key())}"
            self._recording_add_delay()
            self.recorded_events.append({"type": "KEY_DOWN", "key": key_code})
            self.refresh_rec_table()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if self.recording_active:
            key_code = self.map_qt_key_to_evdev(event.key(), event.text())
            if not key_code:
                key_code = f"KEY_CODE_{int(event.key())}"
            self._recording_add_delay()
            self.recorded_events.append({"type": "KEY_UP", "key": key_code})
            self.refresh_rec_table()
            return
        super().keyReleaseEvent(event)

    def refresh_rec_table(self):
        self.rec_table.setRowCount(len(self.recorded_events))
        for i, ev in enumerate(self.recorded_events):
            self.rec_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.rec_table.setItem(i, 1, QTableWidgetItem(ev.get("type", "")))
            self.rec_table.setItem(i, 2, QTableWidgetItem(ev.get("key") or ev.get("mouseButton") or "-"))
            self.rec_table.setItem(i, 3, QTableWidgetItem(str(ev.get("delayMs", "-"))))

    def clear_recorded(self):
        self.recorded_events.clear()
        self.rec_table.setRowCount(0)

    def convert_recording_to_macro(self):
        if not self.recorded_events: return
        new_m = {
            "id": f"macro-{int(time.time() * 1000)}",
            "name": T("Kayıtlı Makro ({} adım)").format(len(self.recorded_events)),
            "description": "Canlı kaydedici ile oluşturuldu",
            "enabled": True,
            "triggerKey": "KEY_LEFTSHIFT+KEY_LEFTCTRL",
            "triggerMode": "ONCE",
            "repeatCount": 1,
            "actions": list(self.recorded_events)
        }
        self.profile_data.setdefault("macros", []).append(new_m)
        self.save_profile_to_disk(restart_daemon=True)
        self.refresh_macro_table()
        self.tabs.setCurrentWidget(self.tab_macros)

    # SEKME 4: Sistem
