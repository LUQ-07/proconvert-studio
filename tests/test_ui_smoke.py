"""UI smoke test against a fake Qt. Verifies our own UI code constructs and its handlers run.

LIMITATION: This does NOT test real Qt rendering or Qt API usage. A run on real PySide6 is still required.
"""
import importlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from .base import corpus
from . import qt_stub


class UiSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.home = Path(tempfile.mkdtemp(prefix="pc-ui-"))
        cls.env = {k: os.environ.get(k) for k in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME")}
        os.environ.update({"XDG_CONFIG_HOME": str(cls.home / "c"), "XDG_DATA_HOME": str(cls.home / "d"), "XDG_CACHE_HOME": str(cls.home / "k")})
        cls.excepthook = sys.excepthook
        qt_stub.install()
        cls.ctx_mod = importlib.import_module("proconvert.ui.context")
        cls.ctx = cls.ctx_mod.AppContext()

    @classmethod
    def tearDownClass(cls):
        sys.excepthook = cls.excepthook
        qt_stub.uninstall()
        for k, v in cls.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(cls.home, ignore_errors=True)

    def test_every_ui_module_imports(self):
        root = Path(__file__).resolve().parent.parent / "proconvert" / "ui"
        for p in sorted(root.rglob("*.py")):
            if p.name == "__init__.py":
                continue
            mod = "proconvert.ui." + ".".join(p.relative_to(root).with_suffix("").parts)
            with self.subTest(mod):
                importlib.import_module(mod)

    def test_pages_construct_and_show(self):
        main = type("M", (), {"statusBar": lambda s: type("S", (), {"showMessage": lambda *a: None})(), "notify": lambda *a: None})()
        from proconvert.ui.pages.about import AboutPage
        from proconvert.ui.pages.batch import BatchPage
        from proconvert.ui.pages.convert import ConvertPage
        from proconvert.ui.pages.dashboard import DashboardPage
        from proconvert.ui.pages.help import HelpPage
        from proconvert.ui.pages.history import HistoryPage
        from proconvert.ui.pages.settings import SettingsPage
        for lang in ("en", "fr", "ar"):
            self.ctx.update(language=lang)
            for cls, args in ((DashboardPage, ()), (ConvertPage, (main,)), (BatchPage, (main,)), (HistoryPage, ()),
                              (SettingsPage, ()), (HelpPage, ()), (AboutPage, ())):
                with self.subTest(lang=lang, page=cls.__name__):
                    page = cls(self.ctx, *args)
                    page.on_show()
        self.ctx.update(language="en")

    def test_convert_page_workflow_logic(self):
        from proconvert.ui.pages.convert import ConvertPage
        errors = []
        main = type("M", (), {"statusBar": lambda s: type("S", (), {"showMessage": lambda *a: None})(),
                              "notify": lambda s, t, m: errors.append(("notify", t))})()
        page = ConvertPage(self.ctx, main)
        for cat in ("pdf", "docx", "pptx", "xlsx"):
            page.select_category(cat)
        page.set_source(str(corpus()["docx"]))
        self.assertEqual("docx", page.category, "category follows the detected file format")
        self.assertEqual("docx", page.info.fmt)
        page.set_source(str(corpus()["garbage_docx"]))        # invalid file -> inline error, previous source kept
        self.assertEqual("rich.docx", page.info.path.name)
        from proconvert.core.pipeline import ConversionResult
        res = ConversionResult(str(self.home / "o.pdf"), "docx", "pdf", "e", "experimental", ["w1"], {"sections": 1, "paragraphs": 2, "tables": 0, "table_rows": 0, "pictures": 0, "characters": 5}, {}, 1.2)
        page._started_at = type("T", (), {"elapsed": lambda s: 1200})()
        page._on_success(res)
        self.assertEqual(1, self.ctx.history.count())
        from proconvert.core.errors import InvalidFileError
        page._on_failure(InvalidFileError(technical="x"))
        self.assertEqual(2, self.ctx.history.count())
        page._on_progress(type("E", (), {"stage": "reading", "fraction": None, "detail": "Page 1"})())
        page._on_progress(type("E", (), {"stage": "writing", "fraction": 0.5, "detail": ""})())

    def test_batch_page_logic(self):
        from proconvert.ui.pages.batch import BatchPage
        main = type("M", (), {"statusBar": lambda s: type("S", (), {"showMessage": lambda *a: None})(), "notify": lambda *a: None})()
        page = BatchPage(self.ctx, main)
        page.fmt_combo.currentData = lambda: "pdf"
        page.folder_edit.text = lambda: ""
        page.add_paths([str(corpus()["docx"]), str(corpus()["xlsx"])])
        self.assertEqual(2, page.queue.summary()["total"])
        page.clear_queue()

    def test_main_window_constructs(self):
        from proconvert.ui.main_window import MainWindow
        from proconvert.ui.palette import DARK
        w = MainWindow(self.ctx, DARK)
        self.assertEqual(8, len(w.pages))   # dashboard, convert, batch, images, history, settings, help, about
        w.navigate("history")
        w.rebuild_pages()

    def test_back_navigation_history(self):
        from proconvert.ui.main_window import MainWindow
        from proconvert.ui.palette import DARK
        w = MainWindow(self.ctx, DARK)
        self.assertEqual([], w._nav_history)                      # starting on the dashboard: nothing to go back to
        for key in ("convert", "history", "settings"):
            w.navigate(key)
        w.navigate("settings")                                    # re-opening the current page adds nothing
        self.assertEqual(["dashboard", "convert", "history"], w._nav_history)
        w.go_back()
        self.assertEqual("history", w._current)
        w.go_back()
        w.go_back()
        self.assertEqual("dashboard", w._current)
        w.go_back()                                               # nothing left: stays put, never raises
        self.assertEqual("dashboard", w._current)
        self.assertEqual([], w._nav_history)
        w.navigate("about", record=False)                         # programmatic jumps (rebuild) are not recorded
        self.assertEqual([], w._nav_history)

    def test_sidebar_state_is_remembered(self):
        self.assertFalse(self.ctx.settings.sidebar_collapsed)
        self.ctx.store.update(sidebar_collapsed=True)
        self.assertTrue(self.ctx.settings.sidebar_collapsed)
        self.ctx.store.update(sidebar_collapsed=False)


if __name__ == "__main__":
    unittest.main()
