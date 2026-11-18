"""Batch conversion screen."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QHeaderView, QLineEdit, QMessageBox,
                               QProgressBar, QTableWidget, QTableWidgetItem)

from ...core.capabilities import CATEGORY_ORDER, route_for
from ...core.errors import ConversionError
from ...core.security import FORMAT_LABELS, extension_format
from ...history.db import HistoryRecord
from ...utils.files import reveal_in_file_manager
from ...workers.batch import FINISHED, BatchItem, BatchQueue, ItemStatus, plan_target
from ..widgets.common import button, hbox, label
from ..workers import BatchBridge
from .base import Page

COLS = 4


class BatchPage(Page):
    def __init__(self, ctx, main_window) -> None:
        super().__init__(ctx)
        self.main = main_window
        tr = self.tr_
        self.queue: BatchQueue | None = None
        self.rows: dict[int, int] = {}
        self.recorded: set[int] = set()
        self.bridge = BatchBridge()
        self.bridge.item_changed.connect(self._on_item)
        self._notified = False
        self.setAcceptDrops(True)

        self.col.addWidget(label(tr("batch.title"), "h1"))
        self.col.addWidget(label(tr("batch.subtitle"), "muted"))

        self.fmt_combo = QComboBox()
        for f in CATEGORY_ORDER:
            self.fmt_combo.addItem(FORMAT_LABELS[f], f)
        self.fmt_combo.setAccessibleName(tr("batch.output_format"))
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText(tr("batch.folder_placeholder"))
        self.folder_edit.setAccessibleName(tr("batch.folder"))
        self.col.addLayout(hbox(label(tr("batch.output_format"), "h3", wrap=False), self.fmt_combo,
                                label(tr("batch.folder"), "h3", wrap=False), self.folder_edit,
                                button(tr("convert.choose_folder"), slot=self._choose_folder)))

        self.table = QTableWidget(0, COLS)
        self.table.setHorizontalHeaderLabels([tr("batch.col_file"), tr("batch.col_from"), tr("batch.col_status"), tr("batch.col_detail")])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(260)
        self.table.setAccessibleName(tr("batch.title"))
        self.col.addWidget(self.table)

        self.add_btn = button(tr("batch.add"), slot=self.add_files)
        self.remove_btn = button(tr("batch.remove"), slot=self.remove_selected)
        self.clear_btn = button(tr("batch.clear"), slot=self.clear_queue)
        self.col.addLayout(hbox(self.add_btn, self.remove_btn, self.clear_btn, stretch_last=True))

        self.start_btn = button(tr("batch.start"), "primary", self.start)
        self.cancel_btn = button(tr("batch.cancel"), "danger", self.cancel)
        self.retry_btn = button(tr("batch.retry"), slot=self.retry)
        self.open_btn = button(tr("convert.open_folder"), slot=self.open_folder)
        self.col.addLayout(hbox(self.start_btn, self.cancel_btn, self.retry_btn, self.open_btn, stretch_last=True))

        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.summary = label("", "muted")
        self.col.addWidget(self.bar)
        self.col.addWidget(self.summary)
        self.col.addWidget(label(tr("batch.note"), "muted"))
        self.col.addStretch(1)
        self._refresh_buttons()

    # ------------------------------------------------------------------ queue
    def _queue(self) -> BatchQueue:
        if self.queue is None:
            self.queue = BatchQueue(self.ctx.settings.max_concurrent_jobs, self.bridge.callback, temp_root=self.ctx.temp.root)
        self.queue.max_workers = self.ctx.settings.max_concurrent_jobs
        return self.queue

    @property
    def is_busy(self) -> bool:
        return bool(self.queue and self.queue.is_active)

    def shutdown(self) -> None:
        if self.queue:
            self.queue.cancel_all()
            self.queue.wait(8)

    def _choose_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, self.tr_("convert.choose_folder"))
        if d:
            self.folder_edit.setText(d)

    def add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, self.tr_("batch.add"), str(Path.home()),
                                                "Documents (*.pdf *.docx *.pptx *.xlsx)")
        self.add_paths(paths)

    def add_paths(self, paths: list[str]) -> None:
        dst = self.fmt_combo.currentData()
        out = Path(self.folder_edit.text()) if self.folder_edit.text().strip() else None
        q = self._queue()
        for p in paths:
            src = Path(p)
            src_fmt = extension_format(src)
            skip = ""
            if src_fmt == dst:
                skip = self.tr_("batch.skip_same")
            elif route_for(src_fmt, dst) is None:
                skip = self.tr_("batch.skip_unsupported")
            target = plan_target(src, out, dst, overwrite=False)
            item = q.add(src, target, self.ctx.settings.to_options(), skip_reason=skip)
            self._ensure_row(item)
        self._refresh_buttons()

    def _ensure_row(self, item: BatchItem) -> int:
        if item.id not in self.rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.rows[item.id] = row
            self.table.setItem(row, 0, QTableWidgetItem(item.source.name))
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, item.id)
            self.table.setItem(row, 1, QTableWidgetItem(extension_format(item.source).upper()))
        return self.rows[item.id]

    def _rebuild_rows(self) -> None:
        self.table.setRowCount(0)
        self.rows.clear()
        if self.queue:
            for it in self.queue.items:
                self._ensure_row(it)
                self._paint(it)

    def _paint(self, item: BatchItem) -> None:
        row = self._ensure_row(item)
        status = self.tr_(f"batch.status.{item.status.value}")
        if item.status == ItemStatus.RUNNING and item.progress is not None:
            status += f" {int(item.progress * 100)}%"
        self.table.setItem(row, 2, QTableWidgetItem(status))
        detail = item.message
        if item.status == ItemStatus.DONE and item.result and item.result.warnings:
            detail = self.tr_("convert.notes", n=len(item.result.warnings))
        self.table.setItem(row, 3, QTableWidgetItem(detail))

    def _on_item(self, item: BatchItem) -> None:
        self._paint(item)
        if item.status in (ItemStatus.DONE, ItemStatus.FAILED, ItemStatus.CANCELLED) and item.id not in self.recorded:
            self.recorded.add(item.id)
            err = (item.error or {}).get("message", "") if item.status != ItemStatus.DONE else ""
            res = item.result
            self.ctx.history.add(HistoryRecord(
                item.source.name, str(item.source), extension_format(item.source), extension_format(item.target),
                "success" if item.status == ItemStatus.DONE else item.status.value, str(item.target) if res else "",
                int(item.duration_s * 1000), err, len(res.warnings) if res else 0, res.status if res else ""))
        q = self.queue
        if q:
            self.bar.setValue(int(q.overall_fraction() * 1000))
            s = q.summary()
            self.summary.setText(self.tr_("batch.summary", done=s["done"], failed=s["failed"], cancelled=s["cancelled"],
                                          pending=s["pending"] + s["running"], skipped=s["skipped"]))
            if all(i.status in FINISHED for i in q.items):
                self._refresh_buttons(finished=True)
                if not self._notified:
                    self._notified = True
                    self.main.notify(self.tr_("batch.finished"), self.summary.text())

    def _selected_ids(self) -> list[int]:
        rows = {i.row() for i in self.table.selectedIndexes()}
        return [self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in rows]

    def remove_selected(self) -> None:
        if self.queue:
            for i in self._selected_ids():
                self.queue.remove(i)
            self._rebuild_rows()
        self._refresh_buttons()

    def clear_queue(self) -> None:
        if self.queue:
            self.queue.clear()
            self._rebuild_rows()
        self._refresh_buttons()

    def start(self) -> None:
        if self.queue:
            self._notified = False
            self.queue.start()
        self._refresh_buttons()

    def cancel(self) -> None:
        if self.queue:
            self.queue.cancel_all()

    def retry(self) -> None:
        if self.queue:
            for it in self.queue.items:
                self.recorded.discard(it.id)
            self.queue.retry_failed()
        self._refresh_buttons()

    def open_folder(self) -> None:
        if self.queue:
            done = [i for i in self.queue.items if i.status == ItemStatus.DONE]
            if done:
                reveal_in_file_manager(done[-1].target)
            elif self.folder_edit.text().strip():
                reveal_in_file_manager(Path(self.folder_edit.text()) / "x")

    def _refresh_buttons(self, finished: bool = False) -> None:
        has = bool(self.queue and self.queue.items)
        active = self.is_busy and not finished
        self.start_btn.setEnabled(has and not active)
        self.cancel_btn.setEnabled(active)
        self.retry_btn.setEnabled(has and not active)
        self.remove_btn.setEnabled(has and not active)
        self.clear_btn.setEnabled(has and not active)

    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:  # noqa: N802
        self.add_paths([u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()])
