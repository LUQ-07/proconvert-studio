"""Images -> PDF / Word: add, preview, reorder, remove, choose page options, convert."""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QProgressBar, QVBoxLayout, QWidget)

from ...converters import ocr
from ...converters.image_tools import SUPPORTED_EXTENSIONS, ImageLayout, check_image_file, make_thumbnail
from ...core.errors import CancelledError, ConversionError
from ...history.db import HistoryRecord
from ...utils.files import reveal_in_file_manager
from ..widgets.common import Card, DropZone, button, hbox, label
from ..workers import ImageConversionThread
from .base import Page

IMAGE_FILTER = "Images (" + " ".join("*" + e for e in SUPPORTED_EXTENSIONS) + ")"
PATH_ROLE = Qt.ItemDataRole.UserRole


class ImagesPage(Page):
    def __init__(self, ctx, main_window) -> None:
        super().__init__(ctx)
        self.main = main_window
        self._thread: ImageConversionThread | None = None
        self._started = 0.0
        self._paths_in_job: list[str] = []
        tr = self.tr_
        s = ctx.settings

        self.col.addWidget(label(tr("images.title"), "h1"))
        self.col.addWidget(label(tr("images.intro"), "muted"))

        self.drop = DropZone(tr("images.drop_title"), tr("images.drop_hint"), tr("images.add"))
        self.drop.files_dropped.connect(self.add_files)
        self.drop.browse_requested.connect(self.browse)
        self.col.addWidget(self.drop)

        # ---- list + preview
        self.col.addWidget(label(tr("images.list"), "h2"))
        self.count_label = label("", "muted")
        self.col.addWidget(self.count_label)
        self.list = QListWidget()
        self.list.setIconSize(QSize(64, 64))
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list.setMinimumHeight(230)
        self.list.setAccessibleName(tr("images.list"))
        self.list.currentItemChanged.connect(lambda _cur, _prev: self._show_preview())
        self.list.model().rowsMoved.connect(lambda *_a: self._refresh_state())
        self.preview = label(tr("images.no_selection"), "muted")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(280, 230)
        self.preview.setAccessibleName(tr("images.preview"))
        self.col.addLayout(hbox(self.list, self.preview, spacing=14))
        self.up_btn = button(tr("images.up"), slot=lambda: self._move(-1))
        self.down_btn = button(tr("images.down"), slot=lambda: self._move(1))
        self.remove_btn = button(tr("images.remove"), slot=self.remove_selected)
        self.clear_btn = button(tr("images.clear"), "danger", self.clear_all)
        self.col.addLayout(hbox(self.up_btn, self.down_btn, self.remove_btn, self.clear_btn, stretch_last=True))

        # ---- options
        self.col.addWidget(label(tr("images.options"), "h2"))
        card = Card()
        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setVerticalSpacing(12)

        def combo(items):
            c = QComboBox()
            for data, text in items:
                c.addItem(text, data)
            return c

        self.fmt_combo = combo([("pdf", tr("images.fmt_pdf")), ("docx", tr("images.fmt_docx")), ("pptx", tr("images.fmt_pptx")),
                                ("xlsx", tr("images.fmt_xlsx"))])
        self.size_combo = combo([("A4", tr("images.size_a4")), ("Letter", tr("images.size_letter")), ("Fit", tr("images.size_fit"))])
        self.size_combo.setCurrentIndex(max(self.size_combo.findData(s.page_size), 0))
        self.orient_combo = combo([("auto", tr("images.or_auto")), ("portrait", tr("images.or_portrait")), ("landscape", tr("images.or_landscape"))])
        self.margin_spin = QDoubleSpinBox()
        self.margin_spin.setRange(0, 50)
        self.margin_spin.setDecimals(1)
        self.margin_spin.setSingleStep(1)
        self.margin_spin.setValue(10)
        self.margin_spin.setSuffix(" mm")
        self.pos_combo = combo([("center", tr("images.pos_center")), ("top", tr("images.pos_top"))])
        self.no_upscale = QCheckBox(tr("images.no_upscale"))
        self.lang_edit = QLineEdit(s.ocr_language)
        self.lang_edit.setAccessibleName(tr("images.ocr_language"))
        self.lang_edit.setToolTip(tr("images.ocr_language_tip"))
        self.excel_hint = label(tr("images.excel_hint"), "muted")
        self.ocr_note = label(tr("settings.ocr_found") if ocr.is_available() else tr("images.ocr_unavailable"),
                              "ok" if ocr.is_available() else "warn")
        for key, widget in (("images.format", self.fmt_combo), ("images.page_size", self.size_combo), ("images.orientation", self.orient_combo),
                            ("images.margins", self.margin_spin), ("images.position", self.pos_combo)):
            widget.setAccessibleName(tr(key))
            form.addRow(label(tr(key), "h3"), widget)
        form.addRow(self.no_upscale)
        form.addRow(label(tr("images.ocr_language"), "h3"), self.lang_edit)
        form.addRow(self.excel_hint)
        form.addRow(self.ocr_note)
        self.size_combo.currentIndexChanged.connect(self._size_changed)
        self.fmt_combo.currentIndexChanged.connect(self._format_changed)
        self.col.addWidget(card)

        # ---- output
        self.col.addWidget(label(tr("images.output"), "h2"))
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText(tr("images.output_placeholder"))
        self.out_edit.setAccessibleName(tr("images.output"))
        self.col.addLayout(hbox(self.out_edit, button(tr("images.choose_output"), slot=self.choose_output)))

        self.convert_btn = button(tr("images.convert"), "primary", self.start)
        self.cancel_btn = button(tr("images.cancel"), slot=self.cancel)
        self.cancel_btn.hide()
        self.col.addLayout(hbox(self.convert_btn, self.cancel_btn, stretch_last=True))
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setAccessibleName(tr("images.running", detail=""))
        self.progress.hide()
        self.progress_text = label("", "muted")
        self.progress_text.hide()
        self.col.addWidget(self.progress)
        self.col.addWidget(self.progress_text)
        self.result_box = QVBoxLayout()
        self.result_box.setSpacing(8)
        self.col.addLayout(self.result_box)
        self.col.addStretch(1)
        self._update_option_state()
        self._refresh_state()

    # ------------------------------------------------------------------ state
    @property
    def is_busy(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def shutdown(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            self._thread.cancel()
            self._thread.wait(15000)

    def paths(self) -> list[str]:
        return [self.list.item(i).data(PATH_ROLE) for i in range(self.list.count())]

    def _refresh_state(self) -> None:
        n = self.list.count()
        self.count_label.setText(self.tr_("images.count", count=n))
        busy = self.is_busy
        row = self.list.currentRow()
        self.up_btn.setEnabled(not busy and row > 0)
        self.down_btn.setEnabled(not busy and 0 <= row < n - 1)
        self.remove_btn.setEnabled(not busy and row >= 0)
        self.clear_btn.setEnabled(not busy and n > 0)
        self.convert_btn.setEnabled(not busy and n > 0)

    def _size_changed(self) -> None:
        self._update_option_state()

    def _update_option_state(self) -> None:
        """Page options only apply to PDF/Word/PowerPoint; the OCR options only to the Excel table scan."""
        excel = self.fmt_combo.currentData() == "xlsx"
        for w in (self.size_combo, self.margin_spin, self.pos_combo, self.no_upscale):
            w.setEnabled(not excel)
        self.orient_combo.setEnabled(not excel and self.size_combo.currentData() != "Fit")   # "Fit to image" has no orientation choice
        for w in (self.lang_edit, self.excel_hint, self.ocr_note):
            w.setVisible(excel)

    def _format_changed(self) -> None:
        self._update_option_state()
        text = self.out_edit.text().strip()
        if text:
            self.out_edit.setText(str(Path(text).with_suffix("." + self.fmt_combo.currentData())))

    def _start_dir(self) -> str:
        d = self.ctx.settings.output_dir
        return d if d and Path(d).is_dir() else str(Path.home())

    # ------------------------------------------------------------------ adding / removing / ordering
    def browse(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, self.tr_("images.add"), self._start_dir(), IMAGE_FILTER + ";;" + self.tr_("convert.all_files") + " (*)")
        if files:
            self.add_files(files)

    def add_files(self, paths: list[str]) -> None:
        if self.is_busy:
            return
        rejected: list[str] = []
        existing = set(self.paths())
        for raw in paths:
            try:
                p = check_image_file(raw)
                png = make_thumbnail(p, 128)             # also proves the file really is a readable image
            except ConversionError:
                rejected.append(Path(raw).name)
                continue
            if str(p) in existing:
                continue
            pm = QPixmap()
            pm.loadFromData(png)
            item = QListWidgetItem(QIcon(pm), p.name)
            item.setData(PATH_ROLE, str(p))
            item.setToolTip(str(p))
            self.list.addItem(item)
            existing.add(str(p))
        if rejected:
            shown = ", ".join(rejected[:5]) + (" ..." if len(rejected) > 5 else "")
            QMessageBox.warning(self, self.tr_("images.title"), self.tr_("images.rejected", names=shown))
        if self.list.count() and not self.out_edit.text().strip():
            first = Path(self.paths()[0])
            self.out_edit.setText(str(Path(self._start_dir() if self.ctx.settings.output_dir else first.parent) / (first.stem + "." + self.fmt_combo.currentData())))
        if self.list.currentRow() < 0 and self.list.count():
            self.list.setCurrentRow(0)
        self._refresh_state()

    def remove_selected(self) -> None:
        row = self.list.currentRow()
        if row >= 0 and not self.is_busy:
            self.list.takeItem(row)
            self._show_preview()
            self._refresh_state()

    def clear_all(self) -> None:
        if not self.is_busy:
            self.list.clear()
            self._show_preview()
            self._refresh_state()

    def _move(self, delta: int) -> None:
        row = self.list.currentRow()
        new = row + delta
        if self.is_busy or row < 0 or not 0 <= new < self.list.count():
            return
        item = self.list.takeItem(row)
        self.list.insertItem(new, item)
        self.list.setCurrentRow(new)
        self._refresh_state()

    def _show_preview(self) -> None:
        item = self.list.currentItem()
        if item is None:
            self.preview.setPixmap(QPixmap())
            self.preview.setText(self.tr_("images.no_selection"))
        else:
            try:
                pm = QPixmap()
                pm.loadFromData(make_thumbnail(item.data(PATH_ROLE), 480))
                self.preview.setText("")
                self.preview.setPixmap(pm)
            except ConversionError as exc:
                self.preview.setPixmap(QPixmap())
                self.preview.setText(exc.user_message)
        self._refresh_state()

    # ------------------------------------------------------------------ output
    def choose_output(self) -> None:
        fmt = self.fmt_combo.currentData()
        flt = {"pdf": "PDF (*.pdf)", "docx": "Word (*.docx)", "pptx": "PowerPoint (*.pptx)", "xlsx": "Excel (*.xlsx)"}[fmt]
        start = self.out_edit.text().strip() or str(Path(self._start_dir()) / ("images." + fmt))
        path, _ = QFileDialog.getSaveFileName(self, self.tr_("images.output"), start, flt)
        if path:
            self.out_edit.setText(str(Path(path).with_suffix("." + fmt)))

    def layout_options(self) -> ImageLayout:
        return ImageLayout(page_size=self.size_combo.currentData(), orientation=self.orient_combo.currentData(),
                           margin_mm=float(self.margin_spin.value()), position=self.pos_combo.currentData(),
                           allow_upscale=not self.no_upscale.isChecked())

    # ------------------------------------------------------------------ run
    def start(self) -> None:
        tr = self.tr_
        if self.is_busy:
            return
        if not self.list.count():
            QMessageBox.information(self, tr("images.title"), tr("images.need_images"))
            return
        text = self.out_edit.text().strip()
        if not text:
            QMessageBox.information(self, tr("images.title"), tr("images.need_output"))
            return
        out = Path(text)
        fmt = self.fmt_combo.currentData()
        overwrite = False
        if out.exists():
            if QMessageBox.question(self, tr("images.title"), tr("images.overwrite_confirm", name=out.name)) != QMessageBox.StandardButton.Yes:
                return
            overwrite = True
        self.clear(self.result_box)
        self._paths_in_job = self.paths()
        self._thread = ImageConversionThread(self._paths_in_job, str(out), fmt, self.layout_options(), overwrite, self,
                                             language=self.lang_edit.text().strip() or "eng")
        self._thread.progress.connect(self._on_progress)
        self._thread.succeeded.connect(self._on_success)
        self._thread.failed.connect(self._on_failure)
        self._thread.finished.connect(self._on_finished)
        self._started = time.monotonic()
        self._set_running(True)
        self._thread.start()

    def cancel(self) -> None:
        if self._thread is not None:
            self.cancel_btn.setEnabled(False)
            self._thread.cancel()

    def _set_running(self, running: bool) -> None:
        for w in (self.drop, self.fmt_combo, self.size_combo, self.orient_combo, self.margin_spin, self.pos_combo, self.no_upscale,
                  self.lang_edit, self.out_edit, self.list):
            w.setEnabled(not running)
        self.cancel_btn.setVisible(running)
        self.cancel_btn.setEnabled(running)
        self.progress.setVisible(running)
        self.progress_text.setVisible(running)
        if running:
            self.progress.setValue(0)
            self.convert_btn.setEnabled(False)
            self.up_btn.setEnabled(False)
            self.down_btn.setEnabled(False)
            self.remove_btn.setEnabled(False)
            self.clear_btn.setEnabled(False)
        else:
            self._update_option_state()
            self._refresh_state()

    def _on_progress(self, fraction: float, detail: str) -> None:
        self.progress.setValue(int(fraction * 100))
        self.progress_text.setText(self.tr_("images.running", detail=detail))

    def _on_finished(self) -> None:
        self._set_running(False)
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None

    def _record(self, status: str, result=None, error: ConversionError | None = None) -> None:
        paths = self._paths_in_job
        if not paths:
            return
        name = Path(paths[0]).name + (f" (+{len(paths) - 1})" if len(paths) > 1 else "")
        ms = int((time.monotonic() - self._started) * 1000)
        self.ctx.history.add(HistoryRecord(name, paths[0], "image", self.fmt_combo.currentData(), status,
                                           str(result.output_path) if result else "", ms,
                                           error.user_message if error else "", len(result.warnings) if result else 0, ""))

    def _on_success(self, result) -> None:
        tr = self.tr_
        self._record("success", result=result)
        out = Path(result.output_path)
        self.clear(self.result_box)
        self.result_box.addWidget(label("\u2713  " + tr("images.done"), "ok"))
        self.result_box.addWidget(label(out.name, "h3"))
        self.result_box.addWidget(label(tr("images.pages", count=result.pages), "muted"))
        if result.warnings:
            shown = result.warnings[:8]
            more = len(result.warnings) - len(shown)
            self.result_box.addWidget(label(tr("images.warnings") + "\n" + "\n".join("\u2022 " + w for w in shown)
                                            + (("\n" + tr("convert.more_notes", n=more)) if more else ""), "warn"))
        self.result_box.addLayout(hbox(
            button(tr("images.open_file"), "primary", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))),
            button(tr("images.open_folder"), slot=lambda: reveal_in_file_manager(out)), stretch_last=True))
        self.main.notify(tr("images.done"), out.name)
        if self.ctx.settings.open_folder_after:
            reveal_in_file_manager(out)

    def _on_failure(self, err: ConversionError) -> None:
        tr = self.tr_
        if isinstance(err, CancelledError):
            self._record("cancelled", error=err)
            self.main.statusBar().showMessage(tr("images.cancelled"), 6000)
            self.result_box.addWidget(label(tr("images.cancelled"), "muted"))
            return
        self._record("failed", error=err)
        self.clear(self.result_box)
        self.result_box.addWidget(label("\u2715  " + tr("images.error_title"), "err"))
        self.result_box.addWidget(label(err.user_message, "h3"))
        self.result_box.addWidget(label(tr("convert.what_to_try") + " " + err.troubleshooting, "muted"))

    def add_from_history(self, path: str) -> None:
        """Used by the History 'retry' action: put the first image of that entry back into the list."""
        if Path(path).exists():
            self.add_files([path])
