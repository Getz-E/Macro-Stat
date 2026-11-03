# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 MacroStat contributors
"""Merkezî tema: renk belirteçleri ve tek global Qt stil sayfası.

Bileşenler görünümü satır içi `setStyleSheet` yerine `variant` / `state`
özellikleriyle seçer; renk değişikliği yalnızca bu dosyada yapılır.
"""

# Renk belirteçleri
BG = "#0b1220"
SURFACE = "#111a2b"
SURFACE_ALT = "#16223a"
INPUT = "#1e293b"
BORDER = "#24344f"
BORDER_STRONG = "#334155"
TEXT = "#e2e8f0"
MUTED = "#94a3b8"
ACCENT = "#0284c7"
ACCENT_LIGHT = "#38bdf8"
SUCCESS = "#10b981"
DANGER = "#ef4444"
DANGER_LIGHT = "#f87171"
WARNING = "#d97706"
VIOLET = "#7c3aed"

STYLESHEET = f"""
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-size: 12px;
}}
QMainWindow, QDialog {{ background-color: {BG}; }}
QLabel {{ background: transparent; }}
QLabel#appTitle {{ font-size: 18px; font-weight: bold; color: white; }}
QLabel#fieldLabel {{ color: {MUTED}; font-size: 12px; font-weight: bold; margin-left: 10px; }}
QLabel#bannerText {{ color: {ACCENT_LIGHT}; font-size: 11px; font-weight: bold; }}
QLabel#dangerText {{ color: {DANGER_LIGHT}; font-size: 11px; font-weight: bold; }}
QLabel#mutedText {{ color: #cbd5e1; font-size: 12px; }}
QLabel#stoppedLabel {{
    color: {DANGER}; font-size: 16px; font-weight: 900; letter-spacing: 3px;
    padding: 3px 18px; background-color: rgba(239, 68, 68, 0.15);
    border: 2px solid {DANGER}; border-radius: 8px;
}}
QLabel#statusBadge {{ font-size: 13px; font-weight: bold; color: {MUTED}; }}
QLabel#statusBadge[state="ok"] {{ color: {SUCCESS}; }}
QLabel#statusBadge[state="info"] {{ color: {ACCENT_LIGHT}; }}
QLabel#statusBadge[state="error"] {{ color: {DANGER}; }}
QLabel#stateLabel {{ color: {MUTED}; font-size: 11px; }}
QLabel#stateLabel[state="on"] {{ color: {SUCCESS}; font-weight: bold; }}
QLabel#sequenceLabel {{ color: {ACCENT_LIGHT}; font-size: 12px; font-weight: bold; min-width: 14px; }}
QLabel#captureStatus {{ font-size: 15px; font-weight: bold; color: {ACCENT_LIGHT}; }}
QLabel#captureStatus[state="ok"] {{ color: {SUCCESS}; }}

QFrame#headerFrame {{
    background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px;
}}
QFrame#infoBanner {{
    background-color: rgba(14, 165, 233, 0.12); border: 1px solid {ACCENT};
    border-radius: 8px;
}}
QFrame#dangerBanner {{
    background-color: rgba(239, 68, 68, 0.15); border: 1px solid {DANGER};
    border-radius: 8px;
}}
QFrame#keyCaptureBox {{
    background-color: #090d16; border: 2px dashed {ACCENT}; border-radius: 10px;
}}

QGroupBox {{
    border: 1px solid {BORDER}; border-radius: 8px; margin-top: 12px;
    padding-top: 8px; font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {ACCENT_LIGHT};
}}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {{
    background-color: {INPUT}; border: 1px solid #475569; border-radius: 6px;
    padding: 4px 8px; color: {TEXT}; selection-background-color: {ACCENT};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QTextEdit:focus {{ border-color: {ACCENT_LIGHT}; }}
QComboBox QAbstractItemView {{
    background-color: {SURFACE}; border: 1px solid {BORDER};
    selection-background-color: {ACCENT}; color: {TEXT};
}}
QComboBox#profileCombo {{
    color: {ACCENT_LIGHT}; font-weight: bold; border-color: {ACCENT};
    min-width: 150px; font-size: 11px;
}}

QPushButton {{
    background-color: {INPUT}; color: {TEXT}; border: 1px solid {BORDER_STRONG};
    border-radius: 6px; padding: 5px 10px; font-weight: bold;
}}
QPushButton:hover {{ background-color: {BORDER_STRONG}; }}
QPushButton:disabled {{ color: #64748b; }}
QPushButton[variant="primary"] {{ background-color: {ACCENT}; color: white; border-color: {ACCENT}; }}
QPushButton[variant="primary"]:hover {{ background-color: {ACCENT_LIGHT}; color: {BG}; }}
QPushButton[variant="success"] {{ background-color: {SUCCESS}; color: #022c22; border-color: {SUCCESS}; }}
QPushButton[variant="danger"] {{ background-color: #dc2626; color: white; border-color: #dc2626; }}
QPushButton[variant="danger"]:hover {{ background-color: {DANGER}; }}
QPushButton[variant="warning"] {{ background-color: {WARNING}; color: white; border-color: {WARNING}; }}
QPushButton[variant="accent"] {{ background-color: #4338ca; color: white; border-color: #4338ca; }}
QPushButton[variant="violet"] {{ background-color: {VIOLET}; color: white; border-color: {VIOLET}; }}
QPushButton[variant="muted"] {{ background-color: #475569; color: white; border-color: #475569; }}
QPushButton[variant="ghostDanger"] {{ background: transparent; color: {DANGER_LIGHT}; border-color: {DANGER}; }}
QPushButton[variant="ghostDanger"]:hover {{ background-color: #dc2626; color: white; }}
QPushButton[compact="true"] {{ padding: 3px 8px; font-size: 11px; }}

QToolButton {{
    background-color: {INPUT}; color: {TEXT}; border: 1px solid {BORDER_STRONG};
    border-radius: 6px; padding: 4px 8px; font-weight: bold;
}}
QToolButton:hover {{ background-color: {BORDER_STRONG}; }}
QToolButton::menu-indicator {{ image: none; }}
QToolButton#iconButton {{ min-width: 26px; min-height: 24px; font-size: 14px; padding: 2px 6px; }}
QToolButton#profileMenu {{ font-size: 15px; padding: 2px 8px; }}
QToolButton[variant="primary"] {{ background-color: {ACCENT}; color: white; border-color: {ACCENT}; }}
QToolButton[variant="success"] {{ background-color: {SUCCESS}; color: #022c22; border-color: {SUCCESS}; }}
QToolButton[variant="danger"] {{ background-color: #dc2626; color: white; border-color: #dc2626; }}
QToolButton[variant="muted"] {{ background-color: #475569; color: white; border-color: #475569; }}

QTableWidget {{
    background-color: #0f172a; alternate-background-color: {SURFACE};
    gridline-color: {BORDER}; border: 1px solid {BORDER}; border-radius: 8px;
}}
QTableWidget::item:selected {{ background-color: {ACCENT}; color: white; }}
QHeaderView::section {{
    background-color: {SURFACE_ALT}; color: {MUTED}; border: none;
    border-right: 1px solid {BORDER}; padding: 6px; font-weight: bold;
}}

QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; top: -1px; }}
QTabBar::tab {{
    background-color: {SURFACE}; color: {MUTED}; padding: 8px 16px;
    border: 1px solid {BORDER}; border-bottom: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
    margin-right: 2px; font-weight: bold;
}}
QTabBar::tab:selected {{ background-color: {ACCENT}; color: white; border-color: {ACCENT}; }}

QMenu {{ background-color: {SURFACE}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px 6px 16px; }}
QMenu::item:selected {{ background-color: {ACCENT}; color: white; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

QScrollBar:vertical {{ background: {SURFACE}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER_STRONG}; border-radius: 5px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: {SURFACE}; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {BORDER_STRONG}; border-radius: 5px; min-width: 24px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
"""


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


def apply_theme(app):
    app.setStyleSheet(STYLESHEET)
