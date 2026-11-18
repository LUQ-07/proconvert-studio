"""Shared page scaffolding."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLayout, QScrollArea, QVBoxLayout, QWidget


class Page(QWidget):
    """Base class: a scrollable column with consistent margins. Subclasses fill ``self.col``."""

    def __init__(self, ctx) -> None:
        super().__init__()
        self.ctx = ctx
        self.tr_ = ctx.tr          # translator callable: self.tr_("key", name=value)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner.setObjectName("Root")
        self.col = QVBoxLayout(inner)
        self.col.setContentsMargins(32, 28, 32, 28)
        self.col.setSpacing(16)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

    def on_show(self) -> None:
        """Called each time the page is navigated to."""

    @staticmethod
    def clear(layout: QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            elif item.layout() is not None:
                Page.clear(item.layout())
