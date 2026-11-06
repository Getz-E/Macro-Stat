# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Kullanıcı ayarları (dil) için kalıcı, atomik depolama."""

import json
import os
import tempfile
from pathlib import Path

#: Kullanıcı yapılandırma dizini. 0.x geliştirme sürümleri eski adı
#: (`cachymacro`) kullanıyordu; veri kaybı olmaması için tek seferlik taşınır.
CONFIG_DIR = Path.home() / ".config" / "macrostat"
_LEGACY_CONFIG_DIR = Path.home() / ".config" / "cachymacro"


def _migrate_legacy_config():
    if CONFIG_DIR.exists() or not _LEGACY_CONFIG_DIR.is_dir():
        return
    try:
        CONFIG_DIR.parent.mkdir(parents=True, exist_ok=True)
        os.replace(_LEGACY_CONFIG_DIR, CONFIG_DIR)
    except OSError:
        pass


_migrate_legacy_config()
SETTINGS_PATH = CONFIG_DIR / "settings.json"


def _detect_language():
    value = (os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES")
             or os.environ.get("LANG") or "").lower()
    return "en" if value.startswith("en") else "tr"


THEME_MODES = ("system", "dark", "light")


def load_settings():
    """Ayarları okur; eksik/bozuk dosyada güvenli varsayılan döndürür."""
    defaults = {
        "language": _detect_language(),
        "theme": "dark",
        "onboarding_completed": False,
        "log_panel_visible": False,
    }
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            if data.get("language") not in ("tr", "en"):
                data["language"] = defaults["language"]
            if data.get("theme") not in THEME_MODES:
                data["theme"] = defaults["theme"]
            data.setdefault("onboarding_completed", False)
            data.setdefault("log_panel_visible", False)
            return data
    except Exception:
        pass
    return defaults


def save_settings(settings):
    """Ayarları atomik olarak yazar (geçici dosya + os.replace)."""
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(SETTINGS_PATH.parent), prefix=".settings-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, SETTINGS_PATH)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
