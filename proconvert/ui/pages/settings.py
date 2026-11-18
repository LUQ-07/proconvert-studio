"""Settings screen. Every control saves immediately and validates through the settings store."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QLineEdit, QMessageBox,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from ...converters import ocr
from ...localization import available_languages
from ...services.diagnostics import export_diagnostics
from ...settings.store import AppSettings, CHOICES
from ...utils.files import human_size
from ..widgets.common import button, hbox, label
from .base import Page


class SettingsPage(Page):
    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        tr = self.tr_
        s = ctx.settings
        self.col.addWidget(label(tr("settings.title"), "h1"))
        tabs = QTabWidget()
        self.col.addWidget(tabs)

        def tab(title: str):
            w = QWidget()
            form = QFormLayout(w)
            form.setContentsMargins(20, 20, 20, 20)
            form.setVerticalSpacing(14)
            tabs.addTab(w, title)
            return form

        def check(key: str, text: str) -> QCheckBox:
            c = QCheckBox(text)
            c.setChecked(getattr(s, key))
            c.toggled.connect(lambda v, k=key: ctx.update(**{k: bool(v)}))
            return c

        def combo(key: str, items: list[tuple[str, str]]) -> QComboBox:
            c = QComboBox()
            for data, text in items:
                c.addItem(text, data)
            c.setCurrentIndex(max(c.findData(getattr(s, key)), 0))
            c.currentIndexChanged.connect(lambda _i, k=key, cb=c: ctx.update(**{k: cb.currentData()}))
            c.setAccessibleName(key)
            return c

        # ---- General
        g = tab(tr("settings.general"))
        self.out_edit = QLineEdit(s.output_dir)
        self.out_edit.setPlaceholderText(tr("settings.output_same"))
        self.out_edit.editingFinished.connect(lambda: ctx.update(output_dir=self._valid_dir(self.out_edit.text())))
        g.addRow(label(tr("settings.output_dir"), "h3"), hbox(self.out_edit, button(tr("convert.choose_folder"), slot=lambda: self._pick(self.out_edit, "output_dir"))))
        g.addRow(check("overwrite_confirm", tr("settings.overwrite_confirm")))
        g.addRow(check("open_folder_after", tr("settings.open_folder_after")))
        g.addRow(check("remember_last_format", tr("settings.remember_format")))
        g.addRow(check("notifications", tr("settings.notifications")))
        langs = []
        for lg in available_languages():
            suffix = "" if lg["reviewed"] and lg["complete"] else f" \u2014 {tr('settings.draft_translation')}"
            langs.append((lg["code"], lg["name"] + suffix))
        g.addRow(label(tr("settings.language"), "h3"), combo("language", langs))
        g.addRow(label(tr("settings.language_note"), "muted"))
        g.addRow(label(tr("settings.appearance"), "h3"),
                 combo("appearance", [("system", tr("settings.follow_system")), ("dark", tr("settings.dark")), ("light", tr("settings.light"))]))

        # ---- Conversion
        c = tab(tr("settings.conversion"))
        c.addRow(label(tr("settings.quality"), "h3"),
                 combo("quality", [("standard", tr("settings.q_standard")), ("high", tr("settings.q_high")), ("original", tr("settings.q_original"))]))
        c.addRow(label(tr("settings.page_size"), "h3"), combo("page_size", [("A4", "A4"), ("Letter", "Letter")]))
        c.addRow(check("ocr_enabled", tr("settings.ocr")))
        self.ocr_lang = QLineEdit(s.ocr_language)
        self.ocr_lang.editingFinished.connect(lambda: ctx.update(ocr_language=self.ocr_lang.text().strip() or "eng"))
        c.addRow(label(tr("settings.ocr_language"), "h3"), self.ocr_lang)
        c.addRow(label(tr("settings.ocr_found") if ocr.is_available() else tr("settings.ocr_missing"), "ok" if ocr.is_available() else "warn"))
        c.addRow(check("detect_columns", tr("settings.detect_columns")))
        c.addRow(check("strip_headers_footers", tr("settings.strip_headers")))
        c.addRow(check("show_experimental_warning", tr("settings.experimental_warning")))
        spin = QSpinBox()
        spin.setRange(1, 4)
        spin.setValue(s.max_concurrent_jobs)
        spin.valueChanged.connect(lambda v: ctx.update(max_concurrent_jobs=int(v)))
        spin.setAccessibleName(tr("settings.max_jobs"))
        c.addRow(label(tr("settings.max_jobs"), "h3"), spin)
        c.addRow(label(tr("settings.pages_note"), "muted"))

        # ---- Privacy
        p = tab(tr("settings.privacy"))
        p.addRow(label(tr("settings.local_only"), "ok"))
        p.addRow(label(tr("settings.local_only_detail"), "muted"))
        p.addRow(check("crash_reports_local", tr("settings.crash_local")))
        p.addRow(button(tr("settings.clear_history"), "danger", self._clear_history))
        self.temp_label = label("", "muted")
        p.addRow(hbox(button(tr("settings.clear_temp"), slot=self._clear_temp), self.temp_label))

        # ---- Advanced
        a = tab(tr("settings.advanced"))
        a.addRow(label(tr("settings.log_level"), "h3"), combo("log_level", [(lv, lv) for lv in CHOICES["log_level"]]))
        self.temp_edit = QLineEdit(s.temp_dir)
        self.temp_edit.setPlaceholderText(tr("settings.temp_default"))
        self.temp_edit.editingFinished.connect(lambda: ctx.update(temp_dir=self._valid_dir(self.temp_edit.text())))
        a.addRow(label(tr("settings.temp_dir"), "h3"), hbox(self.temp_edit, button(tr("convert.choose_folder"), slot=lambda: self._pick(self.temp_edit, "temp_dir"))))
        a.addRow(button(tr("settings.export_diag"), slot=self._export_diag))
        a.addRow(button(tr("settings.reset"), "danger", self._reset))
        self.col.addStretch(1)

    def on_show(self) -> None:
        self.temp_label.setText(human_size(self.ctx.temp.usage_bytes()))

    @staticmethod
    def _valid_dir(text: str) -> str:
        text = text.strip()
        return text if text and Path(text).is_dir() else ""

    def _pick(self, edit: QLineEdit, key: str) -> None:
        d = QFileDialog.getExistingDirectory(self, self.tr_("convert.choose_folder"), edit.text() or str(Path.home()))
        if d:
            edit.setText(d)
            self.ctx.update(**{key: d})

    def _clear_history(self) -> None:
        if QMessageBox.question(self, self.tr_("history.clear"), self.tr_("history.clear_confirm")) == QMessageBox.StandardButton.Yes:
            self.ctx.history.clear()

    def _clear_temp(self) -> None:
        freed = self.ctx.temp.clear_all()
        self.temp_label.setText(self.tr_("settings.freed", size=human_size(freed)))

    def _export_diag(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, self.tr_("settings.export_diag"), str(Path.home() / "proconvert-diagnostics.zip"), "ZIP (*.zip)")
        if path:
            export_diagnostics(path, self.ctx.settings)
            QMessageBox.information(self, self.tr_("settings.export_diag"), self.tr_("settings.diag_saved"))

    def _reset(self) -> None:
        if QMessageBox.question(self, self.tr_("settings.reset"), self.tr_("settings.reset_confirm")) == QMessageBox.StandardButton.Yes:
            self.ctx.update(**{k: v for k, v in AppSettings().__dict__.items() if k != "schema_version"})
            self.window().rebuild_pages()
