# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Makro/profil içe ve dışa aktarma — GUI'den bağımsız saf yardımcılar.

Kurallar:
- Dışa aktarma atomiktir (geçici dosya + ``os.replace``).
- İçe aktarma hiçbir mevcut veriyi ezmez; kimlikler yenilenir.
- Bozuk dosya/şema ``TransferError`` ile tek satırlık mesaj üretir.
"""

import copy
import json
import os
import tempfile
import time
from pathlib import Path

from .sanitize import (
    BTN_PART_RE,
    ID_RE,
    KEY_PART_RE,
    TRIGGER_MODES,
    is_valid_trigger,
    sanitize_display_text,
)

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_MACROS = 500
MAX_PROFILES = 100
MAX_TEXT_BYTES = 64 * 1024

#: İçe aktarılan makro/profil kimlikleri: yalnızca harf, rakam, '_' ve '-'.
#: Kimlikler motora komut satırında geçebilir; kontrol/bidi karakter kabul edilmez.

_PROFILE_FIELDS = (
    "id", "name", "description", "panicKey", "restartKey", "virtualDeviceName",
    "defaultJitterMs", "macros",
)
_MACRO_FIELDS = (
    "id", "name", "description", "enabled", "triggerKey", "triggerMode",
    "repeatCount", "doubleTapTimeoutMs", "holdDurationMs", "actions",
    "releaseActions", "createdAt", "updatedAt",
)


class TransferError(Exception):
    """Kullanıcıya gösterilebilir, tek satırlık aktarma hatası."""


def _one_line(message):
    return " ".join(str(message).split())


def _text_ok(value):
    if not isinstance(value, str):
        return False
    try:
        return len(value.encode("utf-8")) <= MAX_TEXT_BYTES
    except UnicodeEncodeError:
        return False


def is_text_within_limits(value, multiline=False):
    """TEXT eylemi metni motorun bayt sınırına sığıyor mu?"""
    return _text_ok(value)


def _as_int(value, default, low=None, high=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if low is not None and number < low:
        return default
    if high is not None and number > high:
        return default
    return number


def _sanitize_action(raw, warnings):
    if not isinstance(raw, dict):
        warnings.append(T_("Geçersiz eylem atlandı."))
        return None
    act = copy.deepcopy(raw)
    a_type = act.get("type")
    if not isinstance(a_type, str):
        warnings.append(T_("Türü olmayan eylem atlandı."))
        return None

    if a_type in ("KEY_TAP", "KEY_DOWN", "KEY_UP"):
        key = act.get("key")
        if not isinstance(key, str) or not KEY_PART_RE.match(key):
            warnings.append(T_("Geçersiz tuş eylemi atlandı: {}").format(a_type))
            return None
        result = {"type": a_type, "key": key}
        if a_type == "KEY_TAP":
            result["delayMs"] = _as_int(act.get("delayMs"), 20, 1, 10000)
    elif a_type in ("MOUSE_CLICK", "MOUSE_DOWN", "MOUSE_UP"):
        button = act.get("mouseButton", "BTN_LEFT")
        if not isinstance(button, str) or not BTN_PART_RE.match(button):
            button = "BTN_LEFT"
        result = {"type": a_type, "mouseButton": button}
        if a_type == "MOUSE_CLICK":
            result["delayMs"] = _as_int(act.get("delayMs"), 15, 1, 10000)
    elif a_type == "DELAY":
        result = {
            "type": "DELAY",
            "delayMs": _as_int(act.get("delayMs"), 50, 1, 60000),
            "jitterMs": _as_int(act.get("jitterMs"), 2, 0, 1000),
        }
    elif a_type == "TEXT":
        text = act.get("text", "")
        if not _text_ok(text):
            warnings.append(T_("Çok uzun metin eylemi atlandı."))
            return None
        result = {"type": "TEXT", "text": text}
    elif a_type == "MOUSE_MOVE":
        result = {
            "type": "MOUSE_MOVE",
            "dx": _as_int(act.get("dx"), 0, -5000, 5000),
            "dy": _as_int(act.get("dy"), 0, -5000, 5000),
        }
    elif a_type == "MOUSE_SCROLL":
        result = {
            "type": "MOUSE_SCROLL",
            "scrollDelta": -1 if _as_int(act.get("scrollDelta"), 1) < 0 else 1,
        }
    elif a_type == "MOUSE_PATH":
        points = act.get("points")
        if not isinstance(points, list):
            warnings.append(T_("Geçersiz fare yolu eylemi atlandı."))
            return None
        clean = []
        for point in points:
            if isinstance(point, (list, tuple)) and len(point) == 3:
                clean.append([
                    _as_int(point[0], 0, 0, 60000),
                    _as_int(point[1], 0),
                    _as_int(point[2], 0),
                ])
        if not clean:
            warnings.append(T_("Boş fare yolu eylemi atlandı."))
            return None
        result = {"type": "MOUSE_PATH", "points": clean}
    else:
        warnings.append(T_("Bilinmeyen eylem türü atlandı: {}").format(a_type))
        return None

    if isinstance(raw.get("id"), str) and raw["id"]:
        result["id"] = raw["id"]
    return result


def _sanitize_macro(raw, warnings, used_ids, id_prefix):
    if not isinstance(raw, dict):
        warnings.append(T_("Geçersiz makro atlandı."))
        return None
    if not isinstance(raw.get("actions"), list) and not isinstance(raw.get("triggerKey"), str):
        warnings.append(T_("Makro olmayan öğe atlandı."))
        return None

    macro = {key: copy.deepcopy(raw[key]) for key in _MACRO_FIELDS if key in raw}

    macro_id = macro.get("id")
    if (not isinstance(macro_id, str) or not ID_RE.match(macro_id)
            or macro_id in used_ids):
        macro_id = "macro-{}".format(time.time_ns() // 1_000_000)
        suffix = 1
        while macro_id in used_ids:
            macro_id = "macro-{}-{}".format(time.time_ns() // 1_000_000, suffix)
            suffix += 1
    used_ids.add(macro_id)
    macro["id"] = macro_id

    name = macro.get("name")
    name = sanitize_display_text(name, max_len=200) if isinstance(name, str) else ""
    macro["name"] = name if name.strip() else T_("İçe Aktarılan Makro")
    if isinstance(macro.get("description"), str) and _text_ok(macro["description"]):
        macro["description"] = sanitize_display_text(
            macro["description"], multiline=True, max_len=4000)
    else:
        macro.pop("description", None)

    trigger = macro.get("triggerKey")
    if not isinstance(trigger, str) or not _valid_combo(trigger):
        macro["triggerKey"] = ""
        if trigger not in (None, ""):
            warnings.append(T_("Geçersiz tetikleyici boşaltıldı."))

    mode = macro.get("triggerMode")
    macro["triggerMode"] = (
        mode if isinstance(mode, str) and mode in TRIGGER_MODES else "ONCE")
    macro["repeatCount"] = _as_int(macro.get("repeatCount"), 1, 1, 9999)
    if "doubleTapTimeoutMs" in raw:
        macro["doubleTapTimeoutMs"] = _as_int(raw.get("doubleTapTimeoutMs"), 300, 50, 5000)
    if "holdDurationMs" in raw:
        macro["holdDurationMs"] = _as_int(raw.get("holdDurationMs"), 300, 50, 10000)

    # Güvenlik: içe aktarılan makrolar kullanıcı onaylayana dek kapalıdır.
    macro["enabled"] = False

    for list_name, prefix in (("actions", "act"), ("releaseActions", "rel")):
        clean = []
        values = raw.get(list_name)
        if not isinstance(values, list):
            values = []
        for index, action in enumerate(values):
            if len(clean) >= MAX_MACROS * 20:
                warnings.append(T_("Eylem sınırı aşıldı; kalanlar atlandı."))
                break
            sanitized = _sanitize_action(action, warnings)
            if sanitized is None:
                continue
            sanitized["id"] = "{}--{}-{}".format(id_prefix, prefix, index)
            clean.append(sanitized)
        macro[list_name] = clean

    return macro


def _sanitize_profile(raw, warnings, used_profile_ids, used_macro_ids, id_prefix):
    if not isinstance(raw, dict):
        warnings.append(T_("Geçersiz profil atlandı."))
        return None
    profile = {key: copy.deepcopy(raw[key]) for key in _PROFILE_FIELDS if key in raw}

    profile_id = profile.get("id")
    if (not isinstance(profile_id, str) or not ID_RE.match(profile_id)
            or profile_id in used_profile_ids):
        profile_id = "profile-{}".format(time.time_ns() // 1_000_000)
        suffix = 1
        while profile_id in used_profile_ids:
            profile_id = "profile-{}-{}".format(time.time_ns() // 1_000_000, suffix)
            suffix += 1
    used_profile_ids.add(profile_id)
    profile["id"] = profile_id

    name = profile.get("name")
    name = sanitize_display_text(name, max_len=200) if isinstance(name, str) else ""
    profile["name"] = name if name.strip() else T_("İçe Aktarılan Profil")
    if isinstance(profile.get("description"), str) and _text_ok(profile["description"]):
        profile["description"] = sanitize_display_text(
            profile["description"], multiline=True, max_len=4000)
    else:
        profile.pop("description", None)

    panic = profile.get("panicKey")
    if not isinstance(panic, str) or not KEY_PART_RE.match(panic):
        profile.pop("panicKey", None)
    restart = profile.get("restartKey")
    if not isinstance(restart, str) or not KEY_PART_RE.match(restart):
        profile.pop("restartKey", None)
    device = profile.get("virtualDeviceName")
    if _text_ok(device) and sanitize_display_text(device, max_len=80).strip():
        profile["virtualDeviceName"] = sanitize_display_text(device, max_len=80)
    else:
        profile.pop("virtualDeviceName", None)
    profile["defaultJitterMs"] = _as_int(profile.get("defaultJitterMs"), 2, 0, 1000)

    macros = []
    raw_macros = raw.get("macros")
    if not isinstance(raw_macros, list):
        raw_macros = []
    for macro in raw_macros:
        if len(macros) >= MAX_MACROS:
            warnings.append(T_("Makro sınırı aşıldı; kalanlar atlandı."))
            break
        sanitized = _sanitize_macro(macro, warnings, used_macro_ids, id_prefix)
        if sanitized is not None:
            macros.append(sanitized)
    profile["macros"] = macros
    return profile


def _valid_combo(value):
    if not isinstance(value, str) or not value:
        return False
    return 1 <= len(value.split("+")) <= 3 and is_valid_trigger(value)


def _looks_like_profile(data):
    return isinstance(data, dict) and (
        "panicKey" in data or "virtualDeviceName" in data or "defaultJitterMs" in data
    )


def import_payload(data, existing_macro_ids=(), existing_profile_ids=()):
    """Dosya içeriğini doğrular ve eklenecek makro/profil listelerini döndürür."""
    warnings = []
    used_macro_ids = set(existing_macro_ids)
    used_profile_ids = set(existing_profile_ids)
    prefix = "imp{}".format(time.time_ns() // 1_000_000)

    profiles = []
    macros = []

    if isinstance(data, dict) and isinstance(data.get("profiles"), list):
        for index, profile in enumerate(data["profiles"]):
            if len(profiles) >= MAX_PROFILES:
                warnings.append(T_("Profil sınırı aşıldı; kalanlar atlandı."))
                break
            sanitized = _sanitize_profile(
                profile, warnings, used_profile_ids, used_macro_ids,
                "{}p{}".format(prefix, index))
            if sanitized is not None:
                profiles.append(sanitized)
    elif isinstance(data, list):
        for index, macro in enumerate(data):
            if len(macros) >= MAX_MACROS:
                warnings.append(T_("Makro sınırı aşıldı; kalanlar atlandı."))
                break
            sanitized = _sanitize_macro(
                macro, warnings, used_macro_ids, "{}m{}".format(prefix, index))
            if sanitized is not None:
                macros.append(sanitized)
    elif isinstance(data, dict) and _looks_like_profile(data):
        sanitized = _sanitize_profile(
            data, warnings, used_profile_ids, used_macro_ids, prefix + "p0")
        if sanitized is not None:
            profiles.append(sanitized)
    elif isinstance(data, dict) and isinstance(data.get("macros"), list):
        for index, macro in enumerate(data["macros"]):
            if len(macros) >= MAX_MACROS:
                warnings.append(T_("Makro sınırı aşıldı; kalanlar atlandı."))
                break
            sanitized = _sanitize_macro(
                macro, warnings, used_macro_ids, "{}m{}".format(prefix, index))
            if sanitized is not None:
                macros.append(sanitized)
    elif isinstance(data, dict):
        sanitized = _sanitize_macro(data, warnings, used_macro_ids, prefix + "m0")
        if sanitized is not None:
            macros.append(sanitized)

    if not profiles and not macros:
        raise TransferError(_one_line(
            T_("Dosyada içe aktarılabilir makro veya profil bulunamadı.")))
    return {"macros": macros, "profiles": profiles, "warnings": warnings}


def load_payload(path):
    """JSON dosyasını boyut sınırıyla okur ve ayrıştırır."""
    try:
        file_path = Path(path)
        if file_path.stat().st_size > MAX_FILE_BYTES:
            raise TransferError(_one_line(
                T_("Dosya çok büyük (en fazla 5 MB).")))
        raw = file_path.read_bytes()
    except TransferError:
        raise
    except OSError as exc:
        raise TransferError(_one_line(T_("Dosya okunamadı: {}").format(exc)))
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TransferError(_one_line(T_("Geçersiz JSON: {}").format(exc)))


def export_profiles(profiles, path, active_profile_id=""):
    """Profilleri tek bir JSON paketine atomik olarak yazar."""
    if not isinstance(profiles, list) or not profiles:
        raise TransferError(_one_line(T_("Dışa aktarılacak profil seçilmedi.")))
    payload = {
        "schemaVersion": 1,
        "exportedBy": "MacroStat",
        "exportedAt": int(time.time() * 1000),
    }
    if active_profile_id:
        payload["activeProfileId"] = active_profile_id
    payload["profiles"] = copy.deepcopy(profiles)

    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".macrostat-export-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    except OSError as exc:
        raise TransferError(_one_line(T_("Dışa aktarma başarısız: {}").format(exc)))
    return target


def unique_name(name, used_names):
    """'(2)', '(3)' … ekleriyle çakışmayan bir ad üretir."""
    candidate = name or T_("Profil")
    if candidate not in used_names:
        return candidate
    counter = 2
    while "{} ({})".format(candidate, counter) in used_names:
        counter += 1
    return "{} ({})".format(candidate, counter)


# i18n bağımlılığını döngüye sokmamak için tembel çeviri.
def T_(text):
    from .i18n import T
    return T(text)
