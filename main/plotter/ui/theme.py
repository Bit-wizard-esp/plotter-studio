"""Темы в стиле Windows 11 (Fluent): тёмная и светлая.

Палитра взята из Windows 11:
  тёмная  — фон #202020, карточки #2B2B2B, акцент #4CC2FF
  светлая — фон #F3F3F3, карточки #FBFBFB, акцент #005FB8
"""
from __future__ import annotations

import os

from PySide6.QtGui import QColor, QFont

_ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")

DARK = {
    "bg": "#202020",
    "bg_alt": "#2B2B2B",
    "card": "#2B2B2B",
    "card_border": "#3A3A3A",
    "control": "#252526",
    "control_border": "#3F3F3F",
    "control_hover": "#2F2F30",
    "control_pressed": "#252526",
    "text": "#FFFFFF",
    "text_dim": "#BFBFBF",
    "text_hint": "#8F8F8F",
    "disabled": "#707070",
    "accent": "#4CC2FF",
    "accent_hover": "#6ACBFF",
    "accent_pressed": "#35B0F2",
    "accent_text": "#062B3D",
    "accent_disabled": "#2A5568",
    "hover": "#333333",
    "selection": "#3D3D3D",
    "canvas": "#191919",
    "canvas_grid": "#2E3A42",
    "canvas_bed": "#233039",
    "canvas_bed_edge": "#4CC2FF",
    "canvas_image_edge": "#8F8F8F",
    "canvas_path": "#FF6E6E",
    "canvas_lines": "#FF5252",
    "canvas_start": "#7EE787",
    "scroll": "#4D4D4D",
    "scroll_hover": "#5E5E5E",
    "tooltip_bg": "#2B2B2B",
}

LIGHT = {
    "bg": "#F3F3F3",
    "bg_alt": "#FBFBFB",
    "card": "#FBFBFB",
    "card_border": "#E3E3E3",
    "control": "#FFFFFF",
    "control_border": "#D6D6D6",
    "control_hover": "#F5F5F5",
    "control_pressed": "#EFEFEF",
    "text": "#1B1B1B",
    "text_dim": "#4C4C4C",
    "text_hint": "#7A7A7A",
    "disabled": "#A0A0A0",
    "accent": "#005FB8",
    "accent_hover": "#1A6CC0",
    "accent_pressed": "#004C97",
    "accent_text": "#FFFFFF",
    "accent_disabled": "#9DC3E0",
    "hover": "#E9E9E9",
    "selection": "#E3EDF7",
    "canvas": "#ECECEC",
    "canvas_grid": "#D8D8D8",
    "canvas_bed": "#E8EEF3",
    "canvas_bed_edge": "#005FB8",
    "canvas_image_edge": "#7A7A7A",
    "canvas_path": "#D13438",
    "canvas_lines": "#C42B1C",
    "canvas_start": "#107C10",
    "scroll": "#C9C9C9",
    "scroll_hover": "#B5B5B5",
    "tooltip_bg": "#FBFBFB",
}

PALETTES = {"dark": DARK, "light": LIGHT}


def build_qss(p: dict) -> str:
    i = _ICONS
    return f"""
/* ============ база ============ */
* {{ font-family: "Segoe UI Variable Text", "Segoe UI", sans-serif; font-size: 9pt; }}
QWidget {{ background: transparent; color: {p['text']}; }}
QMainWindow, QDialog {{ background: {p['bg']}; }}
QLabel {{ background: transparent; }}
QLabel[hint="true"] {{ color: {p['text_hint']}; font-size: 8pt; }}
QLabel[title="true"] {{ font-size: 10pt; font-weight: 600; }}
QLabel[warn="true"] {{ color: {p['canvas_path']}; font-size: 8pt; }}
QLabel[ok="true"] {{ color: {p['canvas_start']}; font-size: 8pt; }}

/* ============ карточки ============ */
QFrame[card="true"] {{ background: {p['card']}; border: 1px solid {p['card_border']};
                      border-radius: 8px; }}
QFrame[header="true"] {{ background: {p['bg_alt']}; border-bottom: 1px solid {p['card_border']}; }}
QFrame[header="true"] QLabel[app="true"] {{ font-size: 13pt; font-weight: 700; }}
QFrame[header="true"] QLabel[subtitle="true"] {{ color: {p['text_dim']}; font-size: 8pt; }}

/* ============ кнопки ============ */
QPushButton {{ background: {p['control']}; border: 1px solid {p['control_border']};
               border-radius: 6px; padding: 5px 14px; }}
QPushButton:hover {{ background: {p['control_hover']}; border-color: {p['text_hint']}; }}
QPushButton:pressed {{ background: {p['control_pressed']}; }}
QPushButton:disabled {{ color: {p['disabled']}; background: {p['bg_alt']};
                        border-color: {p['card_border']}; }}
QPushButton[accent="true"] {{ background: {p['accent']}; border: none; color: {p['accent_text']};
                              font-weight: 600; padding: 7px 18px; }}
QPushButton[accent="true"]:hover {{ background: {p['accent_hover']}; }}
QPushButton[accent="true"]:pressed {{ background: {p['accent_pressed']}; }}
QPushButton[accent="true"]:disabled {{ background: {p['accent_disabled']}; color: {p['text_hint']}; }}
QPushButton[flat="true"] {{ background: transparent; border: none; padding: 4px; }}
QPushButton[flat="true"]:hover {{ background: {p['hover']}; border-radius: 4px; }}

/* ============ поля ввода ============ */
QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {p['control']}; border: 1px solid {p['control_border']};
    border-radius: 6px; padding: 4px 8px;
    selection-background-color: {p['accent']}; selection-color: {p['accent_text']}; }}
QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{ border-color: {p['text_hint']}; }}
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {p['accent']}; }}
QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{ color: {p['disabled']}; }}

QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border; subcontrol-position: top right;
    width: 20px; border-left: 1px solid {p['control_border']};
    border-top-right-radius: 6px; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right;
    width: 20px; border-left: 1px solid {p['control_border']};
    border-bottom-right-radius: 6px; }}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background: {p['control_hover']}; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url({i}/spin_up.png); width: 12px; height: 12px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url({i}/spin_down.png); width: 12px; height: 12px; }}

QComboBox::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right;
                        width: 24px; border-left: 1px solid {p['control_border']}; }}
QComboBox::down-arrow {{ image: url({i}/combo_arrow.png); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{ background: {p['card']}; border: 1px solid {p['control_border']};
    border-radius: 6px; selection-background-color: {p['selection']};
    selection-color: {p['text']}; outline: none; padding: 3px; }}

QPlainTextEdit, QTextEdit {{
    background: {p['control']}; border: 1px solid {p['control_border']};
    border-radius: 6px; padding: 4px;
    selection-background-color: {p['accent']}; selection-color: {p['accent_text']}; }}
QPlainTextEdit:focus, QTextEdit:focus {{ border: 1px solid {p['accent']}; }}
QPlainTextEdit::placeholder, QTextEdit::placeholder {{ color: {p['text_hint']}; }}

/* ============ слайдеры ============ */
QSlider::groove:horizontal {{ height: 4px; background: {p['control_border']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {p['accent']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: #F5F5F5; width: 18px; height: 18px;
    margin: -7px 0; border-radius: 9px; border: 1px solid {p['control_border']}; }}
QSlider::handle:horizontal:hover {{ background: #FFFFFF; border-color: {p['accent']}; }}
QSlider::handle:horizontal:disabled {{ background: {p['control_border']}; }}

/* ============ чекбоксы ============ */
QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{ width: 19px; height: 19px; border-radius: 5px;
    border: 1px solid {p['text_hint']}; background: {p['control']}; }}
QCheckBox::indicator:hover {{ border-color: {p['accent']}; }}
QCheckBox::indicator:checked {{ background: {p['accent']}; border-color: {p['accent']};
                                 image: url({i}/check.png); }}
QCheckBox::indicator:disabled {{ border-color: {p['card_border']}; background: {p['bg_alt']}; }}

/* ============ вкладки превью ============ */
QTabBar::tab {{ background: transparent; color: {p['text_dim']};
    padding: 6px 18px; margin-right: 4px; border-radius: 6px; }}
QTabBar::tab:selected {{ background: {p['selection']}; color: {p['text']}; font-weight: 600; }}
QTabBar::tab:hover:!selected {{ background: {p['hover']}; }}
QTabBar {{ qproperty-drawBase: false; }}

/* ============ скроллбары ============ */
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p['scroll']}; border-radius: 4px; min-height: 30px; margin: 2px; }}
QScrollBar::handle:vertical:hover {{ background: {p['scroll_hover']}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p['scroll']}; border-radius: 4px; min-width: 30px; margin: 2px; }}
QScrollBar::handle:horizontal:hover {{ background: {p['scroll_hover']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ============ прочее ============ */
QStatusBar {{ background: {p['bg']}; color: {p['text_dim']}; border-top: 1px solid {p['card_border']}; }}
QToolTip {{ background: {p['tooltip_bg']}; color: {p['text']}; border: 1px solid {p['control_border']};
            padding: 5px 9px; border-radius: 5px; }}
QMenu {{ background: {p['card']}; border: 1px solid {p['control_border']}; border-radius: 8px;
         padding: 5px; }}
QMenu::item {{ padding: 6px 26px; border-radius: 5px; background: transparent; }}
QMenu::item:selected {{ background: {p['selection']}; }}
QSplitter::handle {{ background: {p['bg']}; }}
QProgressBar {{ background: {p['control']}; border: 1px solid {p['control_border']};
                border-radius: 6px; text-align: center; }}
QProgressBar::chunk {{ background: {p['accent']}; border-radius: 5px; }}
"""


def monospace_font() -> QFont:
    f = QFont("Cascadia Mono", 9)
    if not f.exactMatch():
        f = QFont("Consolas", 9)
    if not f.exactMatch():
        f = QFont("Courier New", 9)
    f.setStyleHint(QFont.Monospace)
    return f


def apply(app, theme_name: str = "dark") -> None:
    app.setStyleSheet(build_qss(PALETTES[theme_name]))


def colors(theme_name: str = "dark") -> dict:
    return PALETTES[theme_name]


def canvas_bg(theme_name: str) -> QColor:
    return QColor(PALETTES[theme_name]["canvas"])
