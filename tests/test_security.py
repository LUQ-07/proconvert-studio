import os
import unittest
from pathlib import Path

from proconvert.core import errors as E
from proconvert.core.options import Limits
from proconvert.core.security import validate_source, validate_target
from proconvert.utils.files import is_safe_filename, sanitize_filename, unique_path
from proconvert.utils.ranges import parse_page_ranges

from .base import TmpCase, corpus


class SourceValidation(TmpCase):
    def test_valid_files_are_detected(self):
        c = corpus()
        for key, fmt in (("text_pdf", "pdf"), ("docx", "docx"), ("pptx", "pptx"), ("xlsx", "xlsx")):
            self.assertEqual(fmt, validate_source(c[key]).fmt)

    def test_empty_files_rejected(self):
        for ext in ("pdf", "docx", "pptx", "xlsx"):
            with self.assertRaises(E.EmptyContentError):
                validate_source(corpus()[f"empty_{ext}"])

    def test_corrupted_and_disguised(self):
        c = corpus()
        for key in ("garbage_docx", "truncated_docx", "disguised_xlsx"):
            with self.subTest(key), self.assertRaises(E.InvalidFileError):
                validate_source(c[key])

    def test_legacy_and_encrypted_office(self):
        with self.assertRaises(E.UnsupportedFormatError):
            validate_source(corpus()["legacy_doc"])
        with self.assertRaises(E.PasswordProtectedError):
            validate_source(corpus()["ole_docx"])

    def test_zip_bomb_rejected_by_total_size(self):
        with self.assertRaises(E.UnsafeFileError):
            validate_source(corpus()["bomb_docx"], Limits(max_zip_uncompressed_bytes=50 * 1024 * 1024))

    def test_zip_bomb_rejected_by_ratio(self):
        with self.assertRaises(E.UnsafeFileError):
            validate_source(corpus()["bomb_docx"], Limits(ratio_check_min_bytes=10 * 1024 * 1024, max_zip_entry_ratio=300))

    def test_size_limit(self):
        with self.assertRaises(E.FileTooLargeError):
            validate_source(corpus()["docx"], Limits(max_input_bytes=1000))

    def test_missing_and_directory(self):
        with self.assertRaises(E.InvalidFileError):
            validate_source(self.tmp / "nope.pdf")
        d = self.tmp / "folder.pdf"
        d.mkdir()
        with self.assertRaises(E.InvalidFileError):
            validate_source(d)


class TargetValidation(TmpCase):
    def test_good_target(self):
        t = validate_target(self.tmp / "out.pdf", None, "pdf", overwrite=False)
        self.assertEqual("out.pdf", t.name)

    def test_extension_mismatch_and_bad_names(self):
        for name in ("out.docx", "bad:name.pdf", "CON.pdf", "trailing .pdf.", "a|b.pdf"):
            with self.subTest(name), self.assertRaises(E.OutputPathError):
                validate_target(self.tmp / name, None, "pdf", overwrite=False)

    def test_missing_folder(self):
        with self.assertRaises(E.OutputPathError):
            validate_target(self.tmp / "nodir" / "out.pdf", None, "pdf", overwrite=False)

    def test_same_as_source(self):
        src = corpus()["text_pdf"]
        with self.assertRaises(E.OutputPathError):
            validate_target(src, src.resolve(), "pdf", overwrite=True)

    def test_existing_requires_overwrite(self):
        f = self.tmp / "x.pdf"
        f.write_bytes(b"old")
        with self.assertRaises(E.OutputExistsError):
            validate_target(f, None, "pdf", overwrite=False)
        self.assertEqual(f.resolve(), validate_target(f, None, "pdf", overwrite=True))

    def test_symlink_target_refused(self):
        real = self.tmp / "real.pdf"
        real.write_bytes(b"x")
        link = self.tmp / "link.pdf"
        try:
            os.symlink(real, link)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaises(E.OutputPathError):
            validate_target(link, None, "pdf", overwrite=True)

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), "needs a non-root POSIX user")
    def test_read_only_folder(self):
        ro = self.tmp / "ro"
        ro.mkdir()
        ro.chmod(0o555)
        self.addCleanup(ro.chmod, 0o755)
        with self.assertRaises(E.PermissionDeniedError):
            validate_target(ro / "o.pdf", None, "pdf", overwrite=False)


class Helpers(unittest.TestCase):
    def test_filenames(self):
        self.assertEqual("a_b.pdf", sanitize_filename("a:b.pdf"))
        self.assertTrue(sanitize_filename("CON").startswith("_"))
        self.assertEqual("converted", sanitize_filename("..."))
        self.assertTrue(is_safe_filename("report 2026.pdf")[0])
        self.assertFalse(is_safe_filename("x/y.pdf")[0])

    def test_unique_path(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        (d / "a.pdf").write_bytes(b"1")
        (d / "a (1).pdf").write_bytes(b"1")
        self.assertEqual("a (2).pdf", unique_path(d / "a.pdf").name)

    def test_page_ranges(self):
        self.assertEqual([0, 1, 2, 6], parse_page_ranges("1-3,7", 10))
        self.assertEqual(list(range(10)), parse_page_ranges("", 10))
        self.assertEqual([8, 9], parse_page_ranges("9-", 10))
        self.assertEqual([9], parse_page_ranges("5-99", 10)[-1:])
        for bad in ("abc", "3-1", "0", "11", "1,,2", "-"):
            with self.subTest(bad), self.assertRaises(E.InvalidOptionsError):
                parse_page_ranges(bad, 10)


if __name__ == "__main__":
    unittest.main()
