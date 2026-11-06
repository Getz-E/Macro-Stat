# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""MacroStat ortak sabitler, yol çözümleme, günlük ve motor süreç yardımcıları."""

import sys
import os
import stat
import json
import re
import time
import subprocess
import shutil
import atexit
import signal
from pathlib import Path

from macrostat.i18n import T, LANGUAGES, get_language, set_language
from macrostat.settings import CONFIG_DIR, load_settings, save_settings
from macrostat.sanitize import coerce_int, sanitize_display_text  # noqa: F401

DAEMON_PROC = None
LOG_MAX_BYTES = 1_000_000

def _runtime_dir(base=None):
    """Kilit/pid/günlük dosyaları için yalnızca sahibine ait özel dizin.

    ``XDG_RUNTIME_DIR`` yalnızca gerçekten özel ise (başka kullanıcı veya grup
    yazamıyorsa) kullanılır. Aksi halde dünyaya açık ``/tmp`` yerine kullanıcı
    önbelleğindeki 0700 dizine düşülür; sabit adlı dosyalar ele geçirilemez.
    """
    if base is None:
        base = os.environ.get("XDG_RUNTIME_DIR")
    if base:
        candidate = Path(base)
        try:
            info = candidate.stat()
            if (candidate.is_dir() and info.st_uid == os.getuid()
                    and not stat.S_IMODE(info.st_mode) & 0o022):
                return candidate
        except OSError:
            pass
    fallback = Path.home() / ".cache" / "macrostat"
    try:
        fallback.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(fallback, 0o700)
    except OSError:
        pass
    return fallback

RUNTIME_DIR = _runtime_dir()
PID_FILE = RUNTIME_DIR / f"macrostat-{os.getuid()}.pid"

#: Tetikleyici tek parçası: KEY_* / BTN_* adları (motorun kabul ettiği biçim).
_TRIGGER_PART_RE = re.compile(r"^(?:KEY_[A-Z0-9_]+|BTN_[A-Z0-9_]+)$")

#: STOP sonrası motoru yeniden başlatan izleyicinin beklediği varsayılan tuş.
DEFAULT_RESTART_KEY = "KEY_F12"
#: `--watch-restart` sürecinin tuşa basılınca döndüğü çıkış kodu (motorla aynı).
RESTART_WATCH_EXIT_CODE = 42
_RESTART_KEY_RE = re.compile(r"^KEY_[A-Z0-9_]+$")

def normalize_restart_key(value):
    """Yeniden başlatma tuşunu doğrular; geçersizse güvenli varsayılana döner."""
    if isinstance(value, str):
        candidate = value.strip().upper()
        if _RESTART_KEY_RE.match(candidate):
            return candidate
    return DEFAULT_RESTART_KEY

def restart_watch_command(daemon_bin, key):
    """STOP sonrası tuş dinleyicisinin komut satırı."""
    return [str(daemon_bin), "--watch-restart", normalize_restart_key(key)]

def is_valid_trigger(value):
    """'KEY_A+KEY_LEFTCTRL' veya 'BTN_LEFT' gibi tetikleyicileri doğrular."""
    if not isinstance(value, str):
        return False
    parts = [p.strip() for p in value.split("+")]
    return bool(parts) and all(p and _TRIGGER_PART_RE.match(p.upper()) for p in parts)

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
    return pid if target.name == "macrostat-daemon" else None

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

def write_private_bytes(path, data):
    """Dosyayı 0600 izinle, sembolik bağlantı izlemeden atomik olmayan yazma."""
    flags = (os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_CLOEXEC
             | getattr(os, "O_NOFOLLOW", 0))
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, data)
    finally:
        os.close(fd)


def _open_private_log_append(path):
    """Günlüğü sembolik bağlantı izlemeden, 0600 izinle ekleme modunda açar."""
    flags = (os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_CLOEXEC
             | getattr(os, "O_NOFOLLOW", 0))
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
    except OSError:
        pass
    return os.fdopen(fd, "a", encoding="utf-8")


def open_rotated_log():
    """Günlük dosyası sınırsız büyümesin diye 1 MB üzerinde döndürülür."""
    try:
        if (LOG_FILE.exists() and not LOG_FILE.is_symlink()
                and LOG_FILE.stat().st_size > LOG_MAX_BYTES):
            backup = LOG_FILE.with_name(LOG_FILE.name + ".1")
            try:
                backup.unlink()
            except FileNotFoundError:
                pass
            LOG_FILE.rename(backup)
    except Exception:
        pass
    return _open_private_log_append(LOG_FILE)

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
        QFrame, QInputDialog, QFileDialog, QToolButton, QMenu, QCheckBox,
        QListWidget, QListWidgetItem, QScrollArea
    )
    from PyQt6.QtCore import (
        Qt, QTimer, QProcess, pyqtSignal, QRectF, QPropertyAnimation, pyqtProperty,
        QEvent,
    )
    from PyQt6.QtGui import QFont, QColor, QPainter, QBrush, QPen, QIcon
except ImportError:
    print(T("[HATA] PyQt6 kütüphanesi eksik!"))
    print(T("Kurulum için: dağıtımınıza uygun install_ubuntu.sh / install_debian.sh / "
            "install_fedora.sh / install_arch.sh betiğini çalıştırın."))
    sys.exit(1)

# Sabit yollar
SCRIPT_DIR = Path(__file__).resolve().parent.parent
#: Günlük, özel çalışma dizininde tutulur (sabit adlı `/tmp` dosyası yok).
LOG_FILE = RUNTIME_DIR / "macrostat.log"
PANIC_KEY = "KEY_PAUSE"
UDEV_RULE_PATH = Path("/etc/udev/rules.d/99-macrostat.rules")
#: Geniş `chmod 666` veya `input` grubu yerine yalnızca oturum sahibine
#: (`uaccess`) yazma izni veren dar kural.
UDEV_RULE_CONTENT = (
    'KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", '
    'OPTIONS+="static_node=uinput", MODE="0660"\n'
    'SUBSYSTEM=="input", KERNEL=="event*", TAG+="uaccess", MODE="0660"\n'
)

def udev_rule_installed():
    """Dar kapsamlı udev kuralı kurulu ve beklenen izinleri içeriyor mu?

    Eski geniş kurallar (`GROUP="input"`) güncel sayılmaz; kullanıcı yeniden
    kurulum yapmaya yönlendirilir.
    """
    try:
        text = UDEV_RULE_PATH.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return ('KERNEL=="uinput"' in text and 'TAG+="uaccess"' in text
            and 'MODE="0660"' in text and 'SUBSYSTEM=="input"' in text
            and "GROUP=" not in text)


def install_udev_rule():
    """udev kuralını pkexec/sudo ile kurar. (başarılı, ayrıntı) döndürür.

    Betik tamamen sabittir; kullanıcı adı veya başka bir dış değer gömülmez.
    """
    script = (
        "modprobe uinput 2>/dev/null || true\n"
        "cat > {} <<'EOF'\n{}EOF\n"
        "udevadm control --reload-rules\n"
        "udevadm trigger\n"
    ).format(UDEV_RULE_PATH, UDEV_RULE_CONTENT)
    elevated = ["pkexec", "sh", "-c", script] if shutil.which("pkexec") \
        else ["sudo", "sh", "-c", script]
    try:
        result = subprocess.run(elevated)
    except OSError as exc:
        return False, str(exc)
    if result.returncode != 0:
        return False, "exit {}".format(result.returncode)
    return True, ""

def _default_profile_path():
    """Tek kanonik profil şablonu; eski kök konum yalnızca yedektir."""
    for candidate in (SCRIPT_DIR / "assets" / "default_profile.json",
                      SCRIPT_DIR / "profile.json"):
        if candidate.exists():
            return candidate
    return SCRIPT_DIR / "profile.json"

DEFAULT_PROFILE_PATH = _default_profile_path()

def _seed_profile_bytes():
    """Şablonu aktif dile göre üretir (yalnızca görünen ad/açıklama çevrilir)."""
    raw = DEFAULT_PROFILE_PATH.read_text(encoding="utf-8")
    if get_language() != "en":
        return raw.encode("utf-8")
    try:
        data = json.loads(raw)
        for profile in data.get("profiles", []):
            for field in ("name", "description"):
                if isinstance(profile.get(field), str):
                    profile[field] = T(profile[field])
            for macro in profile.get("macros", []):
                for field in ("name", "description"):
                    if isinstance(macro.get(field), str):
                        macro[field] = T(macro[field])
        return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    except Exception:
        return raw.encode("utf-8")


def _daemon_candidates():
    """Motor ikilisi için sabit, PATH'ten bağımsız aday listesi.

    ``shutil.which`` kullanılmaz: PATH ele geçirilirse arayüz rastgele bir
    çalıştırılabiliri motor sanıp başlatabilirdi.
    """
    return [
        SCRIPT_DIR / "macrostat-daemon",
        SCRIPT_DIR / "target" / "release" / "macrostat-daemon",
        Path.home() / ".cargo" / "bin" / "macrostat-daemon",
        Path("/usr/local/bin/macrostat-daemon"),
        Path("/usr/bin/macrostat-daemon"),
    ]


def locate_paths():
    """Tek kanonik ikili ve kullanıcı profil yolu. İlk açılışta depo profili tohumlanır."""
    daemon_bin = None
    for p in _daemon_candidates():
        if p.exists() and p.is_file():
            # Yalnızca depo içindeki derleme çıktısına dokun; sistem ikililerine değil.
            if SCRIPT_DIR in p.parents:
                try:
                    os.chmod(p, 0o755)
                except Exception:
                    pass
            daemon_bin = p
            break

    profile_path = CONFIG_DIR / "profile.json"
    if not profile_path.exists():
        try:
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            if DEFAULT_PROFILE_PATH.exists():
                write_private_bytes(profile_path, _seed_profile_bytes())
        except OSError as e:
            print(f"[UYARI] Profil tohumlanamadı: {e}")

    return daemon_bin, profile_path

# Tohumlama dile duyarlı olsun: arayüz main() çalışmadan önce de ayarı uygula.
set_language(load_settings().get("language", get_language()))

DAEMON_BIN, PROFILE_PATH = locate_paths()
