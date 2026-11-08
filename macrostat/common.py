# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""MacroStat ortak sabitler, yol çözümleme, günlük ve motor süreç yardımcıları."""

import sys
import os
import stat
import json
import time
import shlex
import errno
import tempfile
import subprocess
import atexit
import signal
from pathlib import Path

from macrostat.i18n import T, LANGUAGES, get_language, set_language
from macrostat.settings import CONFIG_DIR, load_settings, save_settings
from macrostat.sanitize import (  # noqa: F401
    TRIGGER_MODES,
    coerce_int,
    is_plain_key_name,
    is_valid_id,
    is_valid_key_name,
    is_valid_trigger,
    sanitize_display_text,
)

DAEMON_PROC = None
LOG_MAX_BYTES = 1_000_000
#: Rust motoruyla aynı profil üst sınırı (32 MiB).
MAX_PROFILE_BYTES = 32 * 1024 * 1024

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

#: STOP sonrası motoru yeniden başlatan izleyicinin beklediği varsayılan tuş.
DEFAULT_RESTART_KEY = "KEY_F12"
#: `--watch-restart` sürecinin tuşa basılınca döndüğü çıkış kodu (motorla aynı).
RESTART_WATCH_EXIT_CODE = 42

def normalize_restart_key(value):
    """Yeniden başlatma tuşunu doğrular; geçersizse güvenli varsayılana döner."""
    if isinstance(value, str):
        candidate = value.strip().upper()
        if is_valid_key_name(candidate, allow_button=False):
            return candidate
    return DEFAULT_RESTART_KEY

def restart_watch_command(daemon_bin, key):
    """STOP sonrası tuş dinleyicisinin komut satırı."""
    return [str(daemon_bin), "--watch-restart", normalize_restart_key(key)]

def _proc_uid(pid):
    """Sürecin etkin kullanıcı kimliği; okunamazsa ``None``."""
    try:
        with open(f"/proc/{pid}/status", "r", encoding="utf-8",
                  errors="ignore") as f:
            for line in f:
                if line.startswith("Uid:"):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None

def _proc_identity(pid):
    """Canlı sürecin yeniden kullanıma dayanıklı kimliği.

    ``starttime`` PID yeniden kullanımını ayırt eder; ``uid`` ve ``exe``
    aynı adı taşıyan yabancı süreçlere sinyal gönderilmesini engeller.
    Zombi süreçler ölü sayılır ve kimlik üretmez.
    """
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    try:
        stat_text = Path(f"/proc/{pid}/stat").read_text(
            encoding="utf-8", errors="ignore")
    except OSError:
        return None
    try:
        # comm alanı parantez içinde boşluk barındırabilir; son ')' sonrası
        # state (alan 3) gelir, starttime ise alan 22'dir (dizin 19).
        fields = stat_text.rsplit(")", 1)[1].split()
        state = fields[0]
        ppid = int(fields[1])
        starttime = int(fields[19])
    except (IndexError, ValueError):
        return None
    if state in ("Z", "X"):
        return None
    uid = _proc_uid(pid)
    if uid is None:
        return None
    try:
        exe = os.readlink(f"/proc/{pid}/exe")
    except OSError:
        return None
    if not exe:
        return None
    return {"pid": pid, "starttime": starttime, "uid": uid, "exe": exe,
            "ppid": ppid}

def _read_pid_identity():
    """Pid dosyasındaki doğrulanmış kimlik kaydı; eski/bozuk kayıt yok sayılır."""
    try:
        data = json.loads(read_private_text_file(PID_FILE, limit=4096))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    pid = data.get("pid")
    starttime = data.get("starttime")
    uid = data.get("uid")
    exe = data.get("exe")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    if (not isinstance(starttime, int) or isinstance(starttime, bool)
            or starttime < 0):
        return None
    if not isinstance(uid, int) or isinstance(uid, bool) or uid < 0:
        return None
    if not isinstance(exe, str) or not exe:
        return None
    return {"pid": pid, "starttime": starttime, "uid": uid, "exe": exe}

def _exe_basename(path):
    """`` (deleted)`` ekini atarak çalıştırılabilir dosya adını döndürür."""
    if not isinstance(path, str):
        return ""
    suffix = " (deleted)"
    if path.endswith(suffix):
        path = path[:-len(suffix)]
    return Path(path).name

def _same_exe_path(actual, expected):
    """Yeniden derlenen (`` (deleted)`` ekli) çalıştırılabilir yolu eşleştirir."""
    if not isinstance(actual, str) or not isinstance(expected, str):
        return False
    suffix = " (deleted)"
    if actual.endswith(suffix):
        actual = actual[:-len(suffix)]
    if expected.endswith(suffix):
        expected = expected[:-len(suffix)]
    return bool(actual) and actual == expected

def _same_process(identity):
    """Kimlik kaydı hâlâ aynı canlı süreci mi gösteriyor?"""
    if not isinstance(identity, dict):
        return False
    current = _proc_identity(identity.get("pid"))
    if current is None:
        return False
    return (current["starttime"] == identity.get("starttime")
            and current["uid"] == identity.get("uid")
            and _same_exe_path(current["exe"], identity.get("exe")))

def _validated_daemon_identity(pid, expected_child=False):
    """Sonlandırılacak sürecin bizim motorumuz olduğunu doğrular.

    Pid dosyasındaki kayıt başka bir PID'yi gösteriyorsa kimlik doğrulaması
    atlanmaz; eşleşmeyen kayıt reddedilir. Kayıt yokken yalnızca çağıranın
    doğrudan alt süreci (``expected_child``) kabul edilir.
    """
    current = _proc_identity(pid)
    if current is None:
        return None
    if current["uid"] != os.geteuid():
        return None
    if _exe_basename(current["exe"]) != "macrostat-daemon":
        return None
    stored = _read_pid_identity()
    if stored is not None:
        if stored["pid"] != pid:
            return None
        if stored["starttime"] != current["starttime"]:
            return None
        if stored["uid"] != current["uid"]:
            return None
        if not _same_exe_path(current["exe"], stored["exe"]):
            return None
        return current
    if expected_child and current["ppid"] == os.getpid():
        return current
    return None

def _pid_file_pid():
    """Pid dosyasındaki sürecin hâlâ doğrulanmış MacroStat motoru olduğunu döndürür."""
    identity = _read_pid_identity()
    if identity is None:
        return None
    if identity["uid"] != os.geteuid():
        return None
    if _exe_basename(identity["exe"]) != "macrostat-daemon":
        return None
    if not _same_process(identity):
        return None
    return identity["pid"]

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

def _terminate_daemon_pid(pid, timeout=1.5, expected_child=False):
    """Kimliği doğrulanmış motora önce SIGTERM, süre dolarsa SIGKILL uygular."""
    if pid is None:
        return
    identity = _validated_daemon_identity(pid, expected_child=expected_child)
    if identity is None:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _same_process(identity):
            return
        time.sleep(0.02)
    # SIGKILL öncesi kimlik yeniden doğrulanır; PID başka sürece geçmiş olabilir.
    if _same_process(identity):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

def cleanup_daemon():
    global DAEMON_PROC
    if DAEMON_PROC is not None:
        # Ölmüş çocuk için eski PID'ye asla sinyal gönderilmez.
        if DAEMON_PROC.poll() is None:
            try:
                _terminate_daemon_pid(DAEMON_PROC.pid, expected_child=True)
                DAEMON_PROC.wait(timeout=0.5)
            except Exception:
                # Popen.kill() kimlik doğrulaması yapmaz; PID yeniden
                # kullanılmış olabileceğinden kör sinyal gönderilmez.
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


def read_private_bytes(path, limit=MAX_PROFILE_BYTES):
    """Normal, sembolik bağlantı olmayan dosyayı en fazla ``limit`` bayt okur.

    Rust motorunun ``read_profile_text`` davranışıyla aynıdır: ``O_NOFOLLOW``
    sembolik bağlantıyı reddeder, yalnızca normal dosya okunur ve boyut
    sınırı aşılırsa hata verilir. Profil yedeği de bu yolu kullanır; böylece
    saldırganın işaret ettiği hedef dosya yedeğe kopyalanmaz.
    """
    flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise OSError(errno.EINVAL, "not a regular file")
        if info.st_size > limit:
            raise OSError(errno.EFBIG, "file too large")
        chunks = []
        total = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise OSError(errno.EFBIG, "file too large")
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def read_private_text_file(path, limit=MAX_PROFILE_BYTES):
    """``read_private_bytes`` sonucunu UTF-8 metne çevirir."""
    return read_private_bytes(path, limit).decode("utf-8")


def atomic_write_private(path, data):
    """0600 geçici dosya + fsync + ``os.replace`` ile atomik özel yazma."""
    path = Path(path)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


def backup_private_file(source, destination):
    """Normal dosyayı sembolik bağlantıyı izlemeden 0600 yedeğe kopyalar."""
    atomic_write_private(destination, read_private_bytes(source))


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

#: Ayrıcalıklı araçlar yalnızca bu sabit, kök sahipli dizinlerde aranır.
#: ``PATH`` hiçbir zaman kullanılmaz.
SYSTEM_BIN_DIRS = (
    Path("/usr/bin"),
    Path("/bin"),
    Path("/usr/sbin"),
    Path("/sbin"),
    Path("/usr/local/bin"),
    Path("/usr/local/sbin"),
)

#: Ubuntu sürümlü Rust paketlerinin kurulum yeri.
VERSIONED_CARGO_PATHS = (Path("/usr/lib/rust-1.79/bin/cargo"),)


#: Linux POSIX ACL genişletilmiş özniteliği.
_POSIX_ACL_XATTR = "system.posix_acl_access"
_ACL_VERSION = 2
_ACL_WRITE = 0x02
_ACL_USER_OBJ = 0x01
_ACL_USER = 0x02
_ACL_GROUP_OBJ = 0x04
_ACL_GROUP = 0x08
_ACL_MASK = 0x10
_ACL_OTHER = 0x20
_ACL_TAGS = frozenset((_ACL_USER_OBJ, _ACL_USER, _ACL_GROUP_OBJ,
                       _ACL_GROUP, _ACL_MASK, _ACL_OTHER))
_MAX_SYMLINK_DEPTH = 40


def _acl_grants_untrusted_write(data, trusted_uids):
    """POSIX ACL verisi güvenilmeyen bir özneye yazma veriyor mu?

    Mod bitleri genişletilmiş ACL'leri yansıtmaz. Adlandırılmış kullanıcı
    veya grup girdisi maskeyle birleşince yazma veriyorsa ve özne güvenilir
    uid listesinde değilse ``True`` döner. Biçim çözümlenemezse güvenli
    taraf seçilir.
    """
    if not isinstance(data, (bytes, bytearray)) or len(data) < 4:
        return True
    if int.from_bytes(data[:4], "little") != _ACL_VERSION:
        return True
    body = bytes(data[4:])
    if not body or len(body) % 8:
        return True
    entries = []
    for offset in range(0, len(body), 8):
        tag = int.from_bytes(body[offset:offset + 2], "little")
        perm = int.from_bytes(body[offset + 2:offset + 4], "little")
        eid = int.from_bytes(body[offset + 4:offset + 8], "little")
        if tag not in _ACL_TAGS or perm & ~0o07:
            return True
        entries.append((tag, perm, eid))
    masks = [perm for tag, perm, _ in entries if tag == _ACL_MASK]
    if len(masks) > 1:
        return True
    has_named = any(tag in (_ACL_USER, _ACL_GROUP)
                    for tag, _, _ in entries)
    if has_named and not masks:
        return True
    mask = masks[0] if masks else 0o07
    for tag, perm, eid in entries:
        if not (perm & mask & _ACL_WRITE):
            continue
        if tag == _ACL_USER and eid in trusted_uids:
            continue
        if tag in (_ACL_USER, _ACL_GROUP, _ACL_OTHER):
            return True
        # Sahip ve grup sahibi girdileri mod bitleriyle ayrıca denetlenir.
    return False


def _path_acl_grants_untrusted_write(path, trusted_uids):
    """Yolun ACL'si güvenilmeyen bir özneye yazma veriyor mu?

    ``system.posix_acl_access`` yoksa veya dosya sistemi POSIX ACL
    desteklemiyorsa yazma izni yoktur. Okunamayan veya çözümlenemeyen
    durumlarda fail-closed davranılır. NFSv4 veya FUSE ACL'leri bu POSIX
    biçiminde görünmeyebilir; bu sınır SECURITY.md içinde belgelenir.
    """
    getxattr = getattr(os, "getxattr", None)
    if getxattr is None:
        return True
    try:
        data = getxattr(path, _POSIX_ACL_XATTR)
    except OSError as exc:
        if exc.errno in (errno.ENODATA, errno.ENOTSUP,
                         errno.EOPNOTSUPP):
            return False
        return True
    return _acl_grants_untrusted_write(data, trusted_uids)


def _stat_component(path):
    """Bir yol bileşeninin stat sonucu; erişilemezse ``None``."""
    try:
        return Path(path).stat()
    except OSError:
        return None


def _chain_directory_is_trusted(info, *, index, parent_uid, ancestor_uids):
    """Zincirdeki bir dizinin sahiplik ve yazma izinleri güvenli mi?

    Doğrudan üst dizinde (``index == 0``) yazma izni kesinlikle yasaktır.
    Daha üst dizinlerde dünya/grup yazılabilirliği yalnızca sticky bit
    (``/tmp`` gibi) varsa kabul edilir; sticky dizinde saldırgan başka
    kullanıcıya ait girişleri yeniden adlandıramaz.
    """
    if info is None or not stat.S_ISDIR(info.st_mode):
        return False
    mode = stat.S_IMODE(info.st_mode)
    if index == 0:
        return info.st_uid == parent_uid and not mode & 0o022
    if info.st_uid not in ancestor_uids:
        return False
    return not mode & 0o022 or bool(mode & stat.S_ISVTX)


def _directory_chain_is_trusted(path, *, parent_uid, ancestor_uids,
                                strict=True):
    """Yolun kendisi ve tüm üst dizinleri güvenli mi?

    ``strict=True`` yolun kendisini çalıştırılabilirin doğrudan üst dizini
    gibi değerlendirir: sticky bit olsa bile yazma izni kabul edilmez.
    ``strict=False`` yolu bir ara dizin gibi değerlendirir; daha üst
    dizinlerde sticky istisnası geçerlidir. Sahiplik ve mod bitlerinin yanı
    sıra genişletilmiş POSIX ACL'leri de denetlenir.
    """
    path = Path(path)
    trusted_uids = set(ancestor_uids) | {parent_uid}
    for index, component in enumerate((path, *path.parents)):
        effective_index = index if strict else index + 1
        if not _chain_directory_is_trusted(
                _stat_component(component), index=effective_index,
                parent_uid=parent_uid, ancestor_uids=ancestor_uids):
            return False
        if _path_acl_grants_untrusted_write(component, trusted_uids):
            return False
    return True


def _resolve_verified_path(path, *, parent_uid, ancestor_uids):
    """Sembolik bağlantıları güvenli biçimde, bileşen bileşen çözer.

    Her symlink'in bulunduğu dizin ve yolun her ara bileşeni doğrulanır;
    saldırganın yazabildiği bir dizindeki ara symlink hedefi saptıramaz.
    Dönen yol tamamen çözümlenmiştir. Güvenilmeyen bileşen, symlink kabı
    veya döngü varsa ``None`` döner.
    """
    path = Path(path)
    if not path.is_absolute():
        return None
    pending = list(path.parts[1:])
    resolved = []
    links = 0
    while pending:
        part = pending.pop(0)
        if part in ("", "."):
            continue
        if part == "..":
            if resolved:
                resolved.pop()
            continue
        candidate = Path("/", *resolved, part)
        if not _directory_chain_is_trusted(
                candidate.parent, parent_uid=parent_uid,
                ancestor_uids=ancestor_uids, strict=False):
            return None
        try:
            info = candidate.lstat()
        except OSError:
            return None
        if stat.S_ISLNK(info.st_mode):
            if not _directory_chain_is_trusted(
                    candidate.parent, parent_uid=parent_uid,
                    ancestor_uids=ancestor_uids, strict=True):
                return None
            links += 1
            if links > _MAX_SYMLINK_DEPTH:
                return None
            try:
                target = os.readlink(candidate)
            except OSError:
                return None
            target_parts = list(Path(target).parts)
            if not target_parts:
                return None
            if Path(target).is_absolute():
                resolved = []
                pending = target_parts[1:] + pending
            else:
                pending = target_parts + pending
            continue
        if pending and not stat.S_ISDIR(info.st_mode):
            return None
        resolved.append(part)
    return Path("/", *resolved)


def _resolved_trusted_executable(path, *, file_uid, parent_uid,
                                 ancestor_uids):
    """Dosyayı ve tüm üst dizin zincirini doğrular; yolu çözer.

    Yalnızca dosyanın kendisi değil, çalıştırma sırasında izlenecek tüm üst
    dizinler ve son symlink'in hedef zincirindeki ara symlink'ler de
    sahiplik, yazma izni ve ACL açısından doğrulanır. Sonuç tamamen
    çözümlenmiş hedef yoludur; ancak hedefin son adı istenen addan farklıysa
    (``/bin/sh`` -> ``bash`` gibi) çağıranın beklediği adı korumak için üst
    dizini çözümlenmiş özgün yol döndürülür. Bu durumda bile zincirdeki
    hiçbir symlink güvenilmeyen bir dizinde değildir.
    """
    candidate = Path(path)
    if not candidate.name:
        return None
    resolved = _resolve_verified_path(
        candidate, parent_uid=parent_uid, ancestor_uids=ancestor_uids)
    exec_parent = _resolve_verified_path(
        candidate.parent, parent_uid=parent_uid, ancestor_uids=ancestor_uids)
    if resolved is None or exec_parent is None:
        return None
    if not _directory_chain_is_trusted(
            exec_parent, parent_uid=parent_uid, ancestor_uids=ancestor_uids,
            strict=True):
        return None
    info = _stat_component(resolved)
    if info is None or not stat.S_ISREG(info.st_mode):
        return None
    if not os.access(resolved, os.X_OK):
        return None
    if info.st_uid != file_uid or stat.S_IMODE(info.st_mode) & 0o022:
        return None
    trusted_uids = set(ancestor_uids) | {file_uid, parent_uid}
    if _path_acl_grants_untrusted_write(resolved, trusted_uids):
        return None
    if resolved.name == candidate.name:
        return resolved
    return exec_parent / candidate.name


def _trusted_root_executable(path):
    """Kök sahipli ve tüm üst dizinleri güvenli çalıştırılabilir yolu."""
    return _resolved_trusted_executable(
        path, file_uid=0, parent_uid=0, ancestor_uids=(0,))


def _trusted_user_executable(path):
    """Geçerli kullanıcıya ait ve üst dizinleri güvenli çalıştırılabilir yolu."""
    uid = os.getuid()
    return _resolved_trusted_executable(
        path, file_uid=uid, parent_uid=uid, ancestor_uids=(0, uid))


def _trusted_daemon_executable(path):
    """Motor ikilisi: kullanıcıya veya köke ait, zinciri güvenli olmalı."""
    executable = _trusted_user_executable(path)
    if executable is not None:
        return executable
    return _trusted_root_executable(path)


def _is_root_controlled(path):
    """Dizin ve tüm üst dizinleri kök sahipli ve yazılamaz mı?"""
    resolved = _resolve_verified_path(
        Path(path), parent_uid=0, ancestor_uids=(0,))
    if resolved is None:
        return False
    return _directory_chain_is_trusted(
        resolved, parent_uid=0, ancestor_uids=(0,))


def _is_trusted_root_binary(path):
    """Kök sahipli, normal, çalıştırılabilir ve yazılamaz dosya mı?"""
    return _trusted_root_executable(path) is not None


def _is_trusted_user_binary(path):
    """Geçerli kullanıcıya ait, üst dizinleri de güvenli çalıştırılabilir mi?"""
    return _trusted_user_executable(path) is not None


def trusted_system_executable(name):
    """Ada göre kök sahipli sistem aracını sabit dizinlerde çözer.

    ``shutil.which``/``PATH`` kullanılmaz: ayrıcalıklı bir araç (sudo,
    pkexec, paket yöneticisi) saldırgan denetimindeki bir dizinden
    çalıştırılmamalıdır. Yalnızca araç dosyası değil, onu içeren dizin ve
    tüm üst dizinler de kök sahipli ve yazılamaz olmalıdır. Sembolik
    bağlantılar hedefleri güvenli olduğu sürece kabul edilir
    (``/bin`` -> ``/usr/bin`` gibi).
    """
    if not name or name in (".", "..") or "/" in name:
        return None
    for directory in SYSTEM_BIN_DIRS:
        if not _is_root_controlled(directory):
            continue
        executable = _trusted_root_executable(directory / name)
        if executable is not None:
            return executable
    return None


def find_cargo():
    """Rust derleyicisini PATH'ten bağımsız, doğrulanmış adaylardan bulur.

    Kullanıcının rustup kurulumu (``$CARGO_HOME/bin`` veya ``~/.cargo/bin``)
    ile dağıtımın kök sahipli paketleri desteklenir; grup/dünya yazılabilir
    dosyalar reddedilir. Kullanıcıya ait ``cargo`` çalıştırmak ayrıcalık
    yükseltmez; yalnızca arayüzle aynı kullanıcı yetkisindedir.
    """
    candidates = []
    cargo_home = os.environ.get("CARGO_HOME")
    if cargo_home and os.path.isabs(cargo_home):
        candidates.append(Path(cargo_home) / "bin" / "cargo")
    try:
        candidates.append(Path.home() / ".cargo" / "bin" / "cargo")
    except RuntimeError:
        pass
    for candidate in candidates:
        executable = _trusted_user_executable(candidate)
        if executable is not None:
            return executable
    for candidate in VERSIONED_CARGO_PATHS:
        executable = _trusted_root_executable(candidate)
        if executable is not None:
            return executable
    return trusted_system_executable("cargo")


def build_udev_install_command():
    """udev kuralını kuran komutu yalnızca güvenilir mutlak yollarla üretir."""
    helper = (trusted_system_executable("pkexec")
              or trusted_system_executable("sudo"))
    shell = trusted_system_executable("sh")
    modprobe = trusted_system_executable("modprobe")
    cat = trusted_system_executable("cat")
    udevadm = trusted_system_executable("udevadm")
    if not all((helper, shell, modprobe, cat, udevadm)):
        return None
    script = (
        "{} uinput 2>/dev/null || true\n"
        "{} > {} <<'EOF'\n{}EOF\n"
        "{} control --reload-rules\n"
        "{} trigger\n"
    ).format(
        shlex.quote(str(modprobe)),
        shlex.quote(str(cat)),
        shlex.quote(str(UDEV_RULE_PATH)),
        UDEV_RULE_CONTENT,
        shlex.quote(str(udevadm)),
        shlex.quote(str(udevadm)),
    )
    return [str(helper), str(shell), "-c", script]


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
    Yükseltilmiş komutun kendisi de yalnızca kök sahipli mutlak yolları
    kullanır; ``PATH`` ele geçirilse bile sahte bir araç çalışmaz.
    """
    command = build_udev_install_command()
    if command is None:
        return False, "trusted privileged helper not found (pkexec/sudo)"
    try:
        result = subprocess.run(command)
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
        # Depo içindeki derleme çıktısı 0644 kalmış olabilir; eski davranışı
        # koru, ancak bir symlink'in hedefini chmod ile değiştirme.
        if SCRIPT_DIR in p.parents:
            try:
                if p.is_file() and not p.is_symlink():
                    os.chmod(p, 0o755)
            except OSError:
                pass
        executable = _trusted_daemon_executable(p)
        if executable is None:
            continue
        daemon_bin = executable
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
