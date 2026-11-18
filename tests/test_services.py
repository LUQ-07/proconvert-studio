import contextlib
import io
import json
import logging
import os
import time
import unittest
import zipfile
from pathlib import Path

from proconvert import config

from proconvert import __version__
from proconvert.history.db import HistoryDB, HistoryRecord
from proconvert.services.diagnostics import export_diagnostics
from proconvert.services.logging_setup import RedactingFilter, setup_logging
from proconvert.services.temp_manager import TempManager
from proconvert.settings.store import AppSettings, SettingsStore, sanitize
from proconvert.utils.semver import SemVer

from .base import TmpCase, corpus


class Settings(TmpCase):
    def test_defaults_roundtrip_and_atomic(self):
        st = SettingsStore(self.tmp / "s.json")
        self.assertEqual("system", st.settings.appearance)
        self.assertFalse(st.settings.crash_reports_local, "crash reporting must default to off")
        self.assertFalse(hasattr(st.settings, "check_updates_on_start"), "updates are handled by the Microsoft Store")
        st.update(appearance="dark", language="fr", max_concurrent_jobs=3, last_formats={"pdf": "docx"})
        st2 = SettingsStore(self.tmp / "s.json")
        self.assertEqual(("dark", "fr", 3, {"pdf": "docx"}), (st2.settings.appearance, st2.settings.language, st2.settings.max_concurrent_jobs, st2.settings.last_formats))
        self.assertEqual([], [p.name for p in self.tmp.iterdir() if p.name.endswith(".tmp")])

    def test_corrupt_file_is_quarantined(self):
        p = self.tmp / "s.json"
        p.write_text("{not json")
        st = SettingsStore(p)
        self.assertEqual("system", st.settings.appearance)
        self.assertTrue(list(self.tmp.glob("s.json.corrupt-*")))

    def test_untrusted_values_are_sanitised(self):
        s = sanitize({"appearance": "neon", "max_concurrent_jobs": 99, "overwrite_confirm": "yes", "bogus": 1,
                      "language": "xx", "quality": "original", "output_dir": 5, "last_formats": {"a": 1}})
        self.assertEqual(("system", 2, True, "en", "original", "", {}),
                         (s.appearance, s.max_concurrent_jobs, s.overwrite_confirm, s.language, s.quality, s.output_dir, s.last_formats))
        self.assertFalse(hasattr(s, "bogus"))
        self.assertEqual("system", sanitize([1, 2]).appearance)

    def test_update_validates_and_notifies(self):
        st = SettingsStore(self.tmp / "s.json")
        seen = []
        st.subscribe(seen.append)
        st.update(appearance="light", log_level="LOUD")
        self.assertEqual(("light", "INFO"), (st.settings.appearance, st.settings.log_level))
        self.assertEqual(1, len(seen))

    def test_old_settings_file_with_removed_update_keys_still_loads(self):
        from proconvert.settings.store import sanitize
        st = sanitize({"language": "fr", "check_updates_on_start": True, "appearance": "dark"})
        self.assertEqual("fr", st.language)
        self.assertEqual("dark", st.appearance)

    def test_to_options(self):
        o = AppSettings(quality="standard", ocr_enabled=True, page_size="Letter").to_options()
        self.assertEqual((1600, True, "Letter"), (o.image_max_px, o.ocr_enabled, o.page_size))


class History(TmpCase):
    def rec(self, name="a.docx", st="success", out="pdf", ms=1000, **kw):
        return HistoryRecord(name, f"/x/{name}", name.split(".")[-1], out, st, f"/y/{name}.{out}", ms, **kw)

    def test_crud_search_filter_sort(self):
        db = HistoryDB(self.tmp / "h.db")
        for r in (self.rec("alpha.docx", ms=300), self.rec("beta.pptx", "failed", error_summary="bad file", ms=100),
                  self.rec("gamma.xlsx", ms=900), self.rec("100%_real.docx", ms=50)):
            db.add(r)
        self.assertEqual(4, db.count())
        self.assertEqual(["100%_real.docx"], [r.input_name for r in db.query(search="100%")], "% must be literal")
        self.assertEqual(1, len(db.query(search="bad file")))
        self.assertEqual(["beta.pptx"], [r.input_name for r in db.query(status="failed")])
        self.assertEqual(2, len(db.query(input_format="docx")))
        self.assertEqual(["gamma.xlsx", "alpha.docx"], [r.input_name for r in db.query(sort="duration_ms")][:2])
        self.assertEqual("100%_real.docx", db.query(sort="duration_ms", descending=False)[0].input_name)
        self.assertEqual(4, len(db.query(sort="id; DROP TABLE conversions")), "unknown sort keys fall back safely")
        rec = db.query()[0]
        self.assertEqual(rec.input_name, db.get(rec.id).input_name)
        db.delete(rec.id)
        self.assertEqual(3, db.count())
        s = db.stats()
        self.assertEqual((3, 2, 1), (s["total"], s["success"], s["failed"]))
        db.clear()
        self.assertEqual(0, db.count())

    def test_no_document_content_columns(self):
        import sqlite3
        HistoryDB(self.tmp / "h.db")
        cols = {r[1] for r in sqlite3.connect(self.tmp / "h.db").execute("PRAGMA table_info(conversions)")}
        self.assertEqual({"id", "input_name", "input_path", "input_format", "output_format", "output_path", "started_at",
                          "duration_ms", "status", "error_summary", "warnings_count", "route_status"}, cols)

    def test_csv_export_neutralises_formulas(self):
        db = HistoryDB(self.tmp / "h.db")
        db.add(self.rec("=HYPERLINK(1).docx"))
        n = db.export_csv(self.tmp / "o.csv")
        text = (self.tmp / "o.csv").read_text(encoding="utf-8-sig")
        self.assertEqual(1, n)
        self.assertIn("'=HYPERLINK", text)
        self.assertNotIn(",=HYPERLINK", text)

    def test_sql_injection_in_search_is_inert(self):
        db = HistoryDB(self.tmp / "h.db")
        db.add(self.rec())
        self.assertEqual([], db.query(search="'; DROP TABLE conversions; --"))
        self.assertEqual(1, db.count())


class SemVerCase(unittest.TestCase):
    def test_precedence_from_spec(self):
        order = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0", "1.0.1", "1.1.0", "2.0.0"]
        vs = [SemVer(x) for x in order]
        self.assertEqual(vs, sorted(vs))
        self.assertEqual(SemVer("1.0.0+build1"), SemVer("1.0.0+build2"))
        for bad in ("1.0", "01.0.0", "a.b.c", ""):
            with self.assertRaises(ValueError):
                SemVer(bad)
        SemVer(__version__)


class LoggingAndTemp(TmpCase):
    def test_redaction(self):
        f = RedactingFilter()
        home = str(Path.home())
        out = f.redact(f"opened {home}/Documents/x.pdf for jane.doe@example.com")
        self.assertNotIn(home, out)
        self.assertIn("~/Documents", out)
        self.assertIn("<email>", out)

    def test_log_file_written_redacted(self):
        path = setup_logging("INFO", self.tmp / "logs")
        logging.getLogger("proconvert.test").info("file %s by bob@example.com", Path.home() / "secret.pdf")
        for h in logging.getLogger("proconvert").handlers:
            h.flush()
        text = path.read_text()
        self.assertIn("<email>", text)
        self.assertNotIn(str(Path.home()), text)

    def test_temp_cleanup(self):
        tm = TempManager(self.tmp / "t")
        old, new = tm.ensure() / "job-old", tm.ensure() / "job-new"
        for d in (old, new):
            d.mkdir()
            (d / "f").write_bytes(b"x" * 100)
        t = time.time() - 48 * 3600
        os.utime(old, (t, t))
        self.assertEqual(1, tm.cleanup_stale(6))
        self.assertTrue(new.exists() and not old.exists())
        self.assertGreaterEqual(tm.clear_all(), 100)
        self.assertFalse(new.exists())


class Diagnostics(TmpCase):
    def test_export_contains_no_documents_and_hides_paths(self):
        logs = self.tmp / "logs"
        setup_logging("INFO", logs)
        logging.getLogger("proconvert.x").info("in %s", Path.home() / "tax.pdf")
        for h in logging.getLogger("proconvert").handlers:
            h.flush()
        s = AppSettings(output_dir="/Users/jane/Private", temp_dir="/tmp/x")
        out = export_diagnostics(self.tmp / "d.zip", s, logs)
        with zipfile.ZipFile(out) as z:
            names = z.namelist()
            blob = b"".join(z.read(n) for n in names).decode("utf-8", "replace")
        self.assertIn("system.json", names)
        self.assertNotIn("/Users/jane/Private", blob)
        self.assertNotIn(str(Path.home()), blob)
        self.assertFalse([n for n in names if n.endswith((".pdf", ".docx", ".xlsx", ".pptx"))])


class Cli(TmpCase):
    def run_cli(self, *args):
        from proconvert.cli import main
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_routes_convert_and_errors(self):
        code, out, _ = self.run_cli("routes")
        self.assertEqual(12 - len(config.DISABLED_ROUTES), len(out.strip().splitlines()))
        code, out, _ = self.run_cli("convert", str(corpus()["docx"]), str(self.tmp / "o.pdf"))
        self.assertEqual(0, code)
        self.assertIn("OK", out)
        code, _, err = self.run_cli("convert", str(corpus()["docx"]), str(self.tmp / "o.pdf"))
        self.assertEqual(2, code)
        self.assertIn("already exists", err)
        self.assertNotIn("Traceback", err)

    def test_selftest_all_routes(self):
        from proconvert import selftest
        report = selftest.run(verbose=False)
        self.assertEqual(12 - len(config.DISABLED_ROUTES), report["passed"])


if __name__ == "__main__":
    unittest.main()
