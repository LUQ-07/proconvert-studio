"""Main window: left navigation sidebar + stacked pages."""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QMessageBox, QPushButton, QStackedWidget,
                               QSystemTrayIcon, QVBoxLayout, QWidget, QMainWindow)

from .. import __version__, config
from ..utils.paths import resource_path
from .icons import icon
from .pages.about import AboutPage
from .pages.batch import BatchPage
from .pages.convert import ConvertPage
from .pages.dashboard import DashboardPage
from .pages.help import HelpPage
from .pages.history import HistoryPage
from .pages.images import ImagesPage
from .pages.settings import SettingsPage
from .widgets.common import label

NAV = [("dashboard", "home"), ("convert", "convert"), ("batch", "batch"), ("images", "image"), ("history", "history"),
       ("settings", "settings"), ("help", "help"), ("about", "info")]


class MainWindow(QMainWindow):
    SIDEBAR_WIDTH = 224

    def __init__(self, ctx, palette: dict[str, str]) -> None:
        super().__init__()
        self.ctx = ctx
        self.palette_tokens = palette
        self.setWindowTitle(config.APP_NAME)
        self.setMinimumSize(980, 660)
        self.resize(1180, 780)
        ico = resource_path("assets/icon.png")
        if ico.exists():
            self.setWindowIcon(QIcon(str(ico)))
        self._tray: QSystemTrayIcon | None = None
        self._pending_rebuild = False
        self.pages: dict[str, QWidget] = {}
        self.nav_buttons: dict[str, QPushButton] = {}
        self._nav_history: list[str] = []      # pages visited before the current one (for the Back button)
        self._current: str | None = None
        self._side_anim: QPropertyAnimation | None = None
        self.build()

    # ------------------------------------------------------------------ construction
    def build(self) -> None:
        tr = self.ctx.tr
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        side = QFrame()
        side.setObjectName("Sidebar")
        self._side = side
        side.setMinimumWidth(0)
        side.setMaximumWidth(self.SIDEBAR_WIDTH)
        side.setMinimumWidth(self.SIDEBAR_WIDTH)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 18, 14, 14)
        sl.setSpacing(4)
        brand = label(config.APP_NAME, "h2")
        brand.setAccessibleName(config.APP_NAME)
        sl.addWidget(brand)
        sl.addSpacing(14)
        self.nav_buttons.clear()
        for key, ico in NAV:
            b = QPushButton("  " + tr(f"nav.{key}"))
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setIcon(icon(ico, self.palette_tokens["muted"]))
            b.setAccessibleName(tr(f"nav.{key}"))
            b.clicked.connect(lambda _c=False, k=key: self.navigate(k))
            sl.addWidget(b)
            self.nav_buttons[key] = b
        sl.addStretch(1)
        sl.addWidget(label(f"v{__version__}", "muted"))
        outer.addWidget(side)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        bar = QFrame()
        bar.setObjectName("TopBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(10, 6, 14, 6)
        bl.setSpacing(6)
        rtl = self.layoutDirection() == Qt.LayoutDirection.RightToLeft
        self.menu_btn = QPushButton()
        self.menu_btn.setObjectName("iconbtn")
        self.menu_btn.setIcon(icon("menu", self.palette_tokens["text"]))
        self.menu_btn.setToolTip(tr("nav.toggle_sidebar") + "  (Ctrl+B)")
        self.menu_btn.setAccessibleName(tr("nav.toggle_sidebar"))
        self.menu_btn.clicked.connect(self.toggle_sidebar)
        self.back_btn = QPushButton()
        self.back_btn.setObjectName("iconbtn")
        self.back_btn.setIcon(icon("arrow_right" if rtl else "arrow_left", self.palette_tokens["text"]))
        self.back_btn.setToolTip(tr("nav.back") + "  (Alt+Left)")
        self.back_btn.setAccessibleName(tr("nav.back"))
        self.back_btn.clicked.connect(self.go_back)
        self.page_title = label("", "h3")
        bl.addWidget(self.menu_btn)
        bl.addWidget(self.back_btn)
        bl.addWidget(self.page_title)
        bl.addStretch(1)
        rl.addWidget(bar)
        self.stack = QStackedWidget()
        rl.addWidget(self.stack, 1)
        outer.addWidget(right, 1)
        if self.ctx.settings.sidebar_collapsed:
            side.setMinimumWidth(0)
            side.setMaximumWidth(0)
            side.hide()

        self.pages = {}
        dash = DashboardPage(self.ctx)
        convert = ConvertPage(self.ctx, self)
        batch = BatchPage(self.ctx, self)
        images = ImagesPage(self.ctx, self)
        history = HistoryPage(self.ctx)
        for key, page in (("dashboard", dash), ("convert", convert), ("batch", batch), ("images", images), ("history", history),
                          ("settings", SettingsPage(self.ctx)), ("help", HelpPage(self.ctx)), ("about", AboutPage(self.ctx))):
            self.pages[key] = page
            self.stack.addWidget(page)
        dash.open_category.connect(lambda fmt: self.open_convert(category=fmt))
        dash.navigate.connect(self.navigate)
        convert.history_changed.connect(lambda: None)
        history.retry_requested.connect(self._retry_from_history)

        for i, (key, _ico) in enumerate(NAV[:9], 1):
            sc = QShortcut(QKeySequence(f"Ctrl+{i}"), self)
            sc.activated.connect(lambda k=key: self.navigate(k))
        QShortcut(QKeySequence("F1"), self).activated.connect(lambda: self.navigate("help"))
        QShortcut(QKeySequence("Ctrl+B"), self).activated.connect(self.toggle_sidebar)
        QShortcut(QKeySequence("Alt+Left"), self).activated.connect(self.go_back)
        QShortcut(QKeySequence.StandardKey.Open, self).activated.connect(lambda: self.open_convert())
        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self._shortcut_convert)

        self.statusBar().showMessage(tr("status.ready"))
        self.navigate("dashboard", record=False)

    def rebuild_pages(self) -> None:
        """Re-create the UI (used after a language change so every string and the layout direction update)."""
        if any(self.pages[k].is_busy for k in ("convert", "batch", "images")):
            self._pending_rebuild = True        # never destroy a page that owns a running job
            self.statusBar().showMessage(self.ctx.tr("app.change_pending"), 8000)
            return
        self._pending_rebuild = False
        current = next((k for k, p in self.pages.items() if p is self.stack.currentWidget()), "dashboard")
        old = self.centralWidget()
        self.build()
        old.deleteLater()
        self.navigate(current, record=False)

    # ------------------------------------------------------------------ navigation
    def navigate(self, key: str, record: bool = True) -> None:
        if getattr(self, "_pending_rebuild", False):
            self.rebuild_pages()
        page = self.pages[key]
        if record and self._current and self._current != key:
            self._nav_history.append(self._current)
            del self._nav_history[:-30]
        self._current = key
        self.stack.setCurrentWidget(page)
        for k, b in self.nav_buttons.items():
            b.setChecked(k == key)
        self.page_title.setText(self.ctx.tr(f"nav.{key}"))
        self.back_btn.setEnabled(bool(self._nav_history))
        page.on_show()

    def go_back(self) -> None:
        """Return to the page that was open before the current one."""
        while self._nav_history:
            key = self._nav_history.pop()
            if key in self.pages and key != self._current:
                self.navigate(key, record=False)
                return
        self.back_btn.setEnabled(False)

    def toggle_sidebar(self) -> None:
        """Slide the navigation sidebar in or out; the choice is remembered."""
        side = self._side
        collapsing = side.isVisible() and side.maximumWidth() > 0
        if self._side_anim is not None:
            self._side_anim.stop()
        side.setMinimumWidth(0)
        if not collapsing:
            side.setMaximumWidth(0)
            side.show()
        anim = QPropertyAnimation(side, b"maximumWidth", self)
        anim.setDuration(160)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        anim.setStartValue(side.maximumWidth())
        anim.setEndValue(0 if collapsing else self.SIDEBAR_WIDTH)

        def done() -> None:
            if collapsing:
                side.hide()
            else:
                side.setMinimumWidth(self.SIDEBAR_WIDTH)
        anim.finished.connect(done)
        self._side_anim = anim
        self.ctx.store.update(sidebar_collapsed=collapsing)
        anim.start()

    def open_convert(self, category: str | None = None, path: str | None = None, target: str | None = None) -> None:
        self.navigate("convert")
        page: ConvertPage = self.pages["convert"]  # type: ignore[assignment]
        if category or path:
            page.open_with(category, path, target)
        elif not page.info:
            page.browse()

    def _retry_from_history(self, path: str, src: str, dst: str) -> None:
        if src == "image":
            self.navigate("images")
            self.pages["images"].add_from_history(path)       # type: ignore[attr-defined]
        else:
            self.open_convert(category=src, path=path, target=dst)

    def _shortcut_convert(self) -> None:
        page = self.pages["convert"]
        if self.stack.currentWidget() is page and page.convert_btn.isEnabled():
            page.start()

    def notify(self, title: str, message: str) -> None:
        self.statusBar().showMessage(f"{title}: {message}", 8000)
        if not self.ctx.settings.notifications:
            return
        if not self.isActiveWindow():
            QApplication.alert(self, 0)
            if QSystemTrayIcon.isSystemTrayAvailable():
                tray = QSystemTrayIcon(self.windowIcon(), self)
                tray.show()
                tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 6000)
                QTimer.singleShot(8000, tray.hide)
                self._tray = tray

    # ------------------------------------------------------------------ shutdown
    def closeEvent(self, event) -> None:  # noqa: N802
        convert, batch, images = self.pages["convert"], self.pages["batch"], self.pages["images"]
        if convert.is_busy or batch.is_busy or images.is_busy:
            answer = QMessageBox.question(self, config.APP_NAME, self.ctx.tr("app.quit_busy"))
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        convert.shutdown()      # terminates worker processes and removes partial output
        batch.shutdown()
        images.shutdown()
        self.ctx.temp.cleanup_stale(6.0)
        event.accept()
