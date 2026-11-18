"""About: version, copyright and open-source licence, third-party notices. (Updates: download the new release.)"""
from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit, QVBoxLayout

from ... import __version__, config
from ...utils.paths import resource_path
from ..widgets.common import button, hbox, label
from .base import Page


class AboutPage(Page):
    def __init__(self, ctx) -> None:
        super().__init__(ctx)
        tr = self.tr_
        self.col.addWidget(label(config.APP_NAME, "h1"))
        self.col.addWidget(label(tr("about.version", version=__version__), "muted"))
        self.col.addWidget(label(tr("about.tagline"), ""))
        self.col.addWidget(label(tr("about.copyright", year=config.COPYRIGHT_YEAR, holder=config.COPYRIGHT_HOLDER), "muted"))
        self.col.addLayout(hbox(
            button(tr("about.notices"), slot=self.show_notices),
            button(tr("about.source_code"), slot=lambda: QDesktopServices.openUrl(QUrl(config.REPOSITORY_URL))),
            stretch_last=True))
        self.col.addStretch(1)

    def show_notices(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr_("about.notices"))
        dlg.resize(760, 560)
        lay = QVBoxLayout(dlg)
        box = QPlainTextEdit()
        box.setReadOnly(True)
        p = resource_path("assets/THIRD_PARTY_NOTICES.txt")
        box.setPlainText(p.read_text(encoding="utf-8") if p.exists() else self.tr_("about.notices_missing"))
        lay.addWidget(box)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.exec()
