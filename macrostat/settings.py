# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Kullanıcı ayarları (dil) için kalıcı, atomik depolama."""

import json
import os
import tempfile
from pathlib import Path

SETTINGS_PATH = Path.home() / ".config" / "cachymacro" / "settings.json"


def _detect_language():
    value = (os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES")
             or os.environ.get("LANG") or "").lower()
    return "en" if value.startswith("en") else "tr"


def load_settings():
    """Ayarları okur; eksik/bozuk dosyada güvenli varsayılan döndürür."""
    defaults = {"language": _detect_language()}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            if data.get("language") not in ("tr", "en"):
                data["language"] = defaults["language"]
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
