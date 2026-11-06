# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""GUI'den bağımsız metin/sayı temizleme yardımcıları.

Profil dosyaları ve içe aktarılan JSON kullanıcı denetimindedir; görünen
alanlar Qt zengin metin yorumlamasına veya terminal kaçış dizilerine yol
açmamalıdır. Bu modül yalnızca standart kütüphane kullanır.
"""

import re

#: C0/C1 denetim karakterleri (satır sonu ve satır başı hariç).
_CONTROL_RE = re.compile(r"[\x00-\x08\t\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def sanitize_display_text(value, single_line=False, multiline=False, max_len=512):
    """Görünen metinden denetim karakterlerini ve HTML açılarını temizler.

    ``single_line`` (varsayılan) tüm boşlukları tek boşluğa indirger;
    ``multiline`` satır sonlarını korur. Sonuç ``max_len`` karakterle sınırlıdır.
    """
    if not isinstance(value, str):
        return ""
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_RE.sub("", text)
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
