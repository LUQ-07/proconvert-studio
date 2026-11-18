"""Single-file conversion screen."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog,
                               QLineEdit, QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget)

from ...converters import ocr
from ...core.capabilities import CATEGORY_ORDER, route_for, targets_for
from ...core.errors import CancelledError, ConversionError, PasswordProtectedError
from ...core.security import FORMAT_LABELS, validate_source, validate_target
from ...history.db import HistoryRecord
from ...utils.files import human_size, open_with_default_app, reveal_in_file_manager, sanitize_filename
from ...workers.process_job import ConversionJob
from ..widgets.common import Card, DropZone, badge, button, hbox, label, repolish
from ..workers import ConversionThread
from .base import Page

FILTERS = {"pdf": "*.pdf", "docx": "*.docx", "pptx": "*.pptx", "xlsx": "*.xlsx"}


class ConvertPage(Page):
    history_changed = Signal()
    busy_changed = Signal(bool)

    def __init__(self, ctx, main_window) -> None:
        super().__init__(ctx)
        self.main = main_window
        tr = self.tr_
        self.category = "pdf"
        self.info = None
        self.thread: ConversionThread | None = None
        self._password: str | None = None
        self._last_launch: tuple | None = None
        self._clock = QElapsedTimer()
        self._ticker = QTimer(self)
        self._ticker.setInterval(500)
        self._ticker.timeout.connect(self._tick)

        self.col.addWidget(label(tr("convert.title"), "h1"))
        self.col.addWidget(label(tr("convert.subtitle"), "muted"))

        # 1. category selector
        row = QHBoxLayout()
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.cat_buttons: dict[str, QPushButton] = {}
        for fmt in CATEGORY_ORDER:
            b = QPushButton(tr(f"category.{fmt}"))
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setAccessibleName(tr(f"category.{fmt}"))
            b.clicked.connect(lambda _c=False, f=fmt: self.select_category(f))
            self.group.addButton(b)
            self.cat_buttons[fmt] = b
            row.addWidget(b)
        row.addStretch(1)
        self.col.addLayout(row)

        # 2. source
        self.drop = DropZone(tr("convert.drop_title"), tr("convert.drop_hint"), tr("convert.browse"))
        self.drop.files_dropped.connect(lambda paths: self.set_source(paths[0]))
        self.drop.browse_requested.connect(self.browse)
        self.col.addWidget(self.drop)
        self.source_error = label("", "err")
        self.source_error.hide()
        self.col.addWidget(self.source_error)

        self.source_card = Card()
        sc = QHBoxLayout(self.source_card)
        sc.setContentsMargins(18, 14, 18, 14)
        self.src_badge = badge("pdf")
        self.src_name = label("", "h3")
        self.src_detail = label("", "muted")
        text = QVBoxLayout()
        text.addWidget(self.src_name)
        text.addWidget(self.src_detail)
        sc.addWidget(self.src_badge)
        sc.addLayout(text, 1)
        self.change_btn = button(tr("convert.change_file"), slot=self.browse)
        sc.addWidget(self.change_btn)
        self.source_card.hide()
        self.col.addWidget(self.source_card)

        # 3. options
        self.options_card = Card()
        oc = QVBoxLayout(self.options_card)
        oc.setContentsMargins(18, 16, 18, 16)
        oc.setSpacing(10)
        oc.addWidget(label(tr("convert.output_format"), "h3"))
        self.fmt_combo = QComboBox()
        self.fmt_combo.setAccessibleName(tr("convert.output_format"))
        self.fmt_combo.currentIndexChanged.connect(self._format_changed)
        oc.addWidget(self.fmt_combo)
        self.route_banner = QFrame()
        self.route_banner.setObjectName("Banner")
        rb = QVBoxLayout(self.route_banner)
        self.route_text = label("", "warn")
        rb.addWidget(self.route_text)
        oc.addWidget(self.route_banner)

        self.pdf_opts = QWidget()
        po = QVBoxLayout(self.pdf_opts)
        po.setContentsMargins(0, 0, 0, 0)
        self.pages_edit = QLineEdit()
        self.pages_edit.setPlaceholderText(tr("convert.pages_placeholder"))
        self.pages_edit.setAccessibleName(tr("convert.pages"))
        self.ocr_check = QCheckBox(tr("convert.use_ocr"))
        po.addWidget(label(tr("convert.pages"), "h3"))
        po.addWidget(self.pages_edit)
        po.addWidget(self.ocr_check)
        oc.addWidget(self.pdf_opts)

        oc.addWidget(label(tr("convert.save_to"), "h3"))
        self.folder_edit = QLineEdit()
        self.folder_edit.setAccessibleName(tr("convert.folder"))
        self.folder_edit.setPlaceholderText(tr("convert.folder_placeholder"))
        self.folder_btn = button(tr("convert.choose_folder"), slot=self.choose_folder)
        oc.addLayout(hbox(self.folder_edit, self.folder_btn))
        self.name_edit = QLineEdit()
        self.name_edit.setAccessibleName(tr("convert.file_name"))
        self.ext_label = label("", "muted", wrap=False)
        oc.addLayout(hbox(label(tr("convert.file_name"), "muted", wrap=False), self.name_edit, self.ext_label))
        self.options_card.hide()
        self.col.addWidget(self.options_card)

        # 4. actions
        self.convert_btn = button(tr("convert.convert"), "primary", self.start)
        self.convert_btn.setAccessibleName(tr("convert.convert"))
        self.convert_btn.setEnabled(False)
        self.cancel_btn = button(tr("convert.cancel"), "danger", self.cancel)
        self.cancel_btn.hide()
        self.col.addLayout(hbox(self.convert_btn, self.cancel_btn, stretch_last=True))

        # 5. progress
        self.progress_card = Card()
        pc = QVBoxLayout(self.progress_card)
        pc.setContentsMargins(18, 16, 18, 16)
        self.stage_label = label("", "h3")
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.elapsed_label = label("", "muted")
        pc.addWidget(self.stage_label)
        pc.addWidget(self.bar)
        pc.addWidget(self.elapsed_label)
        self.progress_card.hide()
        self.col.addWidget(self.progress_card)

        # 6. result
        self.result_card = Card()
        self.result_layout = QVBoxLayout(self.result_card)
        self.result_layout.setContentsMargins(18, 16, 18, 16)
        self.result_card.hide()
        self.col.addWidget(self.result_card)
        self.col.addStretch(1)

        self.select_category("pdf")

    # ------------------------------------------------------------------ public hooks
    def open_with(self, category: str | None = None, path: str | None = None, target: str | None = None) -> None:
        if category:
            self.select_category(category)
        if path:
            self.set_source(path)
            if target and self.info:
                idx = self.fmt_combo.findData(target)
                if idx >= 0:
                    self.fmt_combo.setCurrentIndex(idx)

    @property
    def is_busy(self) -> bool:
        return self.thread is not None and self.thread.isRunning()

    def shutdown(self) -> None:
        if self.thread is not None and self.thread.isRunning():
            self.thread.cancel()
            self.thread.wait(8000)

    # ------------------------------------------------------------------ category / source
    def select_category(self, fmt: str, keep_source: bool = False) -> None:
        if self.is_busy:
            return
        self.category = fmt
        self.cat_buttons[fmt].setChecked(True)
        self.drop.set_texts(self.tr_("convert.drop_title"), self.tr_("convert.drop_hint", ext=f".{fmt}"), self.tr_("convert.browse"))
        self.pdf_opts.setVisible(fmt == "pdf")
        self.ocr_check.setChecked(self.ctx.settings.ocr_enabled)
        self.ocr_check.setEnabled(ocr.is_available())
        self.ocr_check.setToolTip("" if ocr.is_available() else self.tr_("convert.ocr_missing"))
        self.fmt_combo.blockSignals(True)
        self.fmt_combo.clear()
        for dst in targets_for(fmt):
            self.fmt_combo.addItem(FORMAT_LABELS[dst], dst)
        last = self.ctx.settings.last_formats.get(fmt) if self.ctx.settings.remember_last_format else None
        idx = self.fmt_combo.findData(last) if last else -1
        self.fmt_combo.setCurrentIndex(max(idx, 0))
        self.fmt_combo.blockSignals(False)
        if not keep_source:
            self._clear_source()
        self._format_changed()

    def _clear_source(self) -> None:
        self.info = None
        self.source_card.hide()
        self.options_card.hide()
        self.drop.show()
        self.convert_btn.setEnabled(False)
        self.result_card.hide()
        self.progress_card.hide()
        self.source_error.hide()

    def browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self.tr_("convert.browse"), self._start_dir(),
                                              f"{FORMAT_LABELS[self.category]} ({FILTERS[self.category]});;{self.tr_('convert.all_files')} (*)")
        if path:
            self.set_source(path)

    def _start_dir(self) -> str:
        d = self.ctx.settings.output_dir
        return d if d and Path(d).is_dir() else str(Path.home())

    def set_source(self, path: str) -> None:
        if self.is_busy:
            return
        self.result_card.hide()
        try:
            info = validate_source(path)
        except ConversionError as exc:
            self.source_error.setText(f"{exc.user_message}  {exc.troubleshooting}")
            self.source_error.show()
            return
        self.source_error.hide()
        if info.fmt != self.category:
            self.select_category(info.fmt, keep_source=True)
            self.main.statusBar().showMessage(self.tr_("convert.category_switched", name=self.tr_(f"category.{info.fmt}")), 5000)
        self.info = info
        self._password = None
        self.src_badge.setText(info.fmt.upper())
        self.src_badge.setProperty("kind", info.fmt)
        repolish(self.src_badge)
        self.src_name.setText(info.path.name)
        self.src_detail.setText(self.tr_("convert.file_detail", size=human_size(info.size), fmt=FORMAT_LABELS[info.fmt]))
        self.drop.hide()
        self.source_card.show()
        self.options_card.show()
        self.name_edit.setText(sanitize_filename(info.path.stem))
        out = self.ctx.settings.output_dir
        self.folder_edit.setText(out if out and Path(out).is_dir() else str(info.path.parent))
        self.convert_btn.setEnabled(True)
        self._format_changed()
        self.convert_btn.setFocus()

    def choose_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, self.tr_("convert.choose_folder"), self.folder_edit.text() or str(Path.home()))
        if d:
            self.folder_edit.setText(d)

    def _format_changed(self) -> None:
        dst = self.fmt_combo.currentData()
        if not dst:
            return
        self.ext_label.setText(f".{dst}")
        route = route_for(self.category, dst)
        show = bool(route and route.experimental and self.ctx.settings.show_experimental_warning)
        self.route_banner.setVisible(show)
        if show:
            self.route_text.setText(self.tr_("convert.experimental_note"))

    # ------------------------------------------------------------------ run
    def start(self) -> None:
        if self.is_busy or not self.info:
            return
        dst = self.fmt_combo.currentData()
        name = self.name_edit.text().strip()
        if name.lower().endswith(f".{dst}"):
            name = name[: -(len(dst) + 1)]
        folder = Path(self.folder_edit.text().strip() or self.info.path.parent)
        try:
            final = validate_target(folder / f"{name}.{dst}", self.info.path, dst, overwrite=True)
        except ConversionError as exc:
            self._show_error(exc)
            return
        overwrite = False
        if final.exists():
            if self.ctx.settings.overwrite_confirm:
                answer = QMessageBox.question(self, self.tr_("convert.overwrite_title"),
                                              self.tr_("convert.overwrite_text", name=final.name))
                if answer != QMessageBox.StandardButton.Yes:
                    return
            overwrite = True
        if self.ctx.settings.remember_last_format:
            last = dict(self.ctx.settings.last_formats)
            last[self.category] = dst
            self.ctx.update(last_formats=last)
        self._launch(final, overwrite)

    def _launch(self, final: Path, overwrite: bool) -> None:
        opts = self.ctx.settings.to_options()
        if self.category == "pdf":
            opts = replace(opts, pdf_pages=self.pages_edit.text().strip(), pdf_password=self._password,
                           ocr_enabled=self.ocr_check.isChecked() and ocr.is_available())
        self._last_launch = (final, overwrite)
        job = ConversionJob(self.info.path, final, opts, overwrite=overwrite, temp_root=self.ctx.temp.root)
        self.thread = ConversionThread(job, self)
        self.thread.progress.connect(self._on_progress)
        self.thread.succeeded.connect(self._on_success)
        self.thread.failed.connect(self._on_failure)
        self.thread.finished.connect(lambda t=self.thread: self._on_thread_finished(t))
        self._set_running(True)
        self._started_at = QElapsedTimer()
        self._started_at.start()
        self.thread.start()

    def cancel(self) -> None:
        if self.thread is not None and self.thread.isRunning():
            self.cancel_btn.setEnabled(False)
            self.stage_label.setText(self.tr_("convert.cancelling"))
            self.thread.cancel()

    def _set_running(self, running: bool) -> None:
        for w in (self.convert_btn, self.drop, self.change_btn, self.options_card, *self.cat_buttons.values()):
            w.setEnabled(not running)
        self.cancel_btn.setVisible(running)
        self.cancel_btn.setEnabled(True)
        self.progress_card.setVisible(running or self.progress_card.isVisible())
        if running:
            self.result_card.hide()
            self.bar.setRange(0, 0)
            self.stage_label.setText(self.tr_("stage.validating"))
            self._clock.start()
            self._ticker.start()
            self._tick()
        else:
            self._ticker.stop()
        self.busy_changed.emit(running)

    def _tick(self) -> None:
        secs = self._clock.elapsed() // 1000
        self.elapsed_label.setText(self.tr_("convert.elapsed", time=f"{secs // 60:d}:{secs % 60:02d}"))

    def _on_progress(self, ev) -> None:
        text = self.tr_(f"stage.{ev.stage}")
        if ev.detail:
            text = f"{text} - {ev.detail}"
        self.stage_label.setText(text)
        if ev.fraction is None:
            self.bar.setRange(0, 0)               # honest: this stage cannot be measured
        else:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(ev.fraction * 1000))

    def _on_thread_finished(self, finished_thread) -> None:
        if finished_thread is not self.thread:      # a retry already replaced it
            finished_thread.deleteLater()
            return
        self._set_running(False)
        self.thread = None
        finished_thread.deleteLater()

    def _record(self, status: str, result=None, error: ConversionError | None = None) -> None:
        info = self.info
        if info is None:
            return
        ms = int(self._started_at.elapsed()) if hasattr(self, "_started_at") else 0
        dst = self.fmt_combo.currentData() or ""
        self.ctx.history.add(HistoryRecord(
            info.path.name, str(info.path), info.fmt, dst, status,
            result.output_path if result else "", int(result.duration_s * 1000) if result else ms,
            (error.user_message if error else ""), len(result.warnings) if result else 0,
            result.status if result else "",
        ))
        self.history_changed.emit()

    def _on_success(self, result) -> None:
        self._record("success", result=result)
        tr = self.tr_
        self.clear(self.result_layout)
        s = result.stats
        self.result_layout.addWidget(label("\u2713  " + tr("convert.done"), "ok"))
        self.result_layout.addWidget(label(Path(result.output_path).name, "h3"))
        self.result_layout.addWidget(label(tr("convert.summary", sections=s["sections"], paragraphs=s["paragraphs"],
                                                  tables=s["tables"], images=s["pictures"], seconds=f"{result.duration_s:.1f}"), "muted"))
        if result.status == "experimental":
            self.result_layout.addWidget(label(tr("convert.experimental_review"), "warn"))
        if result.warnings:
            self.result_layout.addWidget(label(tr("convert.notes", n=len(result.warnings)), "h3"))
            shown = result.warnings[:8]
            more = len(result.warnings) - len(shown)
            self.result_layout.addWidget(label("\n".join("\u2022 " + w for w in shown) + (("\n" + tr("convert.more_notes", n=more)) if more else ""), "warn"))
        out = Path(result.output_path)
        self.result_layout.addLayout(hbox(
            button(tr("convert.open_file"), "primary", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))),
            button(tr("convert.open_folder"), slot=lambda: reveal_in_file_manager(out)),
            button(tr("convert.another"), slot=self._convert_another), stretch_last=True))
        self.result_card.show()
        self.progress_card.hide()
        self.main.notify(tr("convert.done"), out.name)
        if self.ctx.settings.open_folder_after:
            reveal_in_file_manager(out)

    def _convert_another(self) -> None:
        self._clear_source()

    def _on_failure(self, err: ConversionError) -> None:
        if isinstance(err, CancelledError):
            self._record("cancelled", error=err)
            self.progress_card.hide()
            self.main.statusBar().showMessage(self.tr_("convert.cancelled"), 6000)
            return
        if isinstance(err, PasswordProtectedError) and self.info and self.info.fmt == "pdf" and self._last_launch:
            pw, ok = QInputDialog.getText(self, self.tr_("convert.password_title"), err.user_message + "\n" + self.tr_("convert.password_prompt"),
                                          QLineEdit.EchoMode.Password)
            if ok and pw:
                self._password = pw
                QTimer.singleShot(0, lambda: self._launch(*self._last_launch))
                return
        self._record("failed", error=err)
        self.progress_card.hide()
        self._show_error(err)

    def _show_error(self, err: ConversionError) -> None:
        tr = self.tr_
        self.clear(self.result_layout)
        self.result_layout.addWidget(label("\u2715  " + tr("convert.failed"), "err"))
        self.result_layout.addWidget(label(err.user_message, "h3"))
        self.result_layout.addWidget(label(tr("convert.what_to_try") + " " + err.troubleshooting, "muted"))
        if err.technical:
            tech = label(err.technical, "muted")
            tech.hide()
            toggle = button(tr("convert.show_details"), "link")
            toggle.clicked.connect(lambda _c=False: tech.setVisible(not tech.isVisible()))
            self.result_layout.addWidget(toggle)
            self.result_layout.addWidget(tech)
        self.result_card.show()
