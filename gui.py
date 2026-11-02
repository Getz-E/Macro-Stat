#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MacroStat - Linux Native GUI (PyQt6)
Wayland & X11 Destekli Makro ve Donanım Otomasyon Stüdyosu
"""

import sys
import os
import json
import time
import subprocess
import shutil
import atexit
import signal
from pathlib import Path

DAEMON_PROC = None

def cleanup_daemon():
    global DAEMON_PROC
    if DAEMON_PROC is not None:
        try:
            if hasattr(os, "killpg"):
                os.killpg(os.getpgid(DAEMON_PROC.pid), signal.SIGKILL)
            else:
                DAEMON_PROC.kill()
        except Exception:
            try:
                DAEMON_PROC.kill()
            except Exception:
                pass
        DAEMON_PROC = None

    try:
        subprocess.run(["pkill", "-9", "-f", "cachymacro-daemon"], stderr=subprocess.DEVNULL)
    except Exception:
        pass
    try:
        subprocess.run(["pkill", "-9", "-f", "cachymacro"], stderr=subprocess.DEVNULL)
    except Exception:
        pass

atexit.register(cleanup_daemon)
signal.signal(signal.SIGINT, lambda sig, frame: (cleanup_daemon(), sys.exit(0)))
signal.signal(signal.SIGTERM, lambda sig, frame: (cleanup_daemon(), sys.exit(0)))
if hasattr(signal, "SIGHUP"):
    signal.signal(signal.SIGHUP, lambda sig, frame: (cleanup_daemon(), sys.exit(0)))

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QTableWidget, QTableWidgetItem, QPushButton, QLabel, QLineEdit,
        QComboBox, QSpinBox, QDoubleSpinBox, QHeaderView, QMessageBox,
        QTabWidget, QGroupBox, QFormLayout, QTextEdit, QDialog, QAbstractItemView,
        QFrame, QInputDialog
    )
    from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QRectF, QPropertyAnimation, pyqtProperty
    from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QKeySequence
except ImportError:
    print("[HATA] PyQt6 kütüphanesi eksik!")
    print("Kurulum için: sudo pacman -S python-pyqt6")
    sys.exit(1)

# Sabit yollar
SCRIPT_DIR = Path(__file__).resolve().parent
LOG_FILE = Path("/tmp/cachymacro.log")
PANIC_KEY = "KEY_PAUSE"

def locate_paths():
    candidates_bin = [
        SCRIPT_DIR / "cachymacro-daemon",
        SCRIPT_DIR / "target" / "release" / "cachymacro-daemon",
        SCRIPT_DIR / "cachymacro" / "target" / "release" / "cachymacro-daemon",
        SCRIPT_DIR / "cachymacro" / "cachymacro-daemon",
        SCRIPT_DIR.parent / "target" / "release" / "cachymacro-daemon",
        SCRIPT_DIR.parent / "cachymacro" / "target" / "release" / "cachymacro-daemon",
        SCRIPT_DIR.parent / "cachymacro-daemon",
        SCRIPT_DIR / "target" / "debug" / "cachymacro-daemon",
        SCRIPT_DIR / "cachymacro" / "target" / "debug" / "cachymacro-daemon",
        SCRIPT_DIR.parent / "target" / "debug" / "cachymacro-daemon",
        Path.home() / ".cargo" / "bin" / "cachymacro-daemon",
        Path("/usr/local/bin/cachymacro-daemon"),
        Path("/usr/bin/cachymacro-daemon"),
    ]
    which_bin = shutil.which("cachymacro-daemon")
    if which_bin:
        candidates_bin.insert(0, Path(which_bin))

    daemon_bin = None
    for p in candidates_bin:
        if p.exists() and p.is_file():
            try:
                os.chmod(p, 0o755)
            except Exception:
                pass
            daemon_bin = p
            break

    # Bulunamazsa SCRIPT_DIR ve üst dizinde özyinelemeli ara
    if not daemon_bin:
        for root_p in (SCRIPT_DIR, SCRIPT_DIR.parent):
            try:
                for found in root_p.glob("**/cachymacro-daemon"):
                    if found.is_file() and not found.is_symlink() and "src" not in found.parts:
                        try:
                            os.chmod(found, 0o755)
                        except Exception:
                            pass
                        daemon_bin = found
                        break
            except Exception:
                pass
            if daemon_bin:
                break

    user_config_prof = Path.home() / ".config" / "cachymacro" / "profile.json"
    candidates_prof = [
        user_config_prof,
        SCRIPT_DIR / "profile.json",
        SCRIPT_DIR / "cachymacro" / "profile.json",
        SCRIPT_DIR.parent / "profile.json",
        SCRIPT_DIR.parent / "cachymacro" / "profile.json"
    ]
    profile_path = user_config_prof
    for p in candidates_prof:
        if p.exists() and p.is_file():
            profile_path = p
            break

    return daemon_bin, profile_path

DAEMON_BIN, PROFILE_PATH = locate_paths()

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
        self.setWindowTitle("🎯 Tetikleyici Tuş veya İkili Kombinasyon Ayarla")
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
                    self.app_ref.show_autosave_banner("🛑 Tuş ayarlanırken makrolar durduruldu.")

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Makroların Durdurulduğunu Gösteren Güvenlik Rozeti
        iso_banner = QFrame()
        iso_banner.setStyleSheet("background-color: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; border-radius: 8px; padding: 6px 12px;")
        iso_layout = QHBoxLayout(iso_banner)
        iso_layout.setContentsMargins(4, 2, 4, 2)
        lbl_iso = QLabel("🛑 Makrolar Durduruldu: Tuş ayarlarken diğer makrolar çalıştırılmaz.")
        lbl_iso.setStyleSheet("color: #f87171; font-size: 11px; font-weight: bold;")
        iso_layout.addWidget(lbl_iso)
        layout.addWidget(iso_banner)

        info = QLabel("Klavyenizden bir tuşa basın veya LeftShift+LeftCtrl gibi iki tuşa aynı anda basın:")
        info.setWordWrap(True)
        info.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        layout.addWidget(info)

        self.box = QFrame()
        self.box.setStyleSheet("background-color: #090d16; border: 2px dashed #0284c7; border-radius: 10px; padding: 14px;")
        box_layout = QVBoxLayout(self.box)

        self.status_label = QLabel("⏳ Tuşa veya ikili kombinasyona basın...")
        self.status_label.setStyleSheet("color: #38bdf8; font-size: 15px; font-weight: bold;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box_layout.addWidget(self.status_label)
        layout.addWidget(self.box)

        btn_row = QHBoxLayout()
        self.btn_confirm = QPushButton("✔ Bu Tuşu / Kombinasyonu Kullan")
        self.btn_confirm.setStyleSheet("background-color: #10b981; color: #022c22; font-weight: bold; font-size: 13px; padding: 8px 16px; border-radius: 6px;")
        self.btn_confirm.clicked.connect(self.accept)
        self.btn_confirm.setEnabled(False)
        btn_row.addWidget(self.btn_confirm)

        cancel_btn = QPushButton("İptal")
        cancel_btn.setStyleSheet("background-color: #334155; color: #f1f5f9; padding: 8px 14px; border-radius: 6px;")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()

    def done(self, r):
        # Pencere kapandığında (Kabul, İptal veya X ile kapatma) motor önceden çalışıyorsa yeniden başlat
        if self.was_daemon_running and self.app_ref and hasattr(self.app_ref, "restart_daemon"):
            self.app_ref.restart_daemon(show_message=False)
            if hasattr(self.app_ref, "show_autosave_banner"):
                self.app_ref.show_autosave_banner("▶ Makro motoru tekrar aktif edildi.")
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
                self.status_label.setText("✔ Algılandı: KEY_ESC")
                self.status_label.setStyleSheet("color: #10b981; font-size: 15px; font-weight: bold;")
                self.btn_confirm.setText("✔ Bu Tuşu Kullan (KEY_ESC)")
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
                self.status_label.setText(f"✔ İkili Kombinasyon: {combo_str}")
                self.status_label.setStyleSheet("color: #10b981; font-size: 16px; font-weight: bold;")
            else:
                self.status_label.setText(f"✔ Algılandı: {combo_str}")
                self.status_label.setStyleSheet("color: #38bdf8; font-size: 16px; font-weight: bold;")

            self.btn_confirm.setText(f"✔ Bu Tuşu Kullan ({combo_str})")
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
            self.status_label.setText(f"✔ Algılandı: {combo_str}")
            self.status_label.setStyleSheet("color: #10b981; font-size: 16px; font-weight: bold;")
            self.btn_confirm.setText(f"✔ Bu Tuşu Kullan ({combo_str})")
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
        }
        return mapping.get(qt_key, f"KEY_{text.upper()}" if text and text.isalnum() else None)

class MacroStatApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MacroStat")
        self.resize(1000, 680)
        self.setMinimumSize(850, 550)

        self.profile_data = self.load_profile()
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
        if PROFILE_PATH.exists():
            try:
                with open(PROFILE_PATH, "r", encoding="utf-8") as f:
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
        default_p = {
            "id": "profile-cachy-default",
            "name": "MacroStat Varsayılan Profil",
            "panicKey": "KEY_PAUSE",
            "virtualDeviceName": "MacroStat Virtual Engine",
            "defaultJitterMs": 2,
            "macros": [{"id":"macro-turbo-shift-ctrl","name":"Shift+Ctrl Çift Tuş Tetikleyici","description":"LeftShift + LeftCtrl kombinasyonuna basıldığında hızlı X tuşu tetikler.","enabled":true,"triggerKey":"KEY_LEFTSHIFT+KEY_LEFTCTRL","triggerMode":"ONCE","repeatCount":1,"tags":["Kombinasyon","Oyun"],"actions":[{"id":"a1","type":"KEY_DOWN","key":"KEY_X","description":"X tuşuna basılı tut"},{"id":"a2","type":"DELAY","delayMs":40,"jitterMs":2,"description":"40ms bekle"},{"id":"a3","type":"KEY_UP","key":"KEY_X","description":"X tuşunu bırak"}],"createdAt":1793259933773,"updatedAt":1793259933773},{"id":"macro-burst-clicker","name":"Mouse 5 Hızlı Tıklama","description":"Fare yan tuşuna (M5) basıldığında sol tık bas-çek yapar.","enabled":true,"triggerKey":"BTN_EXTRA","triggerMode":"ONCE","repeatCount":1,"tags":["Fare","FPS"],"actions":[{"id":"m1","type":"MOUSE_DOWN","mouseButton":"LEFT","description":"Sol fare tuşuna bas"},{"id":"m2","type":"DELAY","delayMs":25,"jitterMs":2,"description":"25ms bekle"},{"id":"m3","type":"MOUSE_UP","mouseButton":"LEFT","description":"Sol fareyi bırak"}],"createdAt":1793256333773,"updatedAt":1793256333773},{"id":"macro-fast-macro","name":"F8 Seri Metin & Enter","description":"F8 tuşuyla hızlı terminal komutunu enjekte eder.","enabled":true,"triggerKey":"KEY_F8","triggerMode":"ONCE","repeatCount":1,"tags":["Otomasyon","Terminal"],"actions":[{"id":"t1","type":"TEXT","text":"uname -r","description":"Metin yazdır"},{"id":"t2","type":"DELAY","delayMs":30,"jitterMs":1,"description":"30ms bekle"},{"id":"t3","type":"KEY_TAP","key":"KEY_ENTER","description":"Enter tuşuna bas"}],"createdAt":1793252733773,"updatedAt":1793252733773},{"id":"macro-yr3d5pt","name":"Yeni Makro","description":"Kullanıcı tanımlı makro","enabled":true,"triggerKey":"KEY_A","triggerMode":"ONCE","repeatCount":1,"actions":[{"id":"act-1","type":"KEY_TAP","key":"KEY_X","delayMs":20},{"id":"act-2","type":"DELAY","delayMs":40,"jitterMs":2},{"id":"act-fe26ncx","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-8i710su","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-93gxpmh","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-ar49xhc","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-6hou3hh","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-arhp3t0","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-dvatjb8","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-y60omil","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-qircjy0","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-tdvknfk","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-up7xewj","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-xrzdr6n","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-rn63mnz","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-8kjt2c4","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-5r2yzwp","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-e8ajn17","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-u6srr2t","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-37r7neq","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-1mka5fl","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-j6j9ypu","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-6fk2ujv","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-q7w6e3j","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"},{"id":"act-71ltn10","type":"TEXT","delayMs":20,"jitterMs":2,"text":"Selam CachyOS!"}],"tags":["Özel"],"createdAt":1793269706930,"updatedAt":1793269706930}]
        }
        self.all_profiles = [default_p]
        self.active_profile_id = default_p["id"]
        return default_p

    def save_profile_to_disk(self, restart_daemon=True):
        try:
            self.profile_data["panicKey"] = PANIC_KEY
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
                "activeProfileId": self.profile_data.get("id", ""),
                "profiles": self.all_profiles,
                "id": self.profile_data.get("id", ""),
                "name": self.profile_data.get("name", ""),
                "panicKey": PANIC_KEY,
                "virtualDeviceName": self.profile_data.get("virtualDeviceName", ""),
                "defaultJitterMs": self.profile_data.get("defaultJitterMs", 2),
                "macros": self.profile_data.get("macros", [])
            }

            global PROFILE_PATH
            target_save_path = PROFILE_PATH
            try:
                target_save_path.parent.mkdir(parents=True, exist_ok=True)
                with open(target_save_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
            except OSError:
                target_save_path = Path.home() / ".config" / "cachymacro" / "profile.json"
                target_save_path.parent.mkdir(parents=True, exist_ok=True)
                with open(target_save_path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                PROFILE_PATH = target_save_path

            # cachymacro klasörü varsa onun içindeki profile.json'u da senkronize tut
            alt_prof = SCRIPT_DIR / "cachymacro" / "profile.json" if SCRIPT_DIR.name != "cachymacro" else SCRIPT_DIR.parent / "profile.json"
            if alt_prof.parent.exists():
                try:
                    with open(alt_prof, "w", encoding="utf-8") as f:
                        json.dump(payload, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

            if restart_daemon:
                self.restart_daemon(show_message=False)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Profil kaydedilemedi: {e}")
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
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: white;")
        header_layout.addWidget(title_label)

        lbl_prof = QLabel("Profil:")
        lbl_prof.setStyleSheet("color: #94a3b8; font-size: 12px; font-weight: bold; margin-left: 10px;")
        header_layout.addWidget(lbl_prof)

        self.combo_profiles = QComboBox()
        self.combo_profiles.setStyleSheet("QComboBox { background-color: #1e293b; color: #38bdf8; font-weight: bold; border: 1px solid #0284c7; border-radius: 6px; padding: 4px 8px; min-width: 150px; font-size: 11px; }")
        header_layout.addWidget(self.combo_profiles)

        btn_new_prof = QPushButton("+ Profil")
        btn_new_prof.setStyleSheet("QPushButton { background-color: #0284c7; color: white; font-weight: bold; border-radius: 5px; padding: 4px 8px; font-size: 11px; } QPushButton:hover { background-color: #38bdf8; color: #0f172a; }")
        btn_new_prof.clicked.connect(self.create_new_profile_dialog)
        header_layout.addWidget(btn_new_prof)

        self.populate_profile_combo()
        self.combo_profiles.currentIndexChanged.connect(self.on_profile_selection_changed)

        header_layout.addStretch()

        # STOP çalıştırıldığında üst kısımdaki boşlukta kırmızı harflerle DURDURULDU yazısı
        self.lbl_stopped = QLabel("DURDURULDU")
        self.lbl_stopped.setStyleSheet(
            "color: #ef4444; font-size: 16px; font-weight: 900; letter-spacing: 3px; padding: 3px 18px; "
            "background-color: rgba(239, 68, 68, 0.15); border: 2px solid #ef4444; border-radius: 8px;"
        )
        self.lbl_stopped.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_stopped.hide()
        header_layout.addWidget(self.lbl_stopped)

        header_layout.addStretch()

        self.status_badge = QLabel("● Kontrol ediliyor...")
        self.status_badge.setObjectName("statusBadge")
        header_layout.addWidget(self.status_badge)

        self.btn_quick_fix = QPushButton("🛡️ İzinleri Düzelt & Başlat")
        self.btn_quick_fix.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 6px 12px; border-radius: 6px;")
        self.btn_quick_fix.clicked.connect(self.fix_permissions)
        self.btn_quick_fix.hide()
        header_layout.addWidget(self.btn_quick_fix)

        self.btn_view_log = QPushButton("📋 Günlüğü İncele")
        self.btn_view_log.clicked.connect(self.show_daemon_log)
        header_layout.addWidget(self.btn_view_log)

        self.btn_restart_daemon = QPushButton("🔄 Yeniden Başlat")
        self.btn_restart_daemon.clicked.connect(lambda: self.restart_daemon(show_message=True))
        header_layout.addWidget(self.btn_restart_daemon)

        # STOP Butonu + Çark Butonu
        panic_box = QWidget()
        p_layout = QHBoxLayout(panic_box)
        p_layout.setContentsMargins(0, 0, 0, 0)
        p_layout.setSpacing(3)

        self.btn_panic = QPushButton("🛑 STOP")
        self.btn_panic.setStyleSheet("background-color: #dc2626; color: white; font-weight: bold; font-size: 13px; padding: 6px 16px; border-radius: 6px;")
        self.btn_panic.clicked.connect(self.trigger_panic)
        p_layout.addWidget(self.btn_panic)

        self.btn_panic_settings = QPushButton("⚙")
        self.btn_panic_settings.setFixedSize(32, 32)
        self.btn_panic_settings.setStyleSheet("background-color: #334155; color: #f8fafc; border: 1px solid #475569; border-radius: 6px; font-size: 16px; font-weight: bold;")
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

        self.tabs.addTab(self.tab_macros, "📋 Makrolar")
        self.tabs.addTab(self.tab_editor, "🛠️ Makro Düzenleyici")
        self.tabs.addTab(self.tab_recorder, "🔴 Canlı Tuş Kaydedici")
        self.tabs.addTab(self.tab_system, "⚙️ Sistem & Kılavuz")

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
        self.save_profile_to_disk(restart_daemon=True)
        self.refresh_macro_table()
        self.show_autosave_banner(f"'{selected_p.get('name')}' aktif edildi. Diğer profiller devre dışıdır.")

    def create_new_profile_dialog(self):
        name, ok = QInputDialog.getText(self, "Yeni Profil", "Yeni profil adını girin:")
        if ok and name.strip():
            new_p = {
                "id": f"profile-{int(time.time()*1000)}",
                "name": name.strip(),
                "panicKey": PANIC_KEY,
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
            self.show_autosave_banner(f"'{name.strip()}' profili oluşturuldu ve aktif edildi.")

    def on_tab_changed(self, index):
        if index == 1:
            # Makro düzenlerken ve metin yazarken diğer tüm makrolar durdurulsun
            if self.is_daemon_running() and not getattr(self, "is_manually_stopped", False):
                self.was_editor_daemon_running = True
                self.stop_daemon()
                self.show_autosave_banner("🛑 Düzenleme modu: Metin yazarken ve ayar yaparken makrolar durduruldu.")

            row = self.macro_table.currentRow()
            if 0 <= row < len(self.profile_data.get("macros", [])):
                self.selected_macro_idx = row
            if 0 <= self.selected_macro_idx < len(self.profile_data.get("macros", [])):
                self.load_macro_into_editor(self.selected_macro_idx)
        else:
            # Düzenleyiciden çıkıldığında motoru yeniden başlat (STOP tuşuna basılmamışsa)
            if getattr(self, "was_editor_daemon_running", False) and not getattr(self, "is_manually_stopped", False):
                self.was_editor_daemon_running = False
                self.restart_daemon(show_message=False)
                self.show_autosave_banner("▶ Makro motoru tekrar aktif edildi.")

    def configure_panic_key(self):
        dialog = KeyCaptureDialog(self)
        dialog.setWindowTitle("⚙️ STOP Tuşunu Ayarlayın")
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.captured_key:
            global PANIC_KEY
            PANIC_KEY = dialog.captured_key
            self.show_autosave_banner(f"STOP tuşu '{PANIC_KEY}' olarak güncellendi.")
            self.save_profile_to_disk(restart_daemon=True)

    def show_autosave_banner(self, text):
        self.statusBar().showMessage(f"💾 {text}", 3000)

    # SEKME 1: Makrolar
    def setup_macros_tab(self):
        layout = QVBoxLayout(self.tab_macros)
        layout.setSpacing(10)

        self.macro_table = QTableWidget()
        self.macro_table.setColumnCount(7)
        self.macro_table.setHorizontalHeaderLabels(["Sıra", "Aç / Kapat", "Makro Adı", "Tetikleyici Tuş", "Çalışma Modu", "Eylemler", "Sil"])
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
        self.btn_add_macro = QPushButton("➕ Yeni Makro")
        self.btn_add_macro.clicked.connect(self.create_new_macro)
        btn_layout.addWidget(self.btn_add_macro)

        self.btn_edit_macro = QPushButton("✏️ Düzenle")
        self.btn_edit_macro.clicked.connect(self.edit_selected_macro)
        btn_layout.addWidget(self.btn_edit_macro)

        self.btn_dup_macro = QPushButton("📑 Klonla")
        self.btn_dup_macro.clicked.connect(self.duplicate_selected_macro)
        btn_layout.addWidget(self.btn_dup_macro)

        self.btn_del_macro = QPushButton("✕ Sil (Del)")
        self.btn_del_macro.setStyleSheet("color: #ef4444; font-weight: bold;")
        self.btn_del_macro.clicked.connect(self.delete_selected_macro)
        btn_layout.addWidget(self.btn_del_macro)

        btn_layout.addStretch()

        self.btn_save_all = QPushButton("Kaydet")
        self.btn_save_all.setStyleSheet("background-color: #10b981; color: #022c22; font-weight: bold; padding: 6px 18px; border-radius: 6px;")
        self.btn_save_all.clicked.connect(lambda: self.save_profile_to_disk(restart_daemon=True))
        btn_layout.addWidget(self.btn_save_all)

        layout.addLayout(btn_layout)
        self.refresh_macro_table()

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
            lbl_seq.setStyleSheet("font-weight: bold; color: #38bdf8; font-size: 12px; min-width: 14px;")
            seq_layout.addWidget(lbl_seq)

            btn_up = QPushButton("↑")
            btn_up.setFixedSize(22, 22)
            btn_up.setStyleSheet("QPushButton { background-color: #1e293b; color: #38bdf8; border: 1px solid #334155; border-radius: 4px; font-size: 11px; font-weight: bold; } QPushButton:hover { background-color: #0284c7; color: white; }")
            btn_up.setToolTip("Yukarı Taşı (Yukarı Ok)")
            btn_up.setEnabled(row > 0)
            btn_up.clicked.connect(lambda _, r=row: self.move_macro_up_index(r))
            seq_layout.addWidget(btn_up)

            btn_down = QPushButton("↓")
            btn_down.setFixedSize(22, 22)
            btn_down.setStyleSheet("QPushButton { background-color: #1e293b; color: #38bdf8; border: 1px solid #334155; border-radius: 4px; font-size: 11px; font-weight: bold; } QPushButton:hover { background-color: #0284c7; color: white; }")
            btn_down.setToolTip("Aşağı Taşı (Aşağı Ok)")
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
            lbl_s = QLabel("AÇIK" if is_active else "KAPALI")
            lbl_s.setStyleSheet("color: #10b981; font-weight: bold; font-size: 11px;" if is_active else "color: #94a3b8; font-size: 11px;")

            def make_toggle(r_idx, label):
                def cb(checked):
                    label.setText("AÇIK" if checked else "KAPALI")
                    label.setStyleSheet("color: #10b981; font-weight: bold; font-size: 11px;" if checked else "color: #94a3b8; font-size: 11px;")
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
            btn_x.setStyleSheet("QPushButton { background-color: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid #ef4444; border-radius: 5px; font-weight: 900; font-size: 14px; } QPushButton:hover { background-color: #dc2626; color: white; }")
            btn_x.setToolTip("Makroyu Sil (Kırmızı X)")
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
    def setup_editor_tab(self):
        layout = QVBoxLayout(self.tab_editor)
        layout.setSpacing(10)

        # Düzenleyici Üst Bilgi Rozeti (Makrolar Durduruldu Bildirimi)
        editor_banner = QFrame()
        editor_banner.setStyleSheet("background-color: rgba(14, 165, 233, 0.12); border: 1px solid #0284c7; border-radius: 8px; padding: 7px 12px;")
        eb_layout = QHBoxLayout(editor_banner)
        eb_layout.setContentsMargins(4, 2, 4, 2)
        lbl_eb = QLabel("🛑 Güvenli Düzenleme Modu: Metin yazarken veya makro ayarları yapılırken diğer makrolar durdurulur.")
        lbl_eb.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: bold;")
        eb_layout.addWidget(lbl_eb)
        layout.addWidget(editor_banner)

        form_group = QGroupBox("Makro Yapılandırması")
        form_layout = QFormLayout(form_group)

        self.edit_name = QLineEdit()
        form_layout.addRow("Makro Adı:", self.edit_name)

        trig_row = QHBoxLayout()
        self.combo_trigger_key = QComboBox()
        self.combo_trigger_key.setEditable(True)
        self.combo_trigger_key.addItems([
            "KEY_LEFTSHIFT+KEY_LEFTCTRL", "KEY_LEFTCTRL+KEY_SPACE", "KEY_LEFTSHIFT+KEY_SPACE",
            "KEY_F1", "KEY_F2", "KEY_F3", "KEY_F4", "KEY_F5", "KEY_F6", "KEY_F7", "KEY_F8",
            "KEY_SPACE", "KEY_X", "KEY_C", "KEY_V", "BTN_SIDE", "BTN_EXTRA"
        ])
        trig_row.addWidget(self.combo_trigger_key)

        btn_capture = QPushButton("🎯 Tuşa / İkili Kombinasyona Basarak Ayarla")
        btn_capture.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold;")
        btn_capture.clicked.connect(self.capture_trigger_key)
        trig_row.addWidget(btn_capture)
        form_layout.addRow("Tetikleyici Tuş:", trig_row)

        self.combo_mode = QComboBox()
        self.combo_mode.addItems([
            "Tek Seferlik (ONCE)",
            "Basılı Tutulduğu Sürece (WHILE_HELD)",
            "Aç / Kapa Döngüsü (TOGGLE_LOOP)",
            "Tekrar Sayısı (REPEAT_COUNT)",
            "Çift Dokunma (DOUBLE_TAP)",
            "Uzun Basım (HOLD_LONG_PRESS)",
            "Bas-Bırak Çift Eylemi (PRESS_AND_RELEASE)"
        ])
        form_layout.addRow("Çalışma Modu:", self.combo_mode)

        self.spin_repeat = QSpinBox()
        self.spin_repeat.setRange(1, 9999)
        self.spin_repeat.setValue(1)
        form_layout.addRow("Tekrar Sayısı:", self.spin_repeat)

        layout.addWidget(form_group)

        # Eylemler Tablosu
        self.action_table = QTableWidget()
        self.action_table.setColumnCount(3)
        self.action_table.setHorizontalHeaderLabels(["Sıra", "Eylem Tipi", "Parametreler"])
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
        btn_add_tap = QPushButton("➕ Tuş Bas-Çek")
        btn_add_tap.setStyleSheet("background-color: #0369a1; color: white; font-weight: bold;")
        btn_add_tap.clicked.connect(lambda: self.add_editor_action("KEY_TAP"))
        act_row1.addWidget(btn_add_tap)

        btn_add_down = QPushButton("➕ Tuşa Bas (Basılı Tut)")
        btn_add_down.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold;")
        btn_add_down.setToolTip("Belirtilen tuşu basılı bırakır (Tuşun basılı kalması)")
        btn_add_down.clicked.connect(lambda: self.add_editor_action("KEY_DOWN"))
        act_row1.addWidget(btn_add_down)

        btn_add_up = QPushButton("➕ Tuşu Bırak")
        btn_add_up.setStyleSheet("background-color: #475569; color: white; font-weight: bold;")
        btn_add_up.setToolTip("Basılı tutulan tuşu serbest bırakır")
        btn_add_up.clicked.connect(lambda: self.add_editor_action("KEY_UP"))
        act_row1.addWidget(btn_add_up)

        btn_add_mclick = QPushButton("➕ Fare Tıkla")
        btn_add_mclick.setStyleSheet("background-color: #b45309; color: white; font-weight: bold;")
        btn_add_mclick.clicked.connect(lambda: self.add_editor_action("MOUSE_CLICK"))
        act_row1.addWidget(btn_add_mclick)

        btn_add_mdown = QPushButton("➕ Fare Basılı Tut")
        btn_add_mdown.setStyleSheet("background-color: #d97706; color: white; font-weight: bold;")
        btn_add_mdown.setToolTip("Fare tuşunu basılı bırakır")
        btn_add_mdown.clicked.connect(lambda: self.add_editor_action("MOUSE_DOWN"))
        act_row1.addWidget(btn_add_mdown)

        btn_add_mup = QPushButton("➕ Fare Bırak")
        btn_add_mup.setStyleSheet("background-color: #78716c; color: white; font-weight: bold;")
        btn_add_mup.setToolTip("Basılı fare tuşunu serbest bırakır")
        btn_add_mup.clicked.connect(lambda: self.add_editor_action("MOUSE_UP"))
        act_row1.addWidget(btn_add_mup)

        layout.addLayout(act_row1)

        # 2. Sıra: Gecikme, Metin, Eylem Düzenleme, Silme ve Kaydetme Butonları
        act_row2 = QHBoxLayout()
        btn_add_del = QPushButton("➕ Gecikme")
        btn_add_del.clicked.connect(lambda: self.add_editor_action("DELAY"))
        act_row2.addWidget(btn_add_del)

        btn_add_text = QPushButton("➕ Metin Yazdır")
        btn_add_text.clicked.connect(lambda: self.add_editor_action("TEXT"))
        act_row2.addWidget(btn_add_text)

        btn_edit_act = QPushButton("🎯 Eylem Tuşunu Ayarla / Düzenle")
        btn_edit_act.setStyleSheet("background-color: #4338ca; color: white; font-weight: bold;")
        btn_edit_act.clicked.connect(self.edit_selected_editor_action)
        act_row2.addWidget(btn_edit_act)

        btn_del_act = QPushButton("❌ Eylemi Sil (Del)")
        btn_del_act.clicked.connect(self.delete_editor_action)
        act_row2.addWidget(btn_del_act)

        btn_clear_all = QPushButton("🗑️ Tüm Eylemleri Sil")
        btn_clear_all.setStyleSheet("color: #f87171; font-weight: bold;")
        btn_clear_all.clicked.connect(self.clear_all_editor_actions)
        act_row2.addWidget(btn_clear_all)

        act_row2.addStretch()

        self.btn_save_macro = QPushButton("Kaydet")
        self.btn_save_macro.setStyleSheet("background-color: #10b981; color: #022c22; font-weight: bold; padding: 6px 20px; font-size: 13px;")
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
            self.current_editing_actions = list(m.get("actions", []))
            self.refresh_editor_actions_table()

    def refresh_editor_actions_table(self):
        actions = getattr(self, "current_editing_actions", [])
        self.action_table.setRowCount(len(actions))
        type_labels = {
            "KEY_TAP": "Tuş Bas-Çek",
            "KEY_DOWN": "Tuşa Bas (Basılı Tut)",
            "KEY_UP": "Tuşu Bırak",
            "MOUSE_CLICK": "Fare Tıkla",
            "MOUSE_DOWN": "Fare Basılı Tut",
            "MOUSE_UP": "Fare Bırak",
            "DELAY": "Gecikme Bekle",
            "TEXT": "Metin Yazdır"
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
                params = f"Tuş: {act.get('key', '-')} (Basılı Kalır)"
            elif a_type == "KEY_UP":
                params = f"Tuş: {act.get('key', '-')} (Serbest Bırakılır)"
            elif a_type == "KEY_TAP":
                params = f"Tuş: {act.get('key', '-')} (Basma: {act.get('delayMs', 20)}ms)"
            elif a_type == "MOUSE_DOWN":
                params = f"Fare: {act.get('mouseButton', 'BTN_LEFT')} (Basılı Kalır)"
            elif a_type == "MOUSE_UP":
                params = f"Fare: {act.get('mouseButton', 'BTN_LEFT')} (Serbest Bırakılır)"
            elif a_type == "MOUSE_CLICK":
                params = f"Fare: {act.get('mouseButton', 'BTN_LEFT')}"
            else:
                params = act.get("key") or "-"
            self.action_table.setItem(i, 2, QTableWidgetItem(params))

    def add_editor_action(self, act_type):
        actions = getattr(self, "current_editing_actions", [])
        if act_type in ("KEY_TAP", "KEY_DOWN", "KEY_UP"):
            dlg = KeyCaptureDialog(self)
            dlg.setWindowTitle("Makronun Basacağı Tuşu Seçin (Klavyeden Tuşa Basın)")
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
            chosen, ok = QInputDialog.getItem(self, "Fare Tuşu Seç", "Makro fare tuşu:", btn_options, 0, False)
            btn_name = chosen if ok else "BTN_LEFT"
            if act_type == "MOUSE_CLICK":
                actions.append({"type": "MOUSE_CLICK", "mouseButton": btn_name, "delayMs": 15})
            elif act_type == "MOUSE_DOWN":
                actions.append({"type": "MOUSE_DOWN", "mouseButton": btn_name})
            elif act_type == "MOUSE_UP":
                actions.append({"type": "MOUSE_UP", "mouseButton": btn_name})

        elif act_type == "DELAY":
            ms, ok = QInputDialog.getInt(self, "Gecikme Süresi", "Milisaniye (ms):", 50, 1, 60000)
            if ok:
                actions.append({"type": "DELAY", "delayMs": ms, "jitterMs": 2})

        elif act_type == "TEXT":
            text, ok = QInputDialog.getText(self, "Metin Makrosu", "Yazdırılacak metni girin:")
            if ok and text:
                actions.append({"type": "TEXT", "text": text})
            elif ok:
                actions.append({"type": "TEXT", "text": "Selam CachyOS!"})

        self.refresh_editor_actions_table()
        if actions:
            self.action_table.selectRow(len(actions) - 1)

    def edit_selected_editor_action(self):
        r = self.action_table.currentRow()
        actions = getattr(self, "current_editing_actions", [])
        if not (0 <= r < len(actions)):
            return
        act = actions[r]
        act_type = act.get("type", "")

        if act_type in ("KEY_TAP", "KEY_DOWN", "KEY_UP"):
            dlg = KeyCaptureDialog(self)
            dlg.setWindowTitle("Yeni Tuşa Basın")
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.captured_key:
                act["key"] = dlg.captured_key.split("+")[-1]
            if act_type == "KEY_TAP":
                cur_del = act.get("delayMs", 20)
                ms, ok = QInputDialog.getInt(self, "Tuş Basma Süresi", "Tuş basılı kalma süresi (ms):", cur_del, 1, 10000)
                if ok:
                    act["delayMs"] = ms

        elif act_type in ("MOUSE_CLICK", "MOUSE_DOWN", "MOUSE_UP"):
            btn_options = ["BTN_LEFT", "BTN_RIGHT", "BTN_MIDDLE", "BTN_SIDE", "BTN_EXTRA"]
            cur_btn = act.get("mouseButton", "BTN_LEFT")
            cur_idx = btn_options.index(cur_btn) if cur_btn in btn_options else 0
            chosen, ok = QInputDialog.getItem(self, "Fare Tuşu Değiştir", "Fare tuşu:", btn_options, cur_idx, False)
            if ok:
                act["mouseButton"] = chosen

        elif act_type == "DELAY":
            cur_del = act.get("delayMs", 50)
            ms, ok = QInputDialog.getInt(self, "Gecikme Süresi", "Milisaniye (ms):", cur_del, 1, 60000)
            if ok:
                act["delayMs"] = ms

        elif act_type == "TEXT":
            cur_txt = act.get("text", "")
            text, ok = QInputDialog.getText(self, "Metin Düzenle", "Yazdırılacak metin:", text=cur_txt)
            if ok:
                act["text"] = text

        self.refresh_editor_actions_table()
        self.action_table.selectRow(r)

    def clear_all_editor_actions(self):
        actions = getattr(self, "current_editing_actions", [])
        if actions:
            reply = QMessageBox.question(
                self,
                "Tüm Eylemleri Sil",
                "Bu makrodaki tüm eylemleri silmek istediğinizden emin misiniz?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                actions.clear()
                self.refresh_editor_actions_table()

    def delete_editor_action(self):
        r = self.action_table.currentRow()
        actions = getattr(self, "current_editing_actions", [])
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
            m["actions"] = getattr(self, "current_editing_actions", [])
            self.save_profile_to_disk(restart_daemon=True)
            self.refresh_macro_table()

            self.btn_save_macro.setText("Kaydedildi...")
            self.btn_save_macro.setEnabled(False)
            QTimer.singleShot(500, lambda: (
                self.btn_save_macro.setText("Kaydet"),
                self.btn_save_macro.setEnabled(True),
                self.tabs.setCurrentIndex(0)
            ))

    # SEKME 3: Canlı Kaydedici
    def setup_recorder_tab(self):
        layout = QVBoxLayout(self.tab_recorder)
        layout.addWidget(QLabel("Milisaniye hassasiyetinde canlı klavye ve fare hareketlerini kaydeder."))

        self.rec_table = QTableWidget()
        self.rec_table.setColumnCount(4)
        self.rec_table.setHorizontalHeaderLabels(["Sıra", "Olay", "Tuş / Buton", "Gecikme (ms)"])
        self.rec_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.rec_table)

        b_box = QHBoxLayout()
        self.btn_start_rec = QPushButton("⏺️ Kaydı Başlat")
        self.btn_start_rec.clicked.connect(self.toggle_recording)
        b_box.addWidget(self.btn_start_rec)

        btn_clear = QPushButton("🗑️ Temizle")
        btn_clear.clicked.connect(self.clear_recorded)
        b_box.addWidget(btn_clear)

        btn_conv = QPushButton("💾 Kaydı Yeni Makro Olarak Ekle")
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

            self.btn_start_rec.setText("⏹️ Kaydı Durdur")
            self.btn_start_rec.setStyleSheet("background-color: #ef4444; color: white;")
            self.last_key_time = time.time()
            self.grabKeyboard()
            self.show_autosave_banner("🛑 Canlı kayıt modu: Diğer tüm makrolar durduruldu.")
        else:
            self.btn_start_rec.setText("⏺️ Kaydı Başlat")
            self.btn_start_rec.setStyleSheet("")
            self.releaseKeyboard()
            if getattr(self, "was_recording_daemon_running", False):
                self.restart_daemon(show_message=False)
                self.show_autosave_banner("▶ Makro motoru tekrar aktif edildi.")

    def mousePressEvent(self, event):
        if self.recording_active:
            m_btn = "LEFT" if event.button() == Qt.MouseButton.LeftButton else "RIGHT"
            now = time.time()
            delta = int((now - self.last_key_time) * 1000)
            self.last_key_time = now
            if delta > 10 and self.recorded_events:
                self.recorded_events.append({"type": "DELAY", "delayMs": delta, "jitterMs": 2})
            self.recorded_events.append({"type": "MOUSE_DOWN", "mouseButton": m_btn})
            self.refresh_rec_table()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        # STOP kontrolü
        k_seq = QKeySequence(event.key()).toString().upper()
        if k_seq == PANIC_KEY.replace("KEY_", "").upper() or event.key() == Qt.Key.Key_Pause:
            self.trigger_panic()
            return

        if event.key() == Qt.Key.Key_Escape and not self.recording_active:
            self.tabs.setCurrentIndex(0)
            return

        if self.recording_active:
            now = time.time()
            delta = int((now - self.last_key_time) * 1000)
            self.last_key_time = now
            key_code = f"KEY_{k_seq}" if k_seq else f"KEY_CODE_{event.key()}"
            if delta > 10 and self.recorded_events:
                self.recorded_events.append({"type": "DELAY", "delayMs": delta, "jitterMs": 2})
            self.recorded_events.append({"type": "KEY_DOWN", "key": key_code})
            self.refresh_rec_table()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if self.recording_active:
            now = time.time()
            delta = int((now - self.last_key_time) * 1000)
            self.last_key_time = now
            k_seq = QKeySequence(event.key()).toString().upper()
            key_code = f"KEY_{k_seq}" if k_seq else f"KEY_CODE_{event.key()}"
            if delta > 10 and self.recorded_events:
                self.recorded_events.append({"type": "DELAY", "delayMs": delta, "jitterMs": 2})
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
            "name": f"Kayıtlı Makro ({len(self.recorded_events)} adım)",
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
    def setup_system_tab(self):
        layout = QVBoxLayout(self.tab_system)
        self.sys_info = QTextEdit()
        self.sys_info.setReadOnly(True)
        layout.addWidget(self.sys_info)

        p_box = QHBoxLayout()
        btn_fix = QPushButton("🛡️ Donanım İzinlerini Otomatik Düzelt (setfacl)")
        btn_fix.setStyleSheet("background-color: #0284c7; color: white; font-weight: bold; padding: 8px;")
        btn_fix.clicked.connect(self.fix_permissions)
        p_box.addWidget(btn_fix)

        btn_ref = QPushButton("🔄 Durumu Yenile")
        btn_ref.clicked.connect(self.refresh_system_status)
        p_box.addWidget(btn_ref)

        layout.addLayout(p_box)
        self.refresh_system_status()

    def refresh_system_status(self):
        uinput_ok = os.access("/dev/uinput", os.W_OK)
        guide_text = f"""=== MacroStat Donanım ve Sistem Tanılama ===
Kernel /dev/uinput: {"✔ Erişilebilir (Yazma İzni Var)" if uinput_ok else "❌ Erişim Yok (İzin Gerekli)"}
Motor İkili Dosyası: {DAEMON_BIN or "İkili Dosya Bulunamadı (cargo build --release çalıştırın)"}
Profil Dosyası: {PROFILE_PATH.resolve() if PROFILE_PATH else "Bulunamadı"}
Acil Durdurma Tuşu (STOP): {PANIC_KEY}
Log Dosyası: {LOG_FILE}
"""
        self.sys_info.setPlainText(guide_text)

    def fix_permissions(self):
        try:
            import getpass
            username = os.environ.get("SUDO_USER") or os.environ.get("USER") or getpass.getuser()
            cmd = (
                f"pkexec sh -c 'modprobe uinput 2>/dev/null; "
                f"chmod 666 /dev/uinput 2>/dev/null; "
                f"chmod 666 /dev/input/event* 2>/dev/null; "
                f"setfacl -m u:{username}:rw /dev/uinput 2>/dev/null; "
                f"setfacl -m u:{username}:rw /dev/input/event* 2>/dev/null; "
                f"usermod -aG input {username} 2>/dev/null; "
                f"udevadm control --reload-rules 2>/dev/null; "
                f"udevadm trigger 2>/dev/null' 2>/dev/null || "
                f"sudo sh -c 'chmod 666 /dev/uinput /dev/input/event* 2>/dev/null; usermod -aG input {username} 2>/dev/null'"
            )
            subprocess.run(cmd, shell=True)
            time.sleep(0.2)
            self.restart_daemon(show_message=False)
            self.refresh_system_status()
            QMessageBox.information(self, "İzinler Düzeltildi", "Donanım izinleri başarıyla güncellendi ve motor başlatıldı.")
        except Exception as e:
            QMessageBox.critical(self, "Hata", str(e))

    def is_daemon_running(self):
        if self.daemon_proc is not None:
            if self.daemon_proc.poll() is None:
                return True
        try:
            res = subprocess.run(["pgrep", "-f", "cachymacro-daemon"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            return bool(res.stdout.strip())
        except Exception:
            return False

    def check_and_auto_start_daemon(self):
        if getattr(self, "is_manually_stopped", False) or getattr(self, "was_editor_daemon_running", False):
            return
        if not self.is_daemon_running():
            self.restart_daemon(show_message=False)

    def update_daemon_status(self):
        if getattr(self, "is_manually_stopped", False):
            self.lbl_stopped.show()
            self.status_badge.setText("🔴 Motor Durduruldu (STOP)")
            self.status_badge.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 13px;")
            return
        if getattr(self, "was_editor_daemon_running", False):
            self.status_badge.setText("🛑 Düzenleme Modu (Beklemede)")
            self.status_badge.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 13px;")
            return
        if self.is_daemon_running():
            self.failed_status_checks = 0
            self.status_badge.setText("🟢 Aktif")
            self.status_badge.setStyleSheet("color: #10b981; font-weight: bold; font-size: 13px;")
            self.btn_view_log.setText("📋 Günlük")
            if hasattr(self, 'btn_quick_fix'):
                self.btn_quick_fix.hide()
        else:
            self.failed_status_checks += 1
            if self.failed_status_checks >= 2:
                self.status_badge.setText("🔴 Motor Durduruldu")
                self.status_badge.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 13px;")
                self.btn_view_log.setText("⚠️ Hatayı İncele")
                if hasattr(self, 'btn_quick_fix'):
                    self.btn_quick_fix.show()

    def stop_daemon(self):
        global DAEMON_PROC
        try:
            if self.daemon_proc is not None:
                try:
                    if hasattr(os, "killpg"):
                        os.killpg(os.getpgid(self.daemon_proc.pid), signal.SIGKILL)
                    else:
                        self.daemon_proc.kill()
                except Exception:
                    pass
                self.daemon_proc = None
            DAEMON_PROC = None
            subprocess.run(["pkill", "-9", "-f", "cachymacro-daemon"], stderr=subprocess.DEVNULL)
            self.update_daemon_status()
        except Exception:
            pass

    def restart_daemon(self, show_message=False):
        global DAEMON_BIN, PROFILE_PATH, DAEMON_PROC
        self.is_manually_stopped = False
        self.lbl_stopped.hide()
        if hasattr(self, 'btn_restart_daemon'):
            self.btn_restart_daemon.setStyleSheet("")

        DAEMON_BIN, PROFILE_PATH = locate_paths()
        try:
            if self.daemon_proc is not None:
                try:
                    if hasattr(os, "killpg"):
                        os.killpg(os.getpgid(self.daemon_proc.pid), signal.SIGTERM)
                    else:
                        self.daemon_proc.terminate()
                    self.daemon_proc.wait(timeout=0.2)
                except Exception:
                    try:
                        self.daemon_proc.kill()
                    except Exception:
                        pass
                self.daemon_proc = None

            subprocess.run(["pkill", "-9", "-f", "cachymacro-daemon"], stderr=subprocess.DEVNULL)
            time.sleep(0.08)

            if not DAEMON_BIN or not DAEMON_BIN.exists():
                cargo_candidates = [
                    SCRIPT_DIR / "Cargo.toml",
                    SCRIPT_DIR / "cachymacro" / "Cargo.toml",
                    SCRIPT_DIR.parent / "Cargo.toml",
                    SCRIPT_DIR.parent / "cachymacro" / "Cargo.toml",
                ]
                cargo_dir = None
                for c in cargo_candidates:
                    if c.exists() and c.is_file():
                        cargo_dir = c.parent
                        break

                if cargo_dir and shutil.which("cargo"):
                    self.status_badge.setText("⚙️ Motor derleniyor...")
                    self.status_badge.setStyleSheet("color: #38bdf8; font-weight: bold;")
                    QApplication.processEvents()
                    try:
                        subprocess.run(["cargo", "build", "--release"], cwd=cargo_dir, check=False)
                        DAEMON_BIN, PROFILE_PATH = locate_paths()
                    except Exception:
                        pass

            if not DAEMON_BIN or not DAEMON_BIN.exists():
                if show_message:
                    QMessageBox.warning(self, "Motor Bulunamadı", "Lütfen terminalde 'cargo build --release' komutunu çalıştırın.")
                self.update_daemon_status()
                return

            log_f = open(LOG_FILE, "a", encoding="utf-8")
            self.daemon_proc = subprocess.Popen(
                [str(DAEMON_BIN.resolve()), str(PROFILE_PATH.resolve())],
                cwd=str(DAEMON_BIN.parent.parent if DAEMON_BIN.parent.name == "release" else DAEMON_BIN.parent),
                stdout=log_f,
                stderr=subprocess.STDOUT,
                start_new_session=True
            )
            DAEMON_PROC = self.daemon_proc

            if show_message:
                time.sleep(0.3)
                self.failed_status_checks = 0
                self.update_daemon_status()
                QMessageBox.information(self, "Başarılı", "Makro motoru başlatıldı.")
            else:
                QTimer.singleShot(350, self.update_daemon_status)
        except Exception as e:
            if show_message:
                QMessageBox.critical(self, "Hata", str(e))

    def trigger_panic(self):
        try:
            self.is_manually_stopped = True
            self.lbl_stopped.show()
            self.stop_daemon()
            self.status_badge.setText("🔴 Motor Durduruldu (STOP)")
            self.status_badge.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 13px;")
            self.btn_restart_daemon.setStyleSheet("background-color: #10b981; color: #022c22; font-weight: bold; border-radius: 6px; padding: 6px 14px;")
            self.show_autosave_banner("🛑 STOP Tetiklendi! Motor 'Yeniden Başlat' butonuna basılana dek kapalı kalacaktır.")
        except Exception:
            pass

    def show_daemon_log(self):
        content = "Log dosyası henüz oluşmadı."
        if LOG_FILE.exists():
            try:
                with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception as e:
                content = f"Log okunamadı: {e}"
        dlg = QDialog(self)
        dlg.setWindowTitle("Motor Günlüğü")
        dlg.resize(600, 400)
        l = QVBoxLayout(dlg)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setPlainText(content)
        l.addWidget(txt)
        dlg.exec()

    def closeEvent(self, event):
        try:
            self.status_timer.stop()
        except Exception:
            pass
        cleanup_daemon()
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.aboutToQuit.connect(cleanup_daemon)
    window = MacroStatApp()
    window.show()
    exit_code = app.exec()
    cleanup_daemon()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()

