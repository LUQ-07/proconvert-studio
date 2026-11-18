"""Help & Support: quick start, the live capability matrix, troubleshooting, shortcuts."""
from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem

from ...core.capabilities import CATEGORY_ORDER, SUPPORTED, compatibility_grid, image_row
from ...core.security import FORMAT_LABELS
from ..widgets.common import button, hbox, label
from .base import Page


class HelpPage(Page):
    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        tr = self.tr_
        self.col.addWidget(label(tr("help.title"), "h1"))
        self.col.addWidget(label(tr("help.quickstart"), "h2"))
        self.col.addWidget(label(tr("help.quickstart_body"), ""))
        self.col.addWidget(label(tr("help.matrix"), "h2"))
        self.col.addWidget(label(tr("help.matrix_intro"), "muted"))
        grid = compatibility_grid()
        targets = [tr("help.to_pdf"), tr("help.to_word"), tr("help.to_powerpoint"), tr("help.to_excel")]
        rows = [(FORMAT_LABELS[src], row) for src, row in zip(CATEGORY_ORDER, grid)] + [(tr("help.row_images"), image_row())]
        t = QTableWidget(len(rows), len(targets) + 1)
        t.setHorizontalHeaderLabels([tr("help.col_source")] + targets)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        t.verticalHeader().setVisible(False)
        t.setMinimumHeight(60 + 44 * len(rows))
        t.setAccessibleName(tr("help.matrix"))
        # Explicit foreground + background so the status stays readable in both the dark and the light theme.
        styles = {SUPPORTED: ("\u2714 " + tr("help.supported"), "#1b6b3a"),
                  "experimental": ("\u25D0 " + tr("help.experimental"), "#8a5a00")}
        for r, (row_label, row) in enumerate(rows):
            head = QTableWidgetItem(row_label)
            t.setItem(r, 0, head)
            for c, status in enumerate(row, start=1):
                if status is None:
                    item = QTableWidgetItem("\u2014")
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                else:
                    text, colour = styles[status]
                    item = QTableWidgetItem(text)
                    item.setBackground(QBrush(QColor(colour)))
                    item.setForeground(QBrush(QColor("#ffffff")))
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setToolTip(tr("help.legend_supported") if status == SUPPORTED else tr("help.legend_experimental"))
                t.setItem(r, c, item)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t.resizeRowsToContents()
        self.col.addWidget(t)
        self.col.addWidget(label("\u2714 " + tr("help.supported") + ": " + tr("help.legend_supported"), "muted"))
        self.col.addWidget(label("\u25D0 " + tr("help.experimental") + ": " + tr("help.legend_experimental"), "muted"))
        self.col.addWidget(label(tr("help.troubleshooting"), "h2"))
        self.col.addWidget(label(tr("help.troubleshooting_body"), ""))
        self.col.addWidget(label(tr("help.shortcuts"), "h2"))
        self.col.addWidget(label(tr("help.shortcuts_body"), ""))
        self.col.addWidget(label(tr("help.support"), "h2"))
        self.col.addWidget(label(tr("help.support_body"), ""))
        self.col.addLayout(hbox(button(tr("help.report_button"), "primary",
                                       lambda: QDesktopServices.openUrl(QUrl(ctx.repository_url + "/issues/new"))), stretch_last=True))
        self.col.addStretch(1)
