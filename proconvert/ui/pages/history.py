"""Conversion history screen: search, filter, sort, open, retry, export, clear."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QHeaderView, QLineEdit, QMessageBox,
                               QTableWidget, QTableWidgetItem)

from ...core.capabilities import CATEGORY_ORDER
from ...utils.files import reveal_in_file_manager
from ..widgets.common import button, hbox, label
from .base import Page

# column index -> database sort key
COLUMNS = [("started_at", "history.col_date"), ("input_name", "history.col_file"), ("input_format", "history.col_from"),
           ("output_format", "history.col_to"), ("status", "history.col_status"), ("duration_ms", "history.col_time"),
           (None, "history.col_detail")]


class HistoryPage(Page):
    retry_requested = Signal(str, str, str)    # input path, input format, output format

    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        tr = self.tr_
        self.sort_key, self.descending = "started_at", True
        self.records = []
        self.col.addWidget(label(tr("history.title"), "h1"))

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("history.search"))
        self.search.setAccessibleName(tr("history.search"))
        self.search.setClearButtonEnabled(True)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda _t: self._debounce.start())
        self.status_combo = self._combo([("", tr("history.all_status")), ("success", tr("status.success")),
                                         ("failed", tr("status.failed")), ("cancelled", tr("status.cancelled"))])
        self.from_combo = self._combo([("", tr("history.all_from"))] + [(f, f.upper()) for f in (*CATEGORY_ORDER, "image")])
        self.to_combo = self._combo([("", tr("history.all_to"))] + [(f, f.upper()) for f in CATEGORY_ORDER])
        self.col.addLayout(hbox(self.search, self.status_combo, self.from_combo, self.to_combo))

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels([tr(k) for _s, k in COLUMNS])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(340)
        self.table.setAccessibleName(tr("history.title"))
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionsClickable(True)
        hdr.setSortIndicatorShown(True)
        hdr.sectionClicked.connect(self._header_clicked)
        self.table.itemSelectionChanged.connect(self._sel_changed)
        self.table.cellDoubleClicked.connect(lambda _r, _c: self.open_output())
        self.col.addWidget(self.table)
        self.empty = label(tr("history.empty"), "muted")
        self.col.addWidget(self.empty)

        self.open_btn = button(tr("convert.open_file"), slot=self.open_output)
        self.folder_btn = button(tr("convert.open_folder"), slot=self.show_folder)
        self.retry_btn = button(tr("history.retry"), slot=self.retry)
        self.delete_btn = button(tr("history.delete"), slot=self.delete_selected)
        self.col.addLayout(hbox(self.open_btn, self.folder_btn, self.retry_btn, self.delete_btn, stretch_last=True))
        self.col.addLayout(hbox(button(tr("history.export"), slot=self.export_csv),
                                button(tr("history.clear"), "danger", self.clear_history), stretch_last=True))
        self.col.addWidget(label(tr("history.privacy_note"), "muted"))
        self._sel_changed()

    def _combo(self, items):
        c = QComboBox()
        for data, text in items:
            c.addItem(text, data)
        c.currentIndexChanged.connect(lambda _i: self.refresh())
        c.setAccessibleName(items[0][1])
        return c

    def on_show(self) -> None:
        self.refresh()

    def _header_clicked(self, col: int) -> None:
        key = COLUMNS[col][0]
        if key is None:
            return
        self.descending = (not self.descending) if key == self.sort_key else (key == "started_at")
        self.sort_key = key
        self.table.horizontalHeader().setSortIndicator(col, Qt.SortOrder.DescendingOrder if self.descending else Qt.SortOrder.AscendingOrder)
        self.refresh()

    def refresh(self) -> None:
        self.records = self.ctx.history.query(
            search=self.search.text().strip(), status=self.status_combo.currentData() or "",
            input_format=self.from_combo.currentData() or "", output_format=self.to_combo.currentData() or "",
            sort=self.sort_key, descending=self.descending, limit=1000)
        self.table.setRowCount(len(self.records))
        for r, rec in enumerate(self.records):
            when = datetime.fromisoformat(rec.started_at).astimezone().strftime("%Y-%m-%d %H:%M") if rec.started_at else ""
            detail = rec.error_summary or (self.tr_("convert.notes", n=rec.warnings_count) if rec.warnings_count else "")
            cells = [when, rec.input_name, rec.input_format.upper(), rec.output_format.upper(), self.tr_(f"status.{rec.status}"),
                     f"{rec.duration_ms / 1000:.1f} s", detail]
            for c, text in enumerate(cells):
                self.table.setItem(r, c, QTableWidgetItem(text))
        self.empty.setVisible(not self.records)
        self._sel_changed()

    def _current(self):
        row = self.table.currentRow()
        return self.records[row] if 0 <= row < len(self.records) else None

    def _sel_changed(self) -> None:
        rec = self._current()
        has_out = bool(rec and rec.output_path and Path(rec.output_path).exists())
        self.open_btn.setEnabled(has_out)
        self.folder_btn.setEnabled(has_out)
        self.retry_btn.setEnabled(bool(rec and Path(rec.input_path).exists()))
        self.delete_btn.setEnabled(rec is not None)

    def open_output(self) -> None:
        rec = self._current()
        if rec and rec.output_path and Path(rec.output_path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(rec.output_path))

    def show_folder(self) -> None:
        rec = self._current()
        if rec and rec.output_path:
            reveal_in_file_manager(Path(rec.output_path))

    def retry(self) -> None:
        rec = self._current()
        if rec:
            self.retry_requested.emit(rec.input_path, rec.input_format, rec.output_format)

    def delete_selected(self) -> None:
        rec = self._current()
        if rec and rec.id is not None:
            self.ctx.history.delete(rec.id)
            self.refresh()

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, self.tr_("history.export"), str(Path.home() / "proconvert-history.csv"), "CSV (*.csv)")
        if path:
            n = self.ctx.history.export_csv(path, self.records)
            self.window().statusBar().showMessage(self.tr_("history.exported", n=n), 5000)

    def clear_history(self) -> None:
        if QMessageBox.question(self, self.tr_("history.clear"), self.tr_("history.clear_confirm")) == QMessageBox.StandardButton.Yes:
            self.ctx.history.clear()
            self.refresh()
