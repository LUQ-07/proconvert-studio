import threading
import time
import unittest

from proconvert.core import errors as E
from proconvert.core.capabilities import all_routes
from proconvert.core.extract import extract_text
from proconvert.core.options import ConversionOptions, Limits
from proconvert.workers.batch import BatchQueue, ItemStatus, plan_target
from proconvert.workers.process_job import ConversionJob

from .base import TmpCase, corpus, squash
from .helpers_crash import crash_main, slow_main
from .make_corpus import big_pdf


class JobProcess(TmpCase):
    def test_success_with_real_progress_events(self):
        ev = []
        job = ConversionJob(corpus()["text_pdf"], self.tmp / "o.docx", temp_root=self.work)
        res = job.run(ev.append)
        self.assertTrue((self.tmp / "o.docx").exists())
        self.assertGreaterEqual(len([e for e in ev if e.stage == "reading"]), 1)   # throttled to ~12/s by design
        fr = [e.fraction for e in ev if e.fraction is not None]
        self.assertEqual(fr, sorted(fr))
        self.assertEqual("done", ev[-1].stage)
        self.assertIsNotNone(res.stats["tables"])
        self.assertNoLeftovers()

    def test_error_crosses_process_boundary_with_type_preserved(self):
        job = ConversionJob(corpus()["garbage_pdf"], self.tmp / "o.docx", temp_root=self.work)
        with self.assertRaises(E.InvalidFileError) as cm:
            job.run()
        self.assertTrue(cm.exception.troubleshooting)
        self.assertNoLeftovers()

    def test_cancel_mid_conversion_kills_worker_and_cleans_up(self):
        big = big_pdf(self.tmp / "big.pdf", pages=120)
        job = ConversionJob(big, self.tmp / "o.docx", temp_root=self.work)
        started = threading.Event()
        pids = []

        def on_progress(ev):
            if ev.stage == "reading" and job.pid:
                pids.append(job.pid)
                started.set()
        threading.Timer(1.5, job.cancel).start()
        t0 = time.monotonic()
        with self.assertRaises(E.CancelledError):
            job.run(on_progress)
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 10, "cancellation must be prompt")
        self.assertFalse((self.tmp / "o.docx").exists())
        self.assertNoLeftovers()
        import os
        if pids:
            time.sleep(0.3)
            with self.assertRaises(OSError):
                os.kill(pids[0], 0) if hasattr(os, "kill") and os.name != "nt" else (_ for _ in ()).throw(OSError())

    def test_timeout(self):
        big = big_pdf(self.tmp / "big.pdf", pages=120)
        job = ConversionJob(big, self.tmp / "o.docx", temp_root=self.work, timeout=1.0)
        with self.assertRaises(E.ConversionTimeoutError):
            job.run()
        self.assertNoLeftovers()

    def test_crashing_worker_is_contained(self):
        class Crashy(ConversionJob):
            _target = staticmethod(crash_main)
        with self.assertRaises(E.EngineCrashError):
            Crashy(corpus()["docx"], self.tmp / "o.pdf", temp_root=self.work).run()
        self.assertNoLeftovers()

    def test_hung_worker_is_killed_on_cancel(self):
        class Hung(ConversionJob):
            _target = staticmethod(slow_main)
        job = Hung(corpus()["docx"], self.tmp / "o.pdf", temp_root=self.work)
        threading.Timer(0.8, job.cancel).start()
        t0 = time.monotonic()
        with self.assertRaises(E.CancelledError):
            job.run()
        self.assertLess(time.monotonic() - t0, 8)


class Batch(TmpCase):
    SRC = {"pdf": ("text_pdf", "SENTINEL-PDF-P1"), "docx": ("docx", "SENTINEL-DOCX-INTRO"),
           "pptx": ("pptx", "SENTINEL-PPTX-TITLE"), "xlsx": ("xlsx", "SENTINEL-XLSX-NOTE")}

    def test_batch_runs_all_twelve_routes(self):
        updates = []
        q = BatchQueue(max_workers=2, on_update=lambda i: updates.append((i.id, i.status)), temp_root=self.work)
        for r in all_routes():
            key, _ = self.SRC[r.source]
            q.add(corpus()[key], self.tmp / f"{r.source}_{r.target}.{r.target}", ConversionOptions())
        q.start()
        self.assertTrue(q.wait(240))
        s = q.summary()
        self.assertEqual(len(all_routes()), s["done"], [(i.source.name, i.target.suffix, i.message) for i in q.items if i.status != ItemStatus.DONE])
        for i in q.items:
            token = self.SRC[i.source.suffix.lstrip(".") if i.source.name != "text.pdf" else "pdf"][1]
            self.assertIn(squash(token), squash(extract_text(i.target)))
        self.assertEqual(1.0, q.overall_fraction())
        self.assertNoLeftovers()

    def test_failures_do_not_stop_the_batch_and_retry_works(self):
        q = BatchQueue(max_workers=1, temp_root=self.work)
        later = self.tmp / "later.docx"
        q.add(corpus()["docx"], self.tmp / "a.pdf", ConversionOptions())
        bad = q.add(later, self.tmp / "b.pdf", ConversionOptions())         # does not exist yet
        q.add(corpus()["xlsx"], self.tmp / "c.pdf", ConversionOptions())
        q.start()
        q.wait(120)
        self.assertEqual({"done": 2, "failed": 1}, {k: v for k, v in q.summary().items() if v and k not in ("total",)})
        self.assertIn("could not be found", bad.message)
        import shutil
        shutil.copy(corpus()["docx"], later)
        self.assertEqual(1, q.retry_failed())
        q.wait(120)
        self.assertEqual(3, q.summary()["done"])

    def test_cancel_pending_and_cancel_all(self):
        big = big_pdf(self.tmp / "big.pdf", pages=100)
        q = BatchQueue(max_workers=1, temp_root=self.work)
        a = q.add(big, self.tmp / "a.docx", ConversionOptions())
        b = q.add(corpus()["docx"], self.tmp / "b.pdf", ConversionOptions())
        c = q.add(corpus()["docx"], self.tmp / "c.pdf", ConversionOptions())
        q.start()
        time.sleep(1.2)
        q.cancel_pending()
        self.assertEqual(ItemStatus.CANCELLED, b.status)
        self.assertEqual(ItemStatus.CANCELLED, c.status)
        q.cancel_all()
        q.wait(30)
        self.assertEqual(ItemStatus.CANCELLED, a.status)
        self.assertFalse((self.tmp / "a.docx").exists())
        self.assertNoLeftovers()

    def test_queue_editing_and_skip(self):
        q = BatchQueue(temp_root=self.work)
        x = q.add(corpus()["docx"], self.tmp / "x.pdf", ConversionOptions())
        y = q.add(corpus()["docx"], self.tmp / "y.docx", ConversionOptions(), skip_reason="Already a DOCX file")
        self.assertEqual(ItemStatus.SKIPPED, y.status)
        self.assertTrue(q.remove(x.id))
        q.clear()
        self.assertEqual(0, q.summary()["total"])

    def test_plan_target_never_overwrites(self):
        (self.tmp / "doc.pdf").write_bytes(b"x")
        self.assertEqual("doc (1).pdf", plan_target(self.tmp / "doc.docx", self.tmp, "pdf", False).name)
        self.assertEqual("doc.pdf", plan_target(self.tmp / "doc.docx", self.tmp, "pdf", True).name)


if __name__ == "__main__":
    unittest.main()
