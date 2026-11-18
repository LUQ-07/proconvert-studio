"""Reusable widgets: drop zone, cards, helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget)


def repolish(w: QWidget) -> None:
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


def label(text: str = "", name: str = "", wrap: bool = True) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(wrap)
    lb.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return lb


def button(text: str, variant: str = "", slot: Callable | None = None) -> QPushButton:
    b = QPushButton(text)
    if variant:
        b.setProperty("variant", variant)
    if slot:
        b.clicked.connect(lambda _checked=False: slot())
    return b


def badge(kind: str, text: str | None = None) -> QLabel:
    lb = QLabel(text or kind.upper()[:4])
    lb.setObjectName("badge")
    lb.setProperty("kind", kind)
    lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lb.setFixedWidth(52)
    return lb


class Card(QFrame):
    """Rounded surface. With ``clickable`` it is keyboard-focusable and emits ``clicked``."""

    clicked = Signal()

    def __init__(self, clickable: bool = False) -> None:
        super().__init__()
        self.setObjectName("Card")
        self._clickable = clickable
        if clickable:
            self.setProperty("clickable", True)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if self._clickable and e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if self._clickable and e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(e)


class DropZone(QFrame):
    """Drag-and-drop target that is also usable with the keyboard (Enter/Space opens the picker)."""

    files_dropped = Signal(list)
    browse_requested = Signal()

    def __init__(self, title: str, hint: str, button_text: str) -> None:
        super().__init__()
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(150)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = label(title, "h2")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint = label(hint, "muted")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.browse = button(button_text)
        self.browse.clicked.connect(lambda _c=False: self.browse_requested.emit())
        lay.addWidget(self.title)
        lay.addWidget(self.hint)
        lay.addWidget(self.browse, 0, Qt.AlignmentFlag.AlignCenter)
        self.setAccessibleName(title)
        self.setAccessibleDescription(hint)

    def set_texts(self, title: str, hint: str, button_text: str) -> None:
        self.title.setText(title)
        self.hint.setText(hint)
        self.browse.setText(button_text)

    def _set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        repolish(self)

    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._set_active(True)

    def dragLeaveEvent(self, e) -> None:  # noqa: N802
        self._set_active(False)

    def dropEvent(self, e) -> None:  # noqa: N802
        self._set_active(False)
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            e.acceptProposedAction()
            self.files_dropped.emit([str(Path(p)) for p in paths])

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.browse_requested.emit()
            return
        super().keyPressEvent(e)


def hbox(*widgets, spacing: int = 10, stretch_last: bool = False) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    for w in widgets:
        lay.addWidget(w)
    if stretch_last:
        lay.addStretch(1)
    return lay
