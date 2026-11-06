# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Canlı motor günlüğü paneli: son 5.000 satır, filtre ve renk kodlama."""

import html
from collections import deque

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
    QToolButton, QVBoxLayout, QWidget,
)

from . import theme
from .common import LOG_FILE, LOG_MAX_BYTES, T

#: Panelin tuttuğu en fazla satır sayısı (hem bellek hem görünüm sınırı).
MAX_LOG_LINES = 5000
#: Panel ilk açıldığında dosyanın en fazla bu kadarlık kuyruğu okunur.
#: Günlük dosyası zaten `LOG_MAX_BYTES` ile döndürüldüğü için tümü okunabilir.
INITIAL_READ_BYTES = LOG_MAX_BYTES


def classify_log_line(line):
    """Günlük satırının önem sınıfını döndürür: error/warning/ok/normal."""
    text = line.upper()
    if "[HATA]" in text or "[ERROR]" in text:
        return "error"
    if "[UYARI]" in text or "[WARN]" in text:
        return "warning"
    if any(tag in text for tag in ("[HAZIR]", "[TEST]", "[STOP]", "[READY]")):
        return "ok"
    return "normal"


def filter_lines(lines, query):
    """Büyük/küçük harf duyarsız alt dizgi filtresi; boş sorgu hepsini geçirir."""
    if not query:
        return list(lines)
    needle = query.casefold()
    return [line for line in lines if needle in line.casefold()]


class LogPanel(QWidget):
    """`macrostat.log` dosyasını 500 ms'de bir izleyen salt okunur panel."""

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logPanel")
        self.setMaximumHeight(210)
        self.setMinimumHeight(140)

        self._buffer = deque(maxlen=MAX_LOG_LINES)
        self._offset = 0
        self._inode = None
        self._partial = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 8)
        layout.setSpacing(6)
        layout.addLayout(self._build_toolbar())

        self.view = QPlainTextEdit()
        self.view.setObjectName("logView")
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(MAX_LOG_LINES)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.view.setPlaceholderText(T("Günlük henüz yok."))
        layout.addWidget(self.view, 1)

        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    # -- kurulum ---------------------------------------------------------
    def _build_toolbar(self):
        row = QHBoxLayout()
        row.setSpacing(8)

        title = QLabel(T("Canlı Günlük"))
        title.setObjectName("panelTitle")
        row.addWidget(title)

        self.edit_filter = QLineEdit()
        self.edit_filter.setPlaceholderText(T("Günlükte ara…"))
        self.edit_filter.setClearButtonEnabled(True)
        self.edit_filter.setMaximumWidth(240)
        self.edit_filter.textChanged.connect(self.rebuild_view)
        row.addWidget(self.edit_filter)

        row.addStretch()

        self.chk_follow = QCheckBox(T("Otomatik kaydır"))
        self.chk_follow.setChecked(True)
        row.addWidget(self.chk_follow)

        self.btn_pause = QPushButton(T("Duraklat"))
        self.btn_pause.setCheckable(True)
        self.btn_pause.setProperty("compact", "true")
        self.btn_pause.toggled.connect(self._on_pause_toggled)
        row.addWidget(self.btn_pause)

        self.btn_clear = QPushButton(T("Temizle"))
        self.btn_clear.setProperty("compact", "true")
        self.btn_clear.clicked.connect(self.clear_view)
        row.addWidget(self.btn_clear)

        self.btn_close = QToolButton()
        self.btn_close.setObjectName("iconButton")
        self.btn_close.setText("×")
        self.btn_close.setToolTip(T("Günlük panelini kapat"))
        self.btn_close.clicked.connect(self.closed.emit)
        row.addWidget(self.btn_close)
        return row

    # -- okuma -----------------------------------------------------------
    def poll(self):
        """Yeni satırları okur; dosya döndürülmüş ya da kesilmişse baştan başlar."""
        if self.btn_pause.isChecked():
            return
        try:
            stat = LOG_FILE.stat()
        except OSError:
            return
        rotated = self._inode is not None and stat.st_ino != self._inode
        truncated = stat.st_size < self._offset
        if rotated or truncated:
            self._reset_file()
        self._inode = stat.st_ino
        if stat.st_size <= self._offset:
            return
        initial = self._offset == 0
        start = max(0, stat.st_size - INITIAL_READ_BYTES) if initial else self._offset
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as handle:
                handle.seek(start)
                data = handle.read(stat.st_size - start)
        except OSError:
            return
        self._offset = stat.st_size
        self._consume(data, drop_first_partial=initial and start > 0)

    def refresh_now(self):
        """Panel görünür olduğunda bekletmeden günceller."""
        self.poll()

    def _consume(self, data, drop_first_partial=False):
        parts = (self._partial + data).split("\n")
        self._partial = parts.pop()
        if drop_first_partial and parts:
            parts.pop(0)
        for line in parts:
            self._append_line(line.rstrip("\r"))

    def _reset_file(self):
        self._offset = 0
        self._inode = None
        self._partial = ""
        self._buffer.clear()
        self.view.clear()

    def _append_line(self, line):
        self._buffer.append(line)
        if self._matches(line):
            self._append_html(line)

    def _matches(self, line):
        return not self.edit_filter.text() or \
            self.edit_filter.text().casefold() in line.casefold()

    def _append_html(self, line):
        color_key = {
            "error": "DANGER_LIGHT",
            "warning": "WARNING",
            "ok": "SUCCESS",
        }.get(classify_log_line(line))
        escaped = html.escape(line) or "&nbsp;"
        if color_key:
            color = theme.current_palette()[color_key]
            escaped = '<span style="color:{};">{}</span>'.format(color, escaped)
        self.view.appendHtml(escaped)
        if self.chk_follow.isChecked():
            self._scroll_to_end()

    def _scroll_to_end(self):
        bar = self.view.verticalScrollBar()
        bar.setValue(bar.maximum())

    # -- kullanıcı işlemleri ---------------------------------------------
    def rebuild_view(self):
        """Filtre değiştiğinde tamponu yeniden çizer."""
        self.view.clear()
        for line in filter_lines(self._buffer, self.edit_filter.text()):
            self._append_html(line)
        self._scroll_to_end()

    def clear_view(self):
        self._buffer.clear()
        self.view.clear()

    def _on_pause_toggled(self, paused):
        self.btn_pause.setText(T("Devam et") if paused else T("Duraklat"))
        if not paused:
            self.poll()
