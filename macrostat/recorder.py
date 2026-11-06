# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Canlı kaydedici ve klavye/fare olayları."""

import json
import os
import time
from pathlib import Path

from . import common, theme
from .common import *  # noqa: F401,F403
from .widgets import SlidingSwitch, KeyCaptureDialog  # noqa: F401

#: Fare kaydında kabul edilen düğme adları (motorla aynı küme).
_MOUSE_BUTTON_NAMES = frozenset({"BTN_LEFT", "BTN_RIGHT", "BTN_MIDDLE", "BTN_SIDE", "BTN_EXTRA"})
_MAX_MOUSE_POINTS = 200_000
_MAX_MOUSE_DT_MS = 600_000

def sanitize_mouse_buttons(data):
    """Motorun kaydettiği fare düğmesi olaylarını doğrular ve sınırlara çeker."""
    if not isinstance(data, dict):
        return []
    raw = data.get("buttons")
    if not isinstance(raw, list):
        return []
    buttons = []
    for entry in raw:
        if not isinstance(entry, (list, tuple)) or len(entry) != 3:
            continue
        dt, name, down = entry
        if name not in _MOUSE_BUTTON_NAMES:
            continue
        try:
            dt = int(dt)
            down = int(down)
        except (TypeError, ValueError):
            continue
        if down not in (0, 1):
            continue
        buttons.append([max(0, min(dt, _MAX_MOUSE_DT_MS)), name, down])
        if len(buttons) >= _MAX_MOUSE_POINTS:
            break
    return buttons

def widget_is_within(widget, ancestor):
    """`widget` kendisi veya bir alt/üst öğesiyle `ancestor` içinde mi?"""
    seen = 0
    while widget is not None and seen < 64:
        if widget is ancestor:
            return True
        # Uygulama olay filtresi QWidget olmayan nesneler (ör. QObject/QWindow) de alır.
        parent_widget = getattr(widget, "parentWidget", None)
        if parent_widget is None:
            return False
        widget = parent_widget()
        seen += 1
    return False

def merge_mouse_path_buttons(points, buttons):
    """Hareket noktalarını düğme olaylarıyla zaman sırasına göre birleştirir.

    Noktaların ``dt`` değerleri artımlıdır; düğme zamanları kaydın başından
    itibaren mutlaktır. Bu yüzden noktalar önce mutlak zamana çevrilir, her
    bölümün ilk ``dt`` değeri bir önceki olaydan (düğme veya nokta) geçen
    süreye göre yeniden hesaplanır; aksi hâlde bekleme iki kez sayılır.
    """
    cleaned = [list(p) for p in points if isinstance(p, (list, tuple)) and len(p) == 3]
    if not buttons:
        return [{"type": "MOUSE_PATH", "points": cleaned}]

    absolute = []
    elapsed = 0
    for dt, dx, dy in cleaned:
        elapsed += max(0, int(dt))
        absolute.append((elapsed, dx, dy))

    events = []
    index = 0
    base = 0  # son yayımlanan olayın mutlak zamanı (ms)
    def segment_points(start, stop, previous):
        segment = []
        for when_point, dx, dy in absolute[start:stop]:
            segment.append([max(0, when_point - previous), dx, dy])
            previous = when_point
        return segment, previous

    for when, name, down in sorted(buttons, key=lambda b: b[0]):
        start = index
        while index < len(absolute) and absolute[index][0] <= when:
            index += 1
        if index > start:
            segment, base = segment_points(start, index, base)
            events.append({"type": "MOUSE_PATH", "points": segment})
        gap = when - base
        if gap > 0:
            events.append({"type": "DELAY", "delayMs": gap, "jitterMs": 2})
        base = when
        events.append({
            "type": "MOUSE_DOWN" if down else "MOUSE_UP",
            "mouseButton": name,
        })
    if index < len(absolute):
        tail, _ = segment_points(index, len(absolute), base)
        events.append({"type": "MOUSE_PATH", "points": tail})
    return events

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

        self.chk_mouse_path = QCheckBox(T("Fare hareketini sistem genelinde kaydet"))
        self.chk_mouse_path.setToolTip(T(
            "Kayıt sırasında fare hareketleri evdev üzerinden tüm masaüstünde izlenir. "
            "Kayıt yalnızca göreli hareketi saklar; Pause tuşu kaydı bitirir."
        ))
        layout.addWidget(self.chk_mouse_path)

        # Sistem geneli fare kaydı alt süreci (daemon --record-mouse).
        self._mouse_record_proc = None
        self._mouse_record_file = None
        self._mouse_record_started = 0.0
        self._mouse_record_timer = QTimer(self)
        self._mouse_record_timer.timeout.connect(self._update_mouse_record_label)

        b_box = QHBoxLayout()
        self.btn_start_rec = QPushButton(T("Kaydı Başlat"))
        theme.set_variant(self.btn_start_rec, "primary")
        self.btn_start_rec.clicked.connect(self.toggle_recording)
        b_box.addWidget(self.btn_start_rec)

        self.btn_clear_rec = QPushButton(T("Temizle"))
        self.btn_clear_rec.clicked.connect(self.clear_recorded)
        b_box.addWidget(self.btn_clear_rec)

        self.btn_conv_rec = QPushButton(T("Kaydı Yeni Makro Olarak Ekle"))
        self.btn_conv_rec.clicked.connect(self.convert_recording_to_macro)
        b_box.addWidget(self.btn_conv_rec)

        layout.addLayout(b_box)

    def toggle_recording(self):
        if self.recording_active:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        # Kayıt esnasında makroların devreye girmemesi için motoru durdur
        if self.is_daemon_running():
            self.was_recording_daemon_running = True
            self.stop_daemon()
        else:
            self.was_recording_daemon_running = False

        self.recording_active = True
        self.last_key_time = time.time()
        self.btn_start_rec.setText(T("Kaydı Durdur"))
        theme.set_variant(self.btn_start_rec, "danger")
        self.chk_mouse_path.setEnabled(False)

        if self.chk_mouse_path.isChecked():
            if not self._start_mouse_path_recording():
                self.recording_active = False
                self._finish_recording_ui()
                return
            self.show_autosave_banner(T(
                "Sistem geneli fare kaydı: durdurmak için Pause tuşuna basın veya düğmeyi kullanın."
            ))
        else:
            self.grabKeyboard()
            # Fare olayları alt öğelerde yutulduğu için uygulama düzeyinde dinle.
            app = QApplication.instance()
            if app is not None:
                app.installEventFilter(self)
            self.show_autosave_banner(T("Canlı kayıt modu: Diğer tüm makrolar durduruldu."))

    def _stop_recording(self):
        self.recording_active = False
        self.releaseKeyboard()
        if self._mouse_record_proc is not None:
            # Rust tarafı SIGTERM'de birleştirilmiş kaydı diske yazıp çıkar;
            # bitişi _mouse_record_finished işler.
            self._mouse_record_timer.stop()
            self.btn_start_rec.setEnabled(False)
            self.btn_start_rec.setText(T("Kayıt bitiriliyor..."))
            self._mouse_record_proc.terminate()
            return
        self._finish_recording_ui()

    def _finish_recording_ui(self):
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.btn_start_rec.setEnabled(True)
        self.btn_start_rec.setText(T("Kaydı Başlat"))
        theme.set_variant(self.btn_start_rec, "primary")
        self.chk_mouse_path.setEnabled(True)
        if getattr(self, "was_recording_daemon_running", False):
            self.was_recording_daemon_running = False
            self.restart_daemon(show_message=False)
            self.show_autosave_banner(T("Makro motoru tekrar aktif edildi."))

    def _start_mouse_path_recording(self):
        daemon_bin = getattr(common, "DAEMON_BIN", None)
        if not daemon_bin or not Path(daemon_bin).exists():
            QMessageBox.warning(
                self, T("Hata"),
                T("Motor ikilisi bulunamadı. Önce cargo build --release çalıştırın.")
            )
            return False
        self._mouse_record_file = str(
            common.RUNTIME_DIR / f"macrostat-mouse-{os.getpid()}.json")
        try:
            Path(self._mouse_record_file).unlink(missing_ok=True)
        except OSError:
            pass
        # KDE Wayland'da imleç konumu KWin betiğiyle okunabilir. Alınamazsa
        # kayıt göreli hareketle devam eder (mevcut davranış).
        start = None
        try:
            from .kwin import cursor_position
            start = cursor_position()
        except Exception:
            start = None

        arguments = [
            "--record-mouse", self._mouse_record_file,
            "--panic-key", common.PANIC_KEY,
        ]
        if start:
            arguments += ["--start-x", str(start[0]), "--start-y", str(start[1])]

        proc = QProcess(self)
        proc.setProgram(str(daemon_bin))
        proc.setArguments(arguments)
        proc.finished.connect(self._mouse_record_finished)
        proc.errorOccurred.connect(self._mouse_record_failed)
        self._mouse_record_proc = proc
        self._mouse_record_started = time.time()
        proc.start()
        if not proc.waitForStarted(1500):
            if self._mouse_record_proc is None:
                # errorOccurred zaten kullanıcıyı bilgilendirdi.
                return False
            self._mouse_record_proc = None
            QMessageBox.warning(self, T("Hata"), T("Fare kaydı başlatılamadı: {}").format(
                proc.errorString()))
            return False
        self._mouse_record_timer.start(500)
        self._update_mouse_record_label()
        return True

    def _update_mouse_record_label(self):
        if self._mouse_record_proc is None:
            return
        seconds = max(0, int(time.time() - self._mouse_record_started))
        self.btn_start_rec.setText(T("Durdur ({} sn)").format(seconds))

    def _mouse_record_failed(self, _error):
        if self._mouse_record_proc is None:
            return
        proc = self._mouse_record_proc
        self._mouse_record_proc = None
        self._mouse_record_timer.stop()
        self.recording_active = False
        message = proc.errorString() or T("bilinmeyen hata")
        self._cleanup_mouse_record_file()
        self._finish_recording_ui()
        proc.deleteLater()
        QMessageBox.warning(self, T("Hata"), T("Fare kaydı hatası: {}").format(message))

    def _cleanup_mouse_record_file(self):
        path = self._mouse_record_file
        self._mouse_record_file = None
        if path:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _sanitize_mouse_path(data):
        """Kayıt dosyasındaki noktaları doğrular ve güvenli sınırlara çeker."""
        if not isinstance(data, dict):
            return []
        raw_points = data.get("points")
        if not isinstance(raw_points, list):
            return []
        points = []
        for point in raw_points:
            if not isinstance(point, (list, tuple)) or len(point) != 3:
                continue
            try:
                dt, dx, dy = (int(v) for v in point)
            except (TypeError, ValueError):
                continue
            points.append([
                max(0, min(dt, 600_000)),
                max(-2_147_483_648, min(dx, 2_147_483_647)),
                max(-2_147_483_648, min(dy, 2_147_483_647)),
            ])
            if len(points) >= 200_000:
                break
        return points

    @staticmethod
    def _sanitize_mouse_start(data):
        """Kayıt dosyasındaki isteğe bağlı başlangıç imleç konumunu doğrular."""
        if not isinstance(data, dict):
            return None
        raw = data.get("start")
        if not isinstance(raw, (list, tuple)) or len(raw) != 2:
            return None
        try:
            x, y = (int(v) for v in raw)
        except (TypeError, ValueError):
            return None
        limit = 1_000_000
        return [max(-limit, min(x, limit)), max(-limit, min(y, limit))]

    def _mouse_record_finished(self, exit_code, _exit_status):
        if self._mouse_record_proc is None:
            return
        proc = self._mouse_record_proc
        self._mouse_record_proc = None
        self._mouse_record_timer.stop()
        self.recording_active = False
        stderr = bytes(proc.readAllStandardError()).decode("utf-8", "replace").strip()
        if exit_code != 0 and stderr:
            QMessageBox.warning(self, T("Fare kaydı hatası: {}").format(stderr.splitlines()[-1]))

        points = []
        buttons = []
        start = None
        path = self._mouse_record_file
        if path and Path(path).exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                points = self._sanitize_mouse_path(data)
                buttons = sanitize_mouse_buttons(data)
                start = self._sanitize_mouse_start(data)
            except (OSError, ValueError, json.JSONDecodeError) as e:
                QMessageBox.warning(self, T("Fare kaydı okunamadı: {}").format(e))
        self._cleanup_mouse_record_file()

        if points or buttons:
            events = merge_mouse_path_buttons(points, buttons)
            if start is not None:
                for event in events:
                    if event["type"] == "MOUSE_PATH":
                        event["start"] = start
                        break
            self.recorded_events.extend(events)
            self.refresh_rec_table()
            total_ms = sum(p[0] for p in points)
            self.show_autosave_banner(T("{} nokta, {} fare olayı kaydedildi ({} ms).").format(
                len(points), len(buttons), total_ms))
        elif exit_code == 0:
            self.show_autosave_banner(T("Fare kaydı boş; hareket algılanmadı."))

        proc.deleteLater()
        self._finish_recording_ui()

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

    def _recording_control_widgets(self):
        """Kayıt sırasında tıklanınca kayda alınmaması gereken kaydedici düğmeleri."""
        widgets = [getattr(self, name, None) for name in
                   ("btn_start_rec", "btn_clear_rec", "btn_conv_rec", "chk_mouse_path")]
        return [w for w in widgets if w is not None]

    def _mouse_event_from_recording_controls(self, obj):
        return any(widget_is_within(obj, control)
                   for control in self._recording_control_widgets())

    def eventFilter(self, obj, event):
        """Alt öğeler fare olaylarını yuttuğu için kayıt uygulama düzeyinde yapılır."""
        if getattr(self, "recording_active", False) and \
                not self._mouse_event_from_recording_controls(obj):
            etype = event.type()
            if etype in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
                button = event.button()
                if self._record_mouse_button(
                        button, etype == QEvent.Type.MouseButtonPress):
                    return False
            elif etype == QEvent.Type.Wheel:
                delta = event.angleDelta().y()
                if delta != 0:
                    self._recording_add_delay()
                    self.recorded_events.append({
                        "type": "MOUSE_SCROLL",
                        "scrollDelta": 1 if delta > 0 else -1,
                    })
                    self.refresh_rec_table()
        return super().eventFilter(obj, event)

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
            # Otomatik tekrar (tuş basılı tutulurken) yeni bir basış değildir;
            # aksi hâlde makro aynı tuşu onlarca kez basar.
            if event.isAutoRepeat():
                return
            key_code = self.map_qt_key_to_evdev(event.key(), event.text())
            if not key_code:
                key_code = f"KEY_CODE_{int(event.key())}"
            # Basışta üretilen adı sakla: bırakışta event.text() boş gelir ve
            # metne dayalı adlar (ör. sayısal tuş takımı) tutarsız üretilirdi.
            if not hasattr(self, "_recording_key_names"):
                self._recording_key_names = {}
            self._recording_key_names[event.key()] = key_code
            self._recording_add_delay()
            self.recorded_events.append({"type": "KEY_DOWN", "key": key_code})
            self.refresh_rec_table()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if self.recording_active:
            if event.isAutoRepeat():
                return
            key_code = getattr(self, "_recording_key_names", {}).pop(
                event.key(), None)
            if not key_code:
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
            event_type = ev.get("type", "")
            if event_type == "MOUSE_PATH":
                points = ev.get("points") or []
                detail = T("{} nokta").format(len(points))
                timing = f"{sum(int(p[0]) for p in points if len(p) == 3)} ms"
            else:
                detail = ev.get("key") or ev.get("mouseButton") or "-"
                timing = str(ev.get("delayMs", "-"))
            self.rec_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.rec_table.setItem(i, 1, QTableWidgetItem(event_type))
            self.rec_table.setItem(i, 2, QTableWidgetItem(detail))
            self.rec_table.setItem(i, 3, QTableWidgetItem(timing))

    def clear_recorded(self):
        self.recorded_events.clear()
        self._recording_key_names = {}
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
