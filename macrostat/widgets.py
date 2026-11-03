# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Yeniden kullanılabilir Qt bileşenleri: anahtar ve tuş yakalama."""

from . import theme
from .common import *  # noqa: F401,F403

class SlidingSwitch(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, parent=None, checked=False):
        super().__init__(parent)
        self.setFixedSize(48, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._checked = checked
        self._position = 26.0 if checked else 2.0
        self.anim = QPropertyAnimation(self, b"position", self)
        self.anim.setDuration(160)

    @pyqtProperty(float)
    def position(self):
        return self._position

    @position.setter
    def position(self, pos):
        self._position = pos
        self.update()

    def isChecked(self):
        return self._checked

    def setChecked(self, checked):
        if self._checked != checked:
            self._checked = checked
            self.anim.stop()
            self.anim.setStartValue(self._position)
            self.anim.setEndValue(26.0 if checked else 2.0)
            self.anim.start()
            self.toggled.emit(self._checked)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_color = QColor("#10b981") if self._checked else QColor("#334155")
        border_color = QColor("#059669") if self._checked else QColor("#475569")

        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 12, 12)

        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(self._position, 2.0, 20.0, 20.0))

class KeyCaptureDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(T("🎯 Tetikleyici Tuş veya İkili Kombinasyon Ayarla"))
        self.setFixedSize(480, 280)
        self.captured_key = None
        self.held_keys = []

        # Ana uygulama referansını bul
        self.app_ref = parent if (parent and hasattr(parent, "is_daemon_running")) else None
        if not self.app_ref and parent and hasattr(parent, "window") and hasattr(parent.window(), "is_daemon_running"):
            self.app_ref = parent.window()

        self.was_daemon_running = False
        # Tetikleyici tuş ayarlanırken diğer makroların araya girmesini engellemek için motoru durdur
        if self.app_ref and hasattr(self.app_ref, "is_daemon_running"):
            self.was_daemon_running = self.app_ref.is_daemon_running()
            if self.was_daemon_running:
                self.app_ref.stop_daemon()
                if hasattr(self.app_ref, "show_autosave_banner"):
                    self.app_ref.show_autosave_banner(T("🛑 Tuş ayarlanırken makrolar durduruldu."))

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Makroların Durdurulduğunu Gösteren Güvenlik Rozeti
        iso_banner = QFrame()
        iso_banner.setObjectName("dangerBanner")
        iso_layout = QHBoxLayout(iso_banner)
        iso_layout.setContentsMargins(4, 2, 4, 2)
        lbl_iso = QLabel(T("🛑 Makrolar Durduruldu: Tuş ayarlarken diğer makrolar çalıştırılmaz."))
        lbl_iso.setObjectName("dangerText")
        iso_layout.addWidget(lbl_iso)
        layout.addWidget(iso_banner)

        info = QLabel(T("Klavyenizden bir tuşa basın veya LeftShift+LeftCtrl gibi iki tuşa aynı anda basın:"))
        info.setWordWrap(True)
        info.setObjectName("mutedText")
        layout.addWidget(info)

        self.box = QFrame()
        self.box.setObjectName("keyCaptureBox")
        box_layout = QVBoxLayout(self.box)
        box_layout.setContentsMargins(14, 14, 14, 14)

        self.status_label = QLabel(T("⏳ Tuşa veya ikili kombinasyona basın..."))
        self.status_label.setObjectName("captureStatus")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box_layout.addWidget(self.status_label)
        layout.addWidget(self.box)

        btn_row = QHBoxLayout()
        self.btn_confirm = QPushButton(T("✔ Bu Tuşu / Kombinasyonu Kullan"))
        theme.set_variant(self.btn_confirm, "success")
        self.btn_confirm.clicked.connect(self.accept)
        self.btn_confirm.setEnabled(False)
        btn_row.addWidget(self.btn_confirm)

        cancel_btn = QPushButton(T("İptal"))
        theme.set_variant(cancel_btn, "muted")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()

    def done(self, r):
        # Pencere kapandığında (Kabul, İptal veya X ile kapatma) motor önceden çalışıyorsa yeniden başlat
        if (self.was_daemon_running and self.app_ref
                and hasattr(self.app_ref, "restart_daemon")
                and not getattr(self.app_ref, "is_manually_stopped", False)):
            self.app_ref.restart_daemon(show_message=False)
            if hasattr(self.app_ref, "show_autosave_banner"):
                self.app_ref.show_autosave_banner(T("▶ Makro motoru tekrar aktif edildi."))
        super().done(r)

    def keyPressEvent(self, event):
        qt_key = event.key()
        if qt_key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.captured_key:
                self.accept()
                return

        if qt_key == Qt.Key.Key_Escape:
            if not self.held_keys:
                self.captured_key = "KEY_ESC"
                self.status_label.setText(T("✔ Algılandı: {}").format("KEY_ESC"))
                theme.set_state(self.status_label, "ok")
                self.btn_confirm.setText(T("✔ Bu Tuşu Kullan ({})").format("KEY_ESC"))
                self.btn_confirm.setEnabled(True)
                return

        key_name = self.map_qt_key_to_evdev(qt_key, event.text())
        if key_name and key_name not in self.held_keys:
            self.held_keys.append(key_name)
            if len(self.held_keys) > 2:
                self.held_keys = self.held_keys[-2:]

        if self.held_keys:
            combo_str = "+".join(self.held_keys)
            self.captured_key = combo_str

            if len(self.held_keys) >= 2:
                self.status_label.setText(T("✔ İkili Kombinasyon: {}").format(combo_str))
                theme.set_state(self.status_label, "ok")
            else:
                self.status_label.setText(T("✔ Algılandı: {}").format(combo_str))
                theme.set_state(self.status_label, "info")

            self.btn_confirm.setText(T("✔ Bu Tuşu Kullan ({})").format(combo_str))
            self.btn_confirm.setEnabled(True)

    def keyReleaseEvent(self, event):
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        btn = event.button()
        key_name = None
        if btn == Qt.MouseButton.LeftButton: key_name = "BTN_LEFT"
        elif btn == Qt.MouseButton.RightButton: key_name = "BTN_RIGHT"
        elif btn == Qt.MouseButton.MiddleButton: key_name = "BTN_MIDDLE"
        elif btn == Qt.MouseButton.BackButton or btn == Qt.MouseButton.XButton1: key_name = "BTN_SIDE"
        elif btn == Qt.MouseButton.ForwardButton or btn == Qt.MouseButton.XButton2: key_name = "BTN_EXTRA"

        if key_name:
            if key_name not in self.held_keys:
                self.held_keys.append(key_name)
                if len(self.held_keys) > 2:
                    self.held_keys = self.held_keys[-2:]
            combo_str = "+".join(self.held_keys)
            self.captured_key = combo_str
            self.status_label.setText(T("✔ Algılandı: {}").format(combo_str))
            theme.set_state(self.status_label, "ok")
            self.btn_confirm.setText(T("✔ Bu Tuşu Kullan ({})").format(combo_str))
            self.btn_confirm.setEnabled(True)

    def map_qt_key_to_evdev(self, qt_key, text):
        if Qt.Key.Key_F1 <= qt_key <= Qt.Key.Key_F12:
            return f"KEY_F{qt_key - Qt.Key.Key_F1 + 1}"
        if Qt.Key.Key_A <= qt_key <= Qt.Key.Key_Z:
            return f"KEY_{chr(qt_key)}"
        if Qt.Key.Key_0 <= qt_key <= Qt.Key.Key_9:
            return f"KEY_{chr(qt_key)}"
        mapping = {
            Qt.Key.Key_Space: "KEY_SPACE",
            Qt.Key.Key_Return: "KEY_ENTER",
            Qt.Key.Key_Enter: "KEY_ENTER",
            Qt.Key.Key_Escape: "KEY_ESC",
            Qt.Key.Key_Backspace: "KEY_BACKSPACE",
            Qt.Key.Key_Tab: "KEY_TAB",
            Qt.Key.Key_Shift: "KEY_LEFTSHIFT",
            Qt.Key.Key_Control: "KEY_LEFTCTRL",
            Qt.Key.Key_Alt: "KEY_LEFTALT",
            Qt.Key.Key_Meta: "KEY_LEFTMETA",
            Qt.Key.Key_CapsLock: "KEY_CAPSLOCK",
            Qt.Key.Key_Pause: "KEY_PAUSE",
            Qt.Key.Key_Delete: "KEY_DELETE",
            Qt.Key.Key_Insert: "KEY_INSERT",
            Qt.Key.Key_Home: "KEY_HOME",
            Qt.Key.Key_End: "KEY_END",
            Qt.Key.Key_PageUp: "KEY_PAGEUP",
            Qt.Key.Key_PageDown: "KEY_PAGEDOWN",
            Qt.Key.Key_Up: "KEY_UP",
            Qt.Key.Key_Down: "KEY_DOWN",
            Qt.Key.Key_Left: "KEY_LEFT",
            Qt.Key.Key_Right: "KEY_RIGHT",
            Qt.Key.Key_Print: "KEY_SYSRQ",
        }
        return mapping.get(qt_key, f"KEY_{text.upper()}" if text and text.isalnum() else None)

