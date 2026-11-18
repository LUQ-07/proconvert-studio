"""Qt stylesheet generated from design tokens. Dark, Light and Follow-System."""
from __future__ import annotations

from .palette import DARK, LIGHT

FONT_STACK = '"Segoe UI Variable", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Inter", "Noto Sans", "DejaVu Sans", sans-serif'


def is_dark(app, appearance: str) -> bool:
    if appearance == "dark":
        return True
    if appearance == "light":
        return False
    try:  # Qt >= 6.5
        from PySide6.QtCore import Qt
        scheme = app.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return True
        if scheme == Qt.ColorScheme.Light:
            return False
    except Exception:  # noqa: BLE001
        pass
    from PySide6.QtGui import QPalette
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


def build_qss(p: dict[str, str]) -> str:
    return f"""
* {{ font-family: {FONT_STACK}; font-size: 13px; color: {p['text']}; outline: 0; }}
QMainWindow, QDialog, QWidget#Root, QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {p['bg']}; }}
QToolTip {{ background: {p['surface2']}; color: {p['text']}; border: 1px solid {p['border']}; padding: 6px; }}
QLabel {{ background: transparent; }}
QLabel#h1 {{ font-size: 26px; font-weight: 700; }}
QLabel#h2 {{ font-size: 18px; font-weight: 650; }}
QLabel#h3 {{ font-size: 14px; font-weight: 650; }}
QLabel#muted {{ color: {p['muted']}; }}
QLabel#statValue {{ font-size: 24px; font-weight: 700; }}
QLabel#ok {{ color: {p['success']}; font-weight: 600; }}
QLabel#warn {{ color: {p['warning']}; }}
QLabel#err {{ color: {p['danger']}; font-weight: 600; }}
QLabel#badge {{ color: {p['badge_text']}; font-weight: 700; font-size: 12px; border-radius: 8px; padding: 6px 8px; }}
QLabel#badge[kind="pdf"] {{ background: {p['badge_pdf']}; }}
QLabel#badge[kind="docx"] {{ background: {p['badge_docx']}; }}
QLabel#badge[kind="pptx"] {{ background: {p['badge_pptx']}; }}
QLabel#badge[kind="xlsx"] {{ background: {p['badge_xlsx']}; }}
QLabel#badge[kind="image"] {{ background: {p['badge_image']}; }}
QFrame#Sidebar {{ background: {p['surface']}; border-right: 1px solid {p['border']}; }}
QFrame#Card, QFrame#Panel {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 14px; }}
QFrame#Card[clickable="true"]:hover {{ border: 1px solid {p['accent']}; background: {p['surface2']}; }}
QFrame#Card:focus, QFrame#DropZone:focus {{ border: 2px solid {p['focus']}; }}
QFrame#Banner {{ background: {p['surface2']}; border: 1px solid {p['warning']}; border-radius: 10px; }}
QFrame#DropZone {{ background: {p['surface']}; border: 2px dashed {p['border']}; border-radius: 16px; }}
QFrame#DropZone[active="true"] {{ border: 2px dashed {p['accent']}; background: {p['surface2']}; }}
QPushButton {{ background: {p['surface2']}; border: 1px solid {p['border']}; border-radius: 9px; padding: 9px 16px; font-weight: 600; }}
QPushButton:hover {{ border-color: {p['accent']}; }}
QPushButton:focus {{ border: 2px solid {p['focus']}; }}
QPushButton:disabled {{ color: {p['muted']}; background: {p['surface']}; border-color: {p['border']}; }}
QPushButton[variant="primary"] {{ background: {p['accent']}; color: {p['accent_text']}; border: 1px solid {p['accent']}; font-size: 14px; padding: 11px 26px; }}
QPushButton[variant="primary"]:hover {{ background: {p['accent_hover']}; }}
QPushButton[variant="primary"]:disabled {{ background: {p['surface2']}; color: {p['muted']}; border-color: {p['border']}; }}
QPushButton[variant="danger"] {{ color: {p['danger']}; }}
QPushButton[variant="link"] {{ background: transparent; border: none; color: {p['accent']}; padding: 4px 6px; text-align: left; }}
QFrame#TopBar {{ background: {p['bg']}; border-bottom: 1px solid {p['border']}; }}
QPushButton#iconbtn {{ background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 6px; min-width: 20px; min-height: 20px; }}
QPushButton#iconbtn:hover {{ background: {p['surface2']}; }}
QPushButton#iconbtn:focus {{ border: 2px solid {p['focus']}; }}
QPushButton#iconbtn:disabled {{ background: transparent; }}
QPushButton#nav {{ background: transparent; border: none; border-radius: 10px; padding: 10px 12px; text-align: left; font-weight: 600; color: {p['muted']}; }}
QPushButton#nav:hover {{ background: {p['surface2']}; color: {p['text']}; }}
QPushButton#nav:checked {{ background: {p['surface2']}; color: {p['text']}; border-left: 3px solid {p['accent']}; }}
QPushButton#nav:focus {{ border: 2px solid {p['focus']}; }}
QPushButton#seg {{ border-radius: 9px; padding: 8px 14px; }}
QPushButton#seg:checked {{ background: {p['accent']}; color: {p['accent_text']}; border-color: {p['accent']}; }}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 8px; padding: 8px 10px; selection-background-color: {p['accent']}; selection-color: {p['accent_text']}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border: 2px solid {p['focus']}; }}
QLineEdit:read-only {{ background: {p['surface2']}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{ background: {p['surface']}; border: 1px solid {p['border']}; selection-background-color: {p['accent']}; selection-color: {p['accent_text']}; }}
QCheckBox {{ spacing: 10px; background: transparent; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border: 2px solid {p['muted']}; border-radius: 5px; background: {p['surface']}; }}
QCheckBox::indicator:checked {{ background: {p['accent']}; border-color: {p['accent']}; }}
QCheckBox:focus {{ color: {p['accent']}; }}
QProgressBar {{ border: 1px solid {p['border']}; border-radius: 7px; background: {p['surface2']}; height: 14px; text-align: center; color: {p['text']}; }}
QProgressBar::chunk {{ background: {p['accent']}; border-radius: 6px; }}
QTabWidget::pane {{ border: 1px solid {p['border']}; border-radius: 10px; background: {p['surface']}; top: -1px; }}
QTabBar::tab {{ background: transparent; padding: 10px 18px; margin-right: 4px; border-radius: 8px; color: {p['muted']}; font-weight: 600; }}
QTabBar::tab:selected {{ background: {p['surface2']}; color: {p['text']}; }}
QTabBar::tab:focus {{ border: 2px solid {p['focus']}; }}
QTableWidget, QTableView {{ background: {p['surface']}; alternate-background-color: {p['surface2']}; border: 1px solid {p['border']}; border-radius: 10px; gridline-color: {p['border']}; selection-background-color: {p['accent']}; selection-color: {p['accent_text']}; }}
QHeaderView::section {{ background: {p['surface2']}; color: {p['text']}; padding: 8px; border: none; border-bottom: 1px solid {p['border']}; font-weight: 650; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p['border']}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {p['muted']}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p['border']}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QStatusBar {{ background: {p['surface']}; color: {p['muted']}; border-top: 1px solid {p['border']}; }}
QMessageBox, QInputDialog {{ background: {p['surface']}; }}
"""


def apply_theme(app, appearance: str) -> dict[str, str]:
    palette = DARK if is_dark(app, appearance) else LIGHT
    app.setStyle("Fusion")
    app.setStyleSheet(build_qss(palette))
    return palette
