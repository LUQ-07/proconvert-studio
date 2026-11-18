import errno
import hashlib
import os
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from proconvert.core import errors as E
from proconvert.core import pipeline
from proconvert.core.context import CancelToken
from proconvert.core.extract import extract_text
from proconvert.core.options import ConversionOptions, Limits
from proconvert.core.verify import OutputVerificationError

from .base import TmpCase, corpus, squash


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class Corrupted(TmpCase):
    def expect(self, key, out, exc):
        with self.assertRaises(exc) as cm:
            self.conv(corpus()[key], out)
        self.assertFalse((self.tmp / out).exists(), "no output may exist after a failure")
        self.assertTrue(cm.exception.user_message and cm.exception.troubleshooting)
        self.assertNotIn("Traceback", cm.exception.user_message)
        self.assertNoLeftovers()
        return cm.exception

    def test_each_bad_input_gives_the_right_friendly_error(self):
        cases = [("empty_pdf", "o.docx", E.EmptyContentError), ("empty_docx", "o.pdf", E.EmptyContentError),
                 ("garbage_pdf", "o.docx", E.InvalidFileError), ("garbage_docx", "o.pdf", E.InvalidFileError),
                 ("truncated_docx", "o.pdf", E.InvalidFileError), ("disguised_xlsx", "o.pdf", E.InvalidFileError),
                 ("legacy_doc", "o.pdf", E.UnsupportedFormatError), ("ole_docx", "o.pdf", E.PasswordProtectedError),
                 ("entity_xlsx", "o.pdf", E.UnsafeFileError), ("bomb_docx", "o.pdf", E.UnsafeFileError)]
        for key, out, exc in cases:
            with self.subTest(key):
                if key == "bomb_docx":
                    with self.assertRaises(exc):
                        self.conv(corpus()[key], out, limits=Limits(max_zip_uncompressed_bytes=50 * 1024 * 1024))
                else:
                    self.expect(key, out, exc)

    def test_same_format_and_unknown_target(self):
        with self.assertRaises(E.UnsupportedFormatError):
            self.conv(corpus()["docx"], "o.docx")
        with self.assertRaises(E.UnsupportedFormatError):
            self.conv(corpus()["docx"], "o.txt")

    def test_blank_pdf_is_reported_not_converted_to_an_empty_file(self):
        from reportlab.pdfgen import canvas
        blank = self.tmp / "blank.pdf"
        c = canvas.Canvas(str(blank))
        c.showPage()
        c.save()
        with self.assertRaises(E.EmptyContentError):
            self.conv(blank, "o.docx")
        self.assertFalse((self.tmp / "o.docx").exists())

    def test_page_range_and_page_limit(self):
        with self.assertRaises(E.InvalidOptionsError):
            self.conv(corpus()["text_pdf"], "o.docx", ConversionOptions(pdf_pages="99"))
        with self.assertRaises(E.FileTooLargeError):
            self.conv(corpus()["text_pdf"], "o.docx", limits=Limits(max_pdf_pages=2))

    def test_macro_warning(self):
        src = self.tmp / "macro.docx"
        with zipfile.ZipFile(corpus()["docx"]) as zin, zipfile.ZipFile(src, "w") as zout:
            for i in zin.infolist():
                zout.writestr(i, zin.read(i.filename))
            zout.writestr("word/vbaProject.bin", b"x")
        res = self.conv(src, "o.pdf")
        self.assertTrue(any("macros" in w.lower() for w in res.warnings))


class Passwords(TmpCase):
    def test_password_flow(self):
        enc = corpus()["encrypted_pdf"]
        with self.assertRaises(E.PasswordProtectedError):
            self.conv(enc, "o.docx")
        with self.assertRaises(E.PasswordProtectedError) as cm:
            self.conv(enc, "o.docx", ConversionOptions(pdf_password="wrong"))
        self.assertIn("not correct", cm.exception.user_message)
        res = self.conv(enc, "ok.docx", ConversionOptions(pdf_password="s3cret"))
        self.assertIn("SENTINEL-PDF-P1", squash(extract_text(res.output_path)).replace("SENTINEL-PDF-P1", "SENTINEL-PDF-P1"))
        self.assertNotIn("s3cret", repr(ConversionOptions(pdf_password="s3cret")))
        self.assertEqual("***", ConversionOptions(pdf_password="x").redacted()["pdf_password"])


class OverwriteAndAtomicity(TmpCase):
    def test_existing_file_protected_unless_overwrite(self):
        out = self.tmp / "o.pdf"
        out.write_bytes(b"precious")
        with self.assertRaises(E.OutputExistsError):
            self.conv(corpus()["docx"], "o.pdf")
        self.assertEqual(b"precious", out.read_bytes())
        self.conv(corpus()["docx"], "o.pdf", overwrite=True)
        self.assertTrue(out.read_bytes().startswith(b"%PDF"))
        self.assertNoLeftovers()

    def test_source_is_never_modified(self):
        src = corpus()["docx"]
        before = sha(src)
        self.conv(src, "o.pdf")
        self.assertEqual(before, sha(src))

    def test_disk_full_leaves_target_untouched_and_cleans_up(self):
        out = self.tmp / "o.pdf"
        out.write_bytes(b"precious")
        with mock.patch.object(pipeline.shutil, "copyfile", side_effect=OSError(errno.ENOSPC, "No space left on device")):
            with self.assertRaises(E.DiskFullError):
                self.conv(corpus()["docx"], "o.pdf", overwrite=True)
        self.assertEqual(b"precious", out.read_bytes())
        self.assertNoLeftovers()

    def test_permission_error_on_write_is_friendly(self):
        with mock.patch.object(pipeline.shutil, "copyfile", side_effect=PermissionError(errno.EACCES, "denied")):
            with self.assertRaises(E.PermissionDeniedError):
                self.conv(corpus()["docx"], "o.pdf")
        self.assertNoLeftovers()

    def test_invalid_output_produced_by_a_buggy_writer_is_discarded(self):
        def bad_writer(ir, path, ctx):
            Path(path).write_bytes(b"not a real docx")
        with mock.patch.object(pipeline, "get_writer", return_value=bad_writer):
            with self.assertRaises(OutputVerificationError):
                self.conv(corpus()["text_pdf"], "o.docx")
        self.assertFalse((self.tmp / "o.docx").exists())
        self.assertNoLeftovers()

    def test_unexpected_exception_becomes_friendly_error(self):
        with mock.patch.object(pipeline, "get_reader", return_value=lambda p, c: 1 / 0):
            with self.assertRaises(E.ConversionError) as cm:
                self.conv(corpus()["docx"], "o.pdf")
        self.assertIn("ZeroDivisionError", cm.exception.technical)
        self.assertNotIn("ZeroDivisionError", cm.exception.user_message)
        self.assertNoLeftovers()


class InProcessCancel(TmpCase):
    def test_cancel_before_start(self):
        tok = CancelToken()
        tok.cancel()
        with self.assertRaises(E.CancelledError):
            self.conv(corpus()["docx"], "o.pdf", cancel=tok)
        self.assertFalse((self.tmp / "o.pdf").exists())
        self.assertNoLeftovers()

    def test_cancel_during_reading(self):
        tok = CancelToken()
        seen = []

        def on_progress(ev):
            seen.append(ev.stage)
            if ev.stage == "reading":
                tok.cancel()
        with self.assertRaises(E.CancelledError):
            self.conv(corpus()["text_pdf"], "o.docx", cancel=tok, on_progress=on_progress)
        self.assertNotIn("writing", seen)
        self.assertNoLeftovers()

    def test_cancel_during_writing(self):
        tok = CancelToken()

        def on_progress(ev):
            if ev.stage == "writing":
                tok.cancel()
        with self.assertRaises(E.CancelledError):
            self.conv(corpus()["pptx"], "o.pdf", cancel=tok, on_progress=on_progress)
        self.assertFalse((self.tmp / "o.pdf").exists())
        self.assertNoLeftovers()


class ProgressHonesty(TmpCase):
    def test_progress_is_monotonic_and_stage_ordered(self):
        events = []
        self.conv(corpus()["text_pdf"], "o.docx", on_progress=events.append)
        order = ["validating", "reading", "writing", "verifying", "finalizing", "done"]
        stages = [e.stage for e in events]
        self.assertEqual(order, sorted(set(stages), key=order.index))
        fr = [e.fraction for e in events if e.fraction is not None]
        self.assertEqual(fr, sorted(fr))
        self.assertEqual(1.0, fr[-1])
        indeterminate = {e.stage for e in events if e.fraction is None}
        self.assertEqual({"validating", "verifying", "finalizing"}, indeterminate, "unmeasurable stages must be indeterminate")
        reading = [e for e in events if e.stage == "reading"]
        self.assertGreaterEqual(len(reading), 5, "reading reports once per real page")


if __name__ == "__main__":
    unittest.main()
