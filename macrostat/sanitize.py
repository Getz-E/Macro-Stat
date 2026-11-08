# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""GUI'den bağımsız metin/sayı temizleme yardımcıları.

Profil dosyaları ve içe aktarılan JSON kullanıcı denetimindedir; görünen
alanlar Qt zengin metin yorumlamasına veya terminal kaçış dizilerine yol
açmamalıdır. Bu modül yalnızca standart kütüphane kullanır.
"""

import re

#: Profil/makro/eylem kimlikleri: yalnızca harf, rakam, '_' ve '-'.
#: Kimlikler motora komut satırında geçebilir; kontrol/bidi karakter kabul edilmez.
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

#: Tetikleyici/STOP tuşu parçaları (motorun kabul ettiği biçim).
KEY_PART_RE = re.compile(r"^KEY_[A-Z0-9_]+$")
BTN_PART_RE = re.compile(r"^BTN_[A-Z0-9_]+$")
TRIGGER_PART_RE = re.compile(r"^(?:KEY_[A-Z0-9_]+|BTN_[A-Z0-9_]+)$")
#: Motorun ``string_to_key`` ile çözdüğü ``KEY_`` öneksiz düz adlar
#: (``F9``, ``PAUSE``, ``123``). Boşluk/denetim karakteri içermez.
PLAIN_KEY_RE = re.compile(r"^[A-Za-z0-9_]{1,32}$")

#: Motorun serde enum'uyla aynı büyük harfli tetikleme kipleri.
TRIGGER_MODES = frozenset({
    "ONCE", "WHILE_HELD", "TOGGLE_LOOP", "REPEAT_COUNT", "DOUBLE_TAP",
    "HOLD_LONG_PRESS", "PRESS_AND_RELEASE",
})

#: C0/C1 denetim karakterleri (satır sonu ve satır başı hariç).
_CONTROL_RE = re.compile(r"[\x00-\x08\t\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def is_valid_id(value):
    """Yalnızca güvenli kimlik karakterlerinden oluşan 1-64 karakter mi?"""
    return isinstance(value, str) and bool(ID_RE.match(value))


def is_valid_key_name(value, allow_button=True):
    """Tek bir KEY_*/BTN_* adı mı?"""
    if not isinstance(value, str):
        return False
    pattern = TRIGGER_PART_RE if allow_button else KEY_PART_RE
    return bool(pattern.match(value))


def is_plain_key_name(value):
    """Motorun öneksiz tuş adı biçiminde mi (``F9``, ``PAUSE``, ``123``)?"""
    return isinstance(value, str) and bool(PLAIN_KEY_RE.match(value))


def is_valid_trigger(value):
    """'KEY_A' veya 'KEY_LEFTCTRL+KEY_A' gibi tetikleyici mi?

    Parçalar boşluklardan arındırılır; ardışık '+' veya boş parça kabul
    edilmez. Motor da aynı biçimi (büyük/küçük harf duyarsız) ayrıştırır.
    """
    if not isinstance(value, str):
        return False
    parts = [p.strip() for p in value.split("+")]
    return bool(parts) and all(p and TRIGGER_PART_RE.match(p.upper())
                               for p in parts)

#: Görünmez bidi/yönlendirme ve zero-width karakterleri: görünen adlarda
#: görsel aldatmacaya (sahte uzantı, ters yazım) yol açabilirler.
_INVISIBLE_RE = re.compile(
    r"[\u061c\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u206f\ufeff]")


def sanitize_display_text(value, single_line=False, multiline=False, max_len=512):
    """Görünen metinden denetim karakterlerini ve HTML açılarını temizler.

    ``single_line`` (varsayılan) tüm boşlukları tek boşluğa indirger;
    ``multiline`` satır sonlarını korur. Sonuç ``max_len`` karakterle sınırlıdır.
    """
    if not isinstance(value, str):
        return ""
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_RE.sub("", text)
    text = _INVISIBLE_RE.sub("", text)
    text = text.replace("<", "").replace(">", "")
    if multiline and not single_line:
        text = "\n".join(line.strip() for line in text.split("\n"))
    else:
        text = " ".join(text.split())
    if max_len is not None and len(text) > max_len:
        text = text[:max_len]
    return text


def coerce_int(value, default, low=None, high=None):
    """Sayısal alanı güvenle tamsayıya çevirir; geçersizse varsayılana döner."""
    if isinstance(value, bool) or value is None:
        return _clamp(default, low, high)
    if isinstance(value, str):
        try:
            value = int(value.strip())
        except ValueError:
            return _clamp(default, low, high)
    elif not isinstance(value, int):
        return _clamp(default, low, high)
    return _clamp(value, low, high)


def _clamp(value, low, high):
    if low is not None and value < low:
        value = low
    if high is not None and value > high:
        value = high
    return value
