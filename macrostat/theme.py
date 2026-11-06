# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Merkezî tema: renk belirteçleri, açık/koyu paletler ve tek Qt stil sayfası.

Bileşenler görünümü satır içi `setStyleSheet` yerine `variant` / `state`
özellikleriyle seçer; renk değişikliği yalnızca bu dosyada yapılır.
"""

from string import Template

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPalette

#: Koyu palet (varsayılan). Breeze'e yakın, düşük doygunluklu renkler.
DARK = {
    "BG": "#111318",
    "SURFACE": "#181b22",
    "SURFACE_ALT": "#1e222b",
    "INPUT": "#20242e",
    "TABLE_BG": "#151820",
    "BORDER": "#2a2f3a",
    "BORDER_STRONG": "#3a4150",
    "TEXT": "#e5e7eb",
    "MUTED": "#9ca3af",
    "SELECT_TEXT": "#ffffff",
    "ACCENT": "#3daee9",
    "ACCENT_LIGHT": "#63c7f5",
    "ACCENT_SOFT": "#1c3446",
    "SUCCESS": "#2ecc71",
    "DANGER": "#e74c3c",
    "DANGER_LIGHT": "#ff7b6b",
    "WARNING": "#e0a030",
    "VIOLET": "#7a6cf0",
    "DANGER_BG": "rgba(231, 76, 60, 0.14)",
    "INFO_BG": "rgba(61, 174, 233, 0.12)",
    "KEYBOX_BG": "#0d1016",
}

#: Açık palet.
LIGHT = {
    "BG": "#f5f6f8",
    "SURFACE": "#ffffff",
    "SURFACE_ALT": "#eef0f4",
    "INPUT": "#ffffff",
    "TABLE_BG": "#ffffff",
    "BORDER": "#d7dbe2",
    "BORDER_STRONG": "#c2c8d2",
    "TEXT": "#1f2329",
    "MUTED": "#5f6672",
    "SELECT_TEXT": "#ffffff",
    "ACCENT": "#1d7fbf",
    "ACCENT_LIGHT": "#2196d6",
    "ACCENT_SOFT": "#dcecf7",
    "SUCCESS": "#1e9e56",
    "DANGER": "#c0392b",
    "DANGER_LIGHT": "#a83226",
    "WARNING": "#a86e12",
    "VIOLET": "#5b4bd6",
    "DANGER_BG": "rgba(192, 57, 43, 0.10)",
    "INFO_BG": "rgba(29, 127, 191, 0.10)",
    "KEYBOX_BG": "#fbfcfd",
}

PALETTES = {"dark": DARK, "light": LIGHT}

_mode = "dark"
_palette = DARK
_scheme_connected = False

_STYLE_TEMPLATE = Template("""
QWidget {
    background-color: $BG;
    color: $TEXT;
    font-size: 12px;
}
QMainWindow, QDialog { background-color: $BG; }
QLabel { background: transparent; }
QLabel#appTitle { font-size: 17px; font-weight: 600; color: $TEXT; }
QLabel#fieldLabel { color: $MUTED; font-size: 12px; font-weight: 600; }
QLabel#bannerText { color: $ACCENT_LIGHT; font-size: 11px; font-weight: 600; }
QLabel#dangerText { color: $DANGER_LIGHT; font-size: 11px; font-weight: 600; }
QLabel#mutedText { color: $MUTED; font-size: 12px; }
QLabel#stoppedLabel {
    color: $DANGER; font-size: 13px; font-weight: 700; letter-spacing: 2px;
    padding: 3px 14px; background-color: $DANGER_BG;
    border: 1px solid $DANGER; border-radius: 6px;
}
QLabel#statusBadge { font-size: 12px; font-weight: 600; color: $MUTED; }
QLabel#statusBadge[state="ok"] { color: $SUCCESS; }
QLabel#statusBadge[state="info"] { color: $ACCENT_LIGHT; }
QLabel#statusBadge[state="error"] { color: $DANGER; }
QLabel#stateLabel { color: $MUTED; font-size: 11px; }
QLabel#stateLabel[state="on"] { color: $SUCCESS; font-weight: 600; }
QLabel#sequenceLabel { color: $ACCENT_LIGHT; font-size: 12px; font-weight: 600; min-width: 14px; }
QLabel#captureStatus { font-size: 15px; font-weight: 600; color: $ACCENT_LIGHT; }
QLabel#captureStatus[state="ok"] { color: $SUCCESS; }

QFrame#headerFrame {
    background-color: $SURFACE; border: 1px solid $BORDER; border-radius: 8px;
}
QFrame#infoBanner {
    background-color: $INFO_BG; border: 1px solid $ACCENT; border-radius: 6px;
}
QFrame#dangerBanner {
    background-color: $DANGER_BG; border: 1px solid $DANGER; border-radius: 6px;
}
QFrame#keyCaptureBox {
    background-color: $KEYBOX_BG; border: 1px solid $ACCENT; border-radius: 8px;
}
QScrollArea#editorScroll, QScrollArea#editorScroll > QWidget > QWidget {
    background: transparent; border: none;
}
QWidget#navSidebar {
    background-color: $SURFACE; border: 1px solid $BORDER; border-radius: 8px;
}
QListWidget#navList {
    background: transparent; border: none; outline: 0; padding: 8px 6px;
}
QListWidget#navList::item {
    color: $MUTED; padding: 10px 10px; border-radius: 6px;
    border-left: 3px solid transparent; margin: 1px 0;
}
QListWidget#navList::item:hover { background-color: $SURFACE_ALT; color: $TEXT; }
QListWidget#navList::item:selected {
    background-color: $ACCENT_SOFT; color: $TEXT; border-left: 3px solid $ACCENT;
}
QWidget#logPanel { background-color: $SURFACE; border: 1px solid $BORDER; border-radius: 8px; }
QLabel#panelTitle { color: $MUTED; font-weight: 600; }
QWidget#logPanel QLineEdit { padding: 2px 8px; }
QPlainTextEdit#logView {
    background-color: $TABLE_BG; border: 1px solid $BORDER; border-radius: 4px;
    font-family: "Cascadia Mono", "Noto Sans Mono", monospace; font-size: 11px;
    padding: 4px 6px;
}
QLabel#onboardingStatus[state="ok"], QLabel#onboardingResult[state="ok"] { color: $SUCCESS; }
QLabel#onboardingStatus[state="error"], QLabel#onboardingResult[state="error"] { color: $DANGER; }
QLabel#onboardingResult[state="info"] { color: $ACCENT_LIGHT; }
QLabel#onboardingTitle { font-weight: 600; }
QLabel#onboardingDetail { color: $MUTED; }
QWizard { background-color: $BG; }

QGroupBox {
    border: 1px solid $BORDER; border-radius: 6px; margin-top: 12px;
    padding-top: 8px; font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 10px; padding: 0 5px; color: $TEXT;
}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {
    background-color: $INPUT; border: 1px solid $BORDER_STRONG; border-radius: 5px;
    padding: 4px 8px; color: $TEXT; selection-background-color: $ACCENT;
    selection-color: $SELECT_TEXT;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QTextEdit:focus { border-color: $ACCENT; }
QComboBox QAbstractItemView {
    background-color: $SURFACE; border: 1px solid $BORDER;
    selection-background-color: $ACCENT; selection-color: $SELECT_TEXT; color: $TEXT;
}
QComboBox#profileCombo {
    color: $TEXT; font-weight: 600; border-color: $BORDER_STRONG;
    min-width: 150px; font-size: 12px;
}

QCheckBox, QRadioButton { color: $TEXT; spacing: 8px; }
QCheckBox::indicator, QRadioButton::indicator {
    width: 14px; height: 14px; border: 1px solid $BORDER_STRONG;
    border-radius: 3px; background-color: $INPUT;
}
QRadioButton::indicator { border-radius: 7px; }
QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: $ACCENT; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background-color: $ACCENT; border-color: $ACCENT;
}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {
    border-color: $BORDER; background-color: $SURFACE;
}

QPushButton {
    background-color: $INPUT; color: $TEXT; border: 1px solid $BORDER_STRONG;
    border-radius: 5px; padding: 5px 12px; font-weight: 600;
}
QPushButton:hover { background-color: $SURFACE_ALT; border-color: $ACCENT; }
QPushButton:pressed { background-color: $ACCENT_SOFT; }
QPushButton:disabled { color: $MUTED; }
QPushButton[variant="primary"] { background-color: $ACCENT; color: $SELECT_TEXT; border-color: $ACCENT; }
QPushButton[variant="primary"]:hover { background-color: $ACCENT_LIGHT; color: $SELECT_TEXT; }
QPushButton[variant="success"] { background-color: $SUCCESS; color: $SELECT_TEXT; border-color: $SUCCESS; }
QPushButton[variant="danger"] { background-color: $DANGER; color: $SELECT_TEXT; border-color: $DANGER; }
QPushButton[variant="danger"]:hover { background-color: $DANGER_LIGHT; }
QPushButton[variant="warning"] { background-color: $WARNING; color: $SELECT_TEXT; border-color: $WARNING; }
QPushButton[variant="accent"] { background-color: $ACCENT; color: $SELECT_TEXT; border-color: $ACCENT; }
QPushButton[variant="violet"] { background-color: $VIOLET; color: $SELECT_TEXT; border-color: $VIOLET; }
QPushButton[variant="muted"] { background-color: $SURFACE_ALT; color: $TEXT; border-color: $BORDER_STRONG; }
QPushButton[variant="ghostDanger"] { background: transparent; color: $DANGER; border-color: $BORDER; }
QPushButton[variant="ghostDanger"]:hover { background-color: $DANGER_BG; }
QPushButton[compact="true"] { padding: 3px 8px; font-size: 11px; }

QToolButton {
    background-color: transparent; color: $TEXT; border: 1px solid $BORDER;
    border-radius: 5px; padding: 4px 9px; font-weight: 600;
}
QToolButton:hover { background-color: $SURFACE_ALT; border-color: $ACCENT; }
QToolButton::menu-indicator { image: none; }
QToolButton#iconButton { min-width: 26px; min-height: 24px; padding: 2px 6px; }
QToolButton#profileMenu { padding: 2px 8px; }
QToolButton[variant="primary"] { background-color: $ACCENT; color: $SELECT_TEXT; border-color: $ACCENT; }
QToolButton[variant="success"] { background-color: $SUCCESS; color: $SELECT_TEXT; border-color: $SUCCESS; }
QToolButton[variant="danger"] { background-color: $DANGER; color: $SELECT_TEXT; border-color: $DANGER; }
QToolButton[variant="muted"] { background-color: $SURFACE_ALT; color: $TEXT; border-color: $BORDER_STRONG; }

QTableWidget {
    background-color: $TABLE_BG; alternate-background-color: $SURFACE;
    gridline-color: $BORDER; border: 1px solid $BORDER; border-radius: 6px;
}
QTableWidget::item:selected { background-color: $ACCENT; color: $SELECT_TEXT; }
QHeaderView::section {
    background-color: $SURFACE_ALT; color: $MUTED; border: none;
    border-right: 1px solid $BORDER; padding: 6px; font-weight: 600;
}
QListWidget {
    background-color: $TABLE_BG; border: 1px solid $BORDER; border-radius: 6px;
}

QMenu { background-color: $SURFACE; border: 1px solid $BORDER; padding: 4px; }
QMenu::item { padding: 6px 24px 6px 16px; color: $TEXT; }
QMenu::item:selected { background-color: $ACCENT; color: $SELECT_TEXT; }
QMenu::separator { height: 1px; background: $BORDER; margin: 4px 8px; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: $BORDER_STRONG; border-radius: 5px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: $BORDER_STRONG; border-radius: 5px; min-width: 24px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QStatusBar { background-color: $SURFACE; color: $MUTED; }
QToolTip { background-color: $SURFACE_ALT; color: $TEXT; border: 1px solid $BORDER; padding: 4px; }
""")


def build_stylesheet(palette):
    """Palet sözlüğünden tek global stil sayfası üretir."""
    return _STYLE_TEMPLATE.substitute(palette)


def current_palette():
    """Etkin palet sözlüğü (özelleştirilmiş çizimler için)."""
    return _palette


def current_mode():
    return _mode


def resolve_mode(app, mode):
    """`system` modunu Qt'nin renk şemasından açık/koyuya çözer."""
    if mode in ("dark", "light"):
        return mode
    try:
        scheme = app.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Light:
            return "light"
    except Exception:
        pass
    return "dark"


def _apply_palette(app, palette):
    """Qt'nin kendi çizdiği kontroller (onay kutusu, ipucu) için temel palet."""
    qt_palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: palette["BG"],
        QPalette.ColorRole.WindowText: palette["TEXT"],
        QPalette.ColorRole.Base: palette["INPUT"],
        QPalette.ColorRole.AlternateBase: palette["SURFACE_ALT"],
        QPalette.ColorRole.Text: palette["TEXT"],
        QPalette.ColorRole.Button: palette["INPUT"],
        QPalette.ColorRole.ButtonText: palette["TEXT"],
        QPalette.ColorRole.Highlight: palette["ACCENT"],
        QPalette.ColorRole.HighlightedText: palette["SELECT_TEXT"],
        QPalette.ColorRole.ToolTipBase: palette["SURFACE"],
        QPalette.ColorRole.ToolTipText: palette["TEXT"],
        QPalette.ColorRole.PlaceholderText: palette["MUTED"],
    }
    for role, color in roles.items():
        qt_palette.setColor(role, QColor(color))
    try:
        app.setPalette(qt_palette)
    except Exception:
        pass


def apply_theme(app, mode="dark"):
    """Temayı uygular. `system` seçiliyse Qt renk şeması değişimini izler."""
    global _mode, _palette, _scheme_connected
    _mode = mode if mode in ("system", "dark", "light") else "dark"
    resolved = resolve_mode(app, _mode)
    _palette = PALETTES[resolved]
    _apply_palette(app, _palette)
    app.setStyleSheet(build_stylesheet(_palette))
    if not _scheme_connected:
        try:
            app.styleHints().colorSchemeChanged.connect(
                lambda _scheme: apply_theme(app, _mode) if _mode == "system" else None)
            _scheme_connected = True
        except Exception:
            pass


def icon(name):
    """Sistem tema ikonunu döndürür; bulunamazsa boş ikon (düğme metin gösterir)."""
    if not name:
        return QIcon()
    try:
        return QIcon.fromTheme(name)
    except Exception:
        return QIcon()


def _repolish(widget):
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def set_variant(widget, variant):
    """Statik görünüm varyantı: primary, success, danger, warning, accent, muted..."""
    widget.setProperty("variant", variant)
    _repolish(widget)


def set_state(widget, state):
    """Durum tabanlı renk: ok, info, error, on."""
    widget.setProperty("state", state)
    _repolish(widget)
