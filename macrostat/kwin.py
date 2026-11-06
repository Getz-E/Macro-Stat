# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""KDE Wayland'da imleç konumunu KWin betiği üzerinden okur.

Wayland, uygulamalara imlecin genel ekran konumunu vermez. KWin'in betik
arayüzü ise `workspace.cursorPos` değerini salt okunur olarak sunar. Bu modül
geçici bir KWin betiği yükler, konumu D-Bus ile geri alır ve betiği kaldırır.
KDE dışında veya betik çalıştırılamıyorsa `None` döner; çağıran taraf mevcut
davranışına devam eder.
"""

import os
import tempfile
import time

from . import common

try:
    from PyQt6.QtCore import QEventLoop, QObject, QTimer, pyqtSlot
    from PyQt6.QtDBus import QDBus, QDBusConnection, QDBusMessage
except ImportError:  # QtDBus olmayan PyQt6 derlemeleri
    QDBus = QDBusConnection = None

_TIMEOUT_MS = 800
_SCRIPT_TIMEOUT_MS = 1500


def is_kde_wayland():
    """KDE Plasma Wayland oturumunda mıyız?"""
    if not (os.environ.get("WAYLAND_DISPLAY")
            or os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"):
        return False
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    return "KDE" in desktop


class _CursorSink(QObject):
    def __init__(self):
        super().__init__()
        self.position = None
        self.failed = False

    @pyqtSlot(int, int)
    def cursorpos(self, x, y):
        self.position = [int(x), int(y)]

    @pyqtSlot(str)
    def cursorerror(self, _message):
        self.failed = True


def write_script_file(script):
    """Betiği özel çalışma dizininde 0600 izinli geçici dosyaya yazar."""
    with tempfile.NamedTemporaryFile(
            "w", suffix=".js", prefix="macrostat-cursor-",
            dir=str(common.RUNTIME_DIR), delete=False, encoding="utf-8") as handle:
        handle.write(script)
        path = handle.name
    os.chmod(path, 0o600)
    return path


def _call(bus, service, path, interface, method, arguments):
    message = QDBusMessage.createMethodCall(service, path, interface, method)
    message.setArguments(arguments)
    return bus.call(message, QDBus.CallMode.Block, _SCRIPT_TIMEOUT_MS)


def _load_script(bus, script_path, name):
    reply = _call(bus, "org.kde.KWin", "/Scripting",
                  "org.kde.kwin.Scripting", "loadScript", [script_path, name])
    if reply.type() != QDBusMessage.MessageType.ReplyMessage or not reply.arguments():
        return None
    try:
        return int(reply.arguments()[0])
    except (TypeError, ValueError):
        return None


def _run_script(bus, script_id):
    _call(bus, "org.kde.KWin", f"/Scripting/Script{script_id}",
          "org.kde.kwin.Script", "run", [])


def _unload_script(bus, name):
    try:
        _call(bus, "org.kde.KWin", "/Scripting",
              "org.kde.kwin.Scripting", "unloadScript", [name])
    except Exception:
        pass


def cursor_position():
    """İmlecin mantıksal ekran konumunu `[x, y]` olarak döndürür; yoksa None."""
    if QDBusConnection is None or not is_kde_wayland():
        return None
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        return None

    unique = bus.baseService()
    stamp = time.time_ns()
    object_path = f"/macrostat/cursor/{os.getpid()}/{stamp}"
    script_name = f"macrostat-cursor-{os.getpid()}-{stamp}"
    sink = _CursorSink()
    if not bus.registerObject(
            object_path, sink, QDBusConnection.RegisterOption.ExportAllSlots):
        return None

    script_path = None
    script_id = None
    try:
        script = f"""
try {{
    var p = workspace.cursorPos;
    callDBus("{unique}", "{object_path}", "", "cursorpos", p.x, p.y);
}} catch (e) {{
    callDBus("{unique}", "{object_path}", "", "cursorerror", String(e));
}}
"""
        script_path = write_script_file(script)

        script_id = _load_script(bus, script_path, script_name)
        if script_id is None:
            return None
        _run_script(bus, script_id)

        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(_TIMEOUT_MS)
        loop.exec()
        timer.stop()
        return sink.position if not sink.failed else None
    except Exception:
        return None
    finally:
        if script_id is not None:
            _unload_script(bus, script_name)
        try:
            bus.unregisterObject(object_path)
        except Exception:
            pass
        if script_path:
            try:
                os.unlink(script_path)
            except OSError:
                pass
