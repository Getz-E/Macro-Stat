# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""MacroStat uygulama sınıfı ve giriş noktası."""

import fcntl
import os
import sys

from . import common, theme
from .common import *  # noqa: F401,F403
from .core import CoreMixin
from .macros import MacrosMixin
from .editor import EditorMixin
from .recorder import RecorderMixin
from .system import SystemMixin


class MacroStatApp(CoreMixin, MacrosMixin, EditorMixin, RecorderMixin,
                   SystemMixin, QMainWindow):
    """Sekmeli MacroStat arayüzü; davranış mixin modüllerinde ayrıştırılmıştır."""


_GUI_LOCK = None

def acquire_gui_single_instance():
    """İkinci bir arayüz örneğinin aynı profili/motoru yönetmesini engeller."""
    global _GUI_LOCK
    lock_path = common.RUNTIME_DIR / f"macrostat-gui-{os.getuid()}.lock"
    try:
        # Sabit adlı kilidi başka bir kullanıcı sembolik bağlantıyla yönlendirmesin.
        flags = (os.O_RDWR | os.O_CREAT | os.O_CLOEXEC
                 | getattr(os, "O_NOFOLLOW", 0))
        fd = os.open(lock_path, flags, 0o600)
        handle = os.fdopen(fd, "w", encoding="utf-8")
    except OSError:
        # Kilit dosyası açılamazsa (salt-okunur / kısıtlı dizin) uygulamayı engelleme.
        return True
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return False
    # Önceki (daha uzun) pid metni kalmasın.
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    _GUI_LOCK = handle
    return True

def release_gui_single_instance():
    """Kilit dosyasını bırakır; yeniden başlatmada yeni örneğin açılmasını sağlar."""
    global _GUI_LOCK
    if _GUI_LOCK is not None:
        try:
            _GUI_LOCK.close()
        except Exception:
            pass
        _GUI_LOCK = None

def main():
    user_settings = load_settings()
    set_language(user_settings.get("language", "tr"))
    app = QApplication(sys.argv)
    theme.apply_theme(app, user_settings.get("theme", "dark"))
    if not acquire_gui_single_instance():
        QMessageBox.warning(None, "MacroStat", T("MacroStat zaten çalışıyor. Mevcut pencereyi kullanın."))
        sys.exit(0)
    app.aboutToQuit.connect(cleanup_daemon)
    window = MacroStatApp()
    window.show()
    exit_code = app.exec()
    common.cleanup_daemon()
    sys.exit(exit_code)
