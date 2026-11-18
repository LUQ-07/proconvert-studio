"""Dashboard: welcome, category cards, quick actions, statistics, recent conversions."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout

from ...core.capabilities import CATEGORY_ORDER, targets_for
from ...core.security import FORMAT_LABELS
from ..widgets.common import Card, badge, button, label
from .base import Page


class DashboardPage(Page):
    open_category = Signal(str)
    navigate = Signal(str)

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        tr = self.tr_
        self.col.addWidget(label(tr("dashboard.welcome"), "h1"))
        self.col.addWidget(label(tr("dashboard.subtitle"), "muted"))

        grid = QGridLayout()
        grid.setSpacing(14)
        for i, fmt in enumerate(CATEGORY_ORDER):
            card = Card(clickable=True)
            card.setAccessibleName(tr(f"category.{fmt}"))
            lay = QHBoxLayout(card)
            lay.setContentsMargins(18, 16, 18, 16)
            lay.addWidget(badge(fmt))
            text = QVBoxLayout()
            text.addWidget(label(tr(f"category.{fmt}"), "h3"))
            targets = ", ".join(FORMAT_LABELS[t] for t in targets_for(fmt))
            text.addWidget(label(tr("dashboard.card_desc", source=FORMAT_LABELS[fmt], targets=targets), "muted"))
            lay.addLayout(text, 1)
            card.clicked.connect(lambda f=fmt: self.open_category.emit(f))
            grid.addWidget(card, i // 2, i % 2)
        img_card = Card(clickable=True)
        img_card.setAccessibleName(tr("nav.images"))
        il = QHBoxLayout(img_card)
        il.setContentsMargins(18, 16, 18, 16)
        il.addWidget(badge("image", "IMG"))
        it = QVBoxLayout()
        it.addWidget(label(tr("nav.images"), "h3"))
        it.addWidget(label(tr("images.card_desc"), "muted"))
        il.addLayout(it, 1)
        img_card.clicked.connect(lambda: self.navigate.emit("images"))
        grid.addWidget(img_card, len(CATEGORY_ORDER) // 2, len(CATEGORY_ORDER) % 2)
        self.col.addLayout(grid)

        self.col.addWidget(label(tr("dashboard.quick_actions"), "h2"))
        qa = QHBoxLayout()
        qa.addWidget(button(tr("dashboard.convert_file"), "primary", lambda: self.navigate.emit("convert")))
        qa.addWidget(button(tr("nav.batch"), slot=lambda: self.navigate.emit("batch")))
        qa.addWidget(button(tr("nav.history"), slot=lambda: self.navigate.emit("history")))
        qa.addStretch(1)
        self.col.addLayout(qa)

        self.col.addWidget(label(tr("dashboard.statistics"), "h2"))
        self.stats_row = QHBoxLayout()
        self.stats_row.setSpacing(14)
        self.col.addLayout(self.stats_row)

        self.col.addWidget(label(tr("dashboard.recent"), "h2"))
        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(8)
        self.col.addLayout(self.recent_box)
        self.col.addStretch(1)

    def on_show(self) -> None:
        tr = self.tr_
        s = self.ctx.history.stats()
        self.clear(self.stats_row)
        tiles = [(tr("dashboard.stat_total"), str(s["total"])),
                 (tr("dashboard.stat_rate"), f"{s['success_rate'] * 100:.0f}%" if s["total"] else "-"),
                 (tr("dashboard.stat_time"), f"{s['total_seconds']:.0f} s"),
                 (tr("dashboard.stat_top"), (s["top_route"] or "-").replace("->", "\u2192").upper())]
        for title, value in tiles:
            c = Card()
            lay = QVBoxLayout(c)
            lay.setContentsMargins(16, 14, 16, 14)
            lay.addWidget(label(value, "statValue"))
            lay.addWidget(label(title, "muted"))
            self.stats_row.addWidget(c)
        self.clear(self.recent_box)
        recent = self.ctx.history.query(limit=5)
        if not recent:
            self.recent_box.addWidget(label(tr("dashboard.no_recent"), "muted"))
        for r in recent:
            row = Card()
            lay = QHBoxLayout(row)
            lay.setContentsMargins(14, 10, 14, 10)
            lay.addWidget(badge(r.input_format))
            lay.addWidget(label(f"{r.input_name}  \u2192  {r.output_format.upper()}", "h3"), 1)
            when = datetime.fromisoformat(r.started_at).astimezone().strftime("%Y-%m-%d %H:%M") if r.started_at else ""
            lay.addWidget(label(tr(f"status.{r.status}") + "  \u00b7  " + when, "ok" if r.status == "success" else "muted", wrap=False))
            self.recent_box.addWidget(row)
