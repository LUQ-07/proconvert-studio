"""Qt application bootstrap."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .. import __version__, config
from ..localization import is_rtl
from ..utils.paths import resource_path
from .context import AppContext
from .main_window import MainWindow
from .theme import apply_theme


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(config.ORG_NAME)
    app.setDesktopFileName(config.APP_ID)
    icon_path = resource_path("assets/icon.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    ctx = AppContext()
    state = {"palette": apply_theme(app, ctx.settings.appearance)}
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft if is_rtl(ctx.settings.language) else Qt.LayoutDirection.LeftToRight)
    window = MainWindow(ctx, state["palette"])

    def restyle() -> None:
        state["palette"] = apply_theme(app, ctx.settings.appearance)
        window.palette_tokens = state["palette"]
        window.rebuild_pages()          # re-tints icons

    def relanguage() -> None:
        app.setLayoutDirection(Qt.LayoutDirection.RightToLeft if is_rtl(ctx.settings.language) else Qt.LayoutDirection.LeftToRight)
        window.rebuild_pages()

    ctx.appearance_changed.connect(restyle)
    ctx.language_changed.connect(relanguage)
    try:  # follow the OS when the user chose "Follow System"
        app.styleHints().colorSchemeChanged.connect(lambda _s: restyle() if ctx.settings.appearance == "system" else None)
    except AttributeError:
        pass
    window.show()
    return app.exec()
