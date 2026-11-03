# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""MacroStat ortak sabitler, yol çözümleme, günlük ve motor süreç yardımcıları."""

import sys
import os
import json
import time
import subprocess
import shutil
import atexit
import signal
import fcntl
import copy
from pathlib import Path

from macrostat.i18n import T, LANGUAGES, get_language, set_language
from macrostat.settings import load_settings, save_settings

DAEMON_PROC = None
LOG_MAX_BYTES = 1_000_000
PID_FILE = Path(f"/tmp/cachymacro-{os.getuid()}.pid")

def _pid_file_pid():
    """Pidfile'daki sürecin gerçekten MacroStat motoru olduğunu doğrular."""
    try:
        pid = int(PID_FILE.read_text().strip())
    except Exception:
        return None
    try:
        target = Path(f"/proc/{pid}/exe").resolve()
    except Exception:
        return None
    return pid if target.name == "cachymacro-daemon" else None

def _process_alive(pid):
    """Süreç yaşıyor mu? Zombi (henüz reap edilmemiş) süreç ölü sayılır."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    try:
        # comm alanı parantez içinde boşluk barındırabilir; son ')' sonrası state gelir.
        state = stat.rsplit(")", 1)[1].split()[0]
    except Exception:
        return True
    return state != "Z"

def _terminate_daemon_pid(pid, timeout=1.5):
    """Önce SIGTERM ile temiz kapanış ister, süre dolarsa SIGKILL uygular."""
    if pid is None:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception:
        return
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _process_alive(pid):
            return
        time.sleep(0.02)
    try:
        os.kill(pid, signal.SIGKILL)
    except Exception:
        pass

def cleanup_daemon():
    global DAEMON_PROC
    if DAEMON_PROC is not None:
        try:
            _terminate_daemon_pid(DAEMON_PROC.pid)
            DAEMON_PROC.wait(timeout=0.5)
        except Exception:
            try:
                DAEMON_PROC.kill()
            except Exception:
                pass
        DAEMON_PROC = None
    else:
        _terminate_daemon_pid(_pid_file_pid())
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass

def open_rotated_log():
    """Günlük dosyası sınırsız büyümesin diye 1 MB üzerinde döndürülür."""
    try:
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_BYTES:
            backup = LOG_FILE.with_name(LOG_FILE.name + ".1")
            try:
                backup.unlink()
            except FileNotFoundError:
                pass
            LOG_FILE.rename(backup)
    except Exception:
        pass
    return open(LOG_FILE, "a", encoding="utf-8")

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
        QFrame, QInputDialog, QFileDialog, QToolButton, QMenu
    )
    from PyQt6.QtCore import (
        Qt, QTimer, QProcess, pyqtSignal, QRectF, QPropertyAnimation, pyqtProperty,
    )
    from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QIcon
except ImportError:
    print(T("[HATA] PyQt6 kütüphanesi eksik!"))
    print(T("Kurulum için: sudo pacman -S python-pyqt6"))
    sys.exit(1)

# Sabit yollar
SCRIPT_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = Path("/tmp/cachymacro.log")
PANIC_KEY = "KEY_PAUSE"

def _default_profile_path():
    """Tek kanonik profil şablonu; eski kök konum yalnızca yedektir."""
    for candidate in (SCRIPT_DIR / "assets" / "default_profile.json",
                      SCRIPT_DIR / "profile.json"):
        if candidate.exists():
            return candidate
    return SCRIPT_DIR / "profile.json"

DEFAULT_PROFILE_PATH = _default_profile_path()

def locate_paths():
    """Tek kanonik ikili ve kullanıcı profil yolu. İlk açılışta depo profili tohumlanır."""
    candidates_bin = [
        SCRIPT_DIR / "cachymacro-daemon",
        SCRIPT_DIR / "target" / "release" / "cachymacro-daemon",
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

    profile_path = Path.home() / ".config" / "cachymacro" / "profile.json"
    if not profile_path.exists():
        seed = DEFAULT_PROFILE_PATH
        try:
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            if seed.exists():
                shutil.copy2(seed, profile_path)
        except OSError as e:
            print(f"[UYARI] Profil tohumlanamadı: {e}")

    return daemon_bin, profile_path

DAEMON_BIN, PROFILE_PATH = locate_paths()
