# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Sol dikey kenar çubuğu ve sayfa yığını.

`PageStack`, mevcut kodun `QTabWidget` üzerinden kullandığı küçük API
yüzeyini (`currentIndex`, `setCurrentIndex`, `setCurrentWidget`,
`currentChanged`, ...) birebir sunar; böylece sayfa mantığı değişmez.
"""

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QListWidget, QListWidgetItem, QStackedWidget, QVBoxLayout, QWidget,
)

from . import theme
from .common import T  # noqa: F401


class NavSidebar(QWidget):
    """İkon + etiketli dikey gezinme listesi."""

    currentRowChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("navSidebar")
        self.setFixedWidth(196)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.list = QListWidget()
        self.list.setObjectName("navList")
        self.list.setIconSize(QSize(18, 18))
        self.list.setSpacing(1)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.currentRowChanged.connect(self.currentRowChanged)
        layout.addWidget(self.list)

    def add_item(self, text, icon_name=""):
        item = QListWidgetItem(theme.icon(icon_name), text)
        item.setSizeHint(QSize(0, 40))
        self.list.addItem(item)

    def set_current_row(self, row):
        self.list.setCurrentRow(row)


class PageStack(QWidget):
    """Kenar çubuğu + `QStackedWidget`; `QTabWidget` uyumlu yüzey."""

    currentChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.sidebar = NavSidebar()
        self.stack = QStackedWidget()

        layout.addWidget(self.sidebar)
        layout.addWidget(self.stack, 1)

        self.sidebar.currentRowChanged.connect(self._on_row_changed)

    def add_page(self, widget, label, icon_name=""):
        self.stack.addWidget(widget)
        self.sidebar.add_item(label, icon_name)
        if self.stack.count() == 1:
            self.sidebar.set_current_row(0)

    # QTabWidget uyumluluğu
    def addTab(self, widget, label):  # noqa: N802 - Qt adlandırması
        self.add_page(widget, label)

    def count(self):
        return self.stack.count()

    def widget(self, index):
        return self.stack.widget(index)

    def currentIndex(self):  # noqa: N802 - Qt adlandırması
        return self.stack.currentIndex()

    def currentWidget(self):  # noqa: N802 - Qt adlandırması
        return self.stack.currentWidget()

    def setCurrentIndex(self, index):  # noqa: N802 - Qt adlandırması
        if index < 0 or index >= self.stack.count() or index == self.stack.currentIndex():
            return
        self.stack.setCurrentIndex(index)
        self.sidebar.set_current_row(index)
        self.currentChanged.emit(index)

    def setCurrentWidget(self, widget):  # noqa: N802 - Qt adlandırması
        index = self.stack.indexOf(widget)
        if index >= 0:
            self.setCurrentIndex(index)

    def _on_row_changed(self, row):
        if row < 0 or row >= self.stack.count():
            return
        if row == self.stack.currentIndex():
            return
        self.stack.setCurrentIndex(row)
        self.currentChanged.emit(row)
