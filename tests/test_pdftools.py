import tempfile
import unittest
from pathlib import Path

import pdfplumber
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from proconvert.core.errors import (InvalidFileError, InvalidOptionsError, OutputExistsError, OutputPathError,
                                    PasswordProtectedError)
from proconvert.pdftools import (add_page_numbers, add_watermark, compress_pdf, delete_pages, duplicate_pages,
                                 extract_pages, images_to_pdf, merge_pdfs, pdf_info, pdf_to_images, protect_pdf,
                                 reorder_pages, rotate_pages, set_metadata, split_pdf, unprotect_pdf)

from .make_corpus import make_png


def make_pdf(path: Path, n: int, tag="DOC") -> Path:
    c = canvas.Canvas(str(path), pagesize=(300, 400))
    for i in range(1, n + 1):
        c.drawString(40, 350, f"{tag}-PAGE-{i}")
        c.showPage()
    c.save()
    return path


def page_texts(path) -> list[str]:
    with pdfplumber.open(str(path)) as pdf:
        return [(p.extract_text() or "").strip() for p in pdf.pages]


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)
        self.a = make_pdf(self.d / "a.pdf", 5, "A")
        self.b = make_pdf(self.d / "b.pdf", 2, "B")

    def tearDown(self):
        self._tmp.cleanup()

    def no_temp_files_left(self):
        self.assertEqual([], [p.name for p in self.d.iterdir() if p.name.startswith(".pdftool-")])


class PageOps(Base):
    def test_merge_order_and_count(self):
        out = merge_pdfs([self.a, self.b], self.d / "m.pdf")
        t = page_texts(out)
        self.assertEqual(7, len(t))
        self.assertEqual("A-PAGE-1", t[0])
        self.assertEqual("B-PAGE-2", t[-1])
        self.no_temp_files_left()

    def test_merge_needs_two_and_refuses_output_equal_to_input(self):
        with self.assertRaises(InvalidOptionsError):
            merge_pdfs([self.a], self.d / "m.pdf")
        with self.assertRaises((OutputPathError, OutputExistsError)):
            merge_pdfs([self.a, self.b], self.a, overwrite=True)

    def test_extract_delete_reorder_duplicate(self):
        self.assertEqual(["A-PAGE-2", "A-PAGE-3", "A-PAGE-5"], page_texts(extract_pages(self.a, self.d / "e.pdf", "2-3,5")))
        self.assertEqual(["A-PAGE-1", "A-PAGE-4", "A-PAGE-5"], page_texts(delete_pages(self.a, self.d / "d.pdf", "2-3")))
        self.assertEqual(["A-PAGE-3", "A-PAGE-1", "A-PAGE-1"], page_texts(reorder_pages(self.a, self.d / "r.pdf", [3, 1, 1])))
        dup = page_texts(duplicate_pages(self.a, self.d / "u.pdf", "2"))
        self.assertEqual(["A-PAGE-1", "A-PAGE-2", "A-PAGE-2", "A-PAGE-3"], dup[:4])
        self.assertEqual(6, len(dup))

    def test_cannot_delete_every_page_or_use_bad_ranges(self):
        with self.assertRaises(InvalidOptionsError):
            delete_pages(self.a, self.d / "x.pdf", "1-5")
        with self.assertRaises(InvalidOptionsError):
            extract_pages(self.a, self.d / "x.pdf", "9")
        with self.assertRaises(InvalidOptionsError):
            reorder_pages(self.a, self.d / "x.pdf", [1, 99])
        with self.assertRaises(InvalidOptionsError):
            extract_pages(self.a, self.d / "x.pdf", "")

    def test_rotate_selected_pages_only(self):
        out = rotate_pages(self.a, self.d / "rot.pdf", 90, "2")
        rot = [p.get("/Rotate", 0) for p in PdfReader(str(out)).pages]
        self.assertEqual([0, 90, 0, 0, 0], rot)
        with self.assertRaises(InvalidOptionsError):
            rotate_pages(self.a, self.d / "rot2.pdf", 45)

    def test_split_every_n_and_by_ranges(self):
        parts = split_pdf(self.a, self.d, every=2)
        self.assertEqual([2, 2, 1], [len(PdfReader(str(p)).pages) for p in parts])
        self.assertTrue(all(p.name.startswith("a_part") for p in parts))
        sub = self.d / "r"
        sub.mkdir()
        parts = split_pdf(self.a, sub, ranges=["1-2", "3-"])
        self.assertEqual([2, 3], [len(PdfReader(str(p)).pages) for p in parts])

    def test_split_does_not_overwrite_without_consent(self):
        split_pdf(self.a, self.d, every=5)
        with self.assertRaises(OutputExistsError):
            split_pdf(self.a, self.d, every=5)
        split_pdf(self.a, self.d, every=5, overwrite=True)


class OutputSafety(Base):
    def test_existing_output_protected_and_source_untouched(self):
        before = self.a.read_bytes()
        target = self.d / "o.pdf"
        extract_pages(self.a, target, "1")
        with self.assertRaises(OutputExistsError):
            extract_pages(self.a, target, "2")
        extract_pages(self.a, target, "2", overwrite=True)
        self.assertEqual(["A-PAGE-2"], page_texts(target))
        self.assertEqual(before, self.a.read_bytes())
        with self.assertRaises(OutputPathError):
            extract_pages(self.a, self.a, "1", overwrite=True)

    def test_bad_inputs_are_friendly_errors(self):
        txt = self.d / "fake.pdf"
        txt.write_text("not a pdf")
        with self.assertRaises(InvalidFileError):
            extract_pages(txt, self.d / "o.pdf", "1")
        with self.assertRaises(InvalidFileError):
            extract_pages(self.d / "missing.pdf", self.d / "o.pdf", "1")
        (self.d / "doc.docx").write_bytes(b"x")
        with self.assertRaises(InvalidFileError):
            extract_pages(self.d / "doc.docx", self.d / "o.pdf", "1")
        with self.assertRaises(OutputPathError):
            extract_pages(self.a, self.d / "nofolder" / "o.pdf", "1")
        with self.assertRaises(OutputPathError):
            extract_pages(self.a, self.d / "o.txt", "1")

    def test_truncated_pdf_is_reported_not_crash(self):
        bad = self.d / "cut.pdf"
        bad.write_bytes(self.a.read_bytes()[:200])
        with self.assertRaises(InvalidFileError):
            extract_pages(bad, self.d / "o.pdf", "1")
        self.no_temp_files_left()

    def test_failed_write_leaves_no_partial_file(self):
        import proconvert.pdftools.ops as ops
        orig = ops._save
        calls = []

        def boom(writer, target):
            with ops._atomic(target) as tmp:
                tmp.write_bytes(b"partial")
                calls.append(tmp)
                raise RuntimeError("disk exploded")
        ops._save = boom
        try:
            with self.assertRaises(RuntimeError):
                extract_pages(self.a, self.d / "o.pdf", "1")
        finally:
            ops._save = orig
        self.assertFalse((self.d / "o.pdf").exists())
        self.assertFalse(calls[0].exists())


class Overlays(Base):
    def test_watermark_text_on_every_page_and_selected_pages(self):
        out = add_watermark(self.a, self.d / "w.pdf", "CONFIDENTIAL")
        for i, page in enumerate(PdfReader(str(out)).pages):
            txt = page.extract_text()
            self.assertIn(f"A-PAGE-{i + 1}", txt, "original content must be kept")
            self.assertIn("CONFIDENTIAL", txt)
        only2 = add_watermark(self.a, self.d / "w2.pdf", "DRAFT", pages="2")
        has = ["DRAFT" in PdfReader(str(only2)).pages[i].extract_text() for i in range(5)]
        self.assertEqual([False, True, False, False, False], has)

    def test_watermark_accepts_unicode_and_validates_options(self):
        out = add_watermark(self.a, self.d / "w3.pdf", "Confidentiel é - سري")
        self.assertEqual(5, len(PdfReader(str(out)).pages))   # must not crash; Arabic shaping is NOT claimed
        with self.assertRaises(InvalidOptionsError):
            add_watermark(self.a, self.d / "w4.pdf", "")
        with self.assertRaises(InvalidOptionsError):
            add_watermark(self.a, self.d / "w4.pdf", "x", opacity=5)

    def test_page_numbers(self):
        out = add_page_numbers(self.a, self.d / "n.pdf", fmt="Page {n} of {total}", start=1)
        t = page_texts(out)
        self.assertIn("Page 1 of 5", t[0])
        self.assertIn("Page 5 of 5", t[4])
        out2 = add_page_numbers(self.a, self.d / "n2.pdf", start=10, position="top-right")
        self.assertIn("10 / 14", page_texts(out2)[0])
        with self.assertRaises(InvalidOptionsError):
            add_page_numbers(self.a, self.d / "n3.pdf", fmt="no placeholder")


class MetadataSecuritySize(Base):
    def test_metadata_roundtrip(self):
        out = set_metadata(self.a, self.d / "md.pdf", title="My Title", author="Me", keywords="a,b")
        info = pdf_info(out)
        self.assertEqual("My Title", info["title"])
        self.assertEqual("Me", info["author"])
        self.assertEqual(5, info["pages"])
        self.assertEqual(["A-PAGE-1"], page_texts(out)[:1])

    def test_protect_requires_password_then_unprotect_needs_the_right_one(self):
        enc = protect_pdf(self.a, self.d / "enc.pdf", "s3cret!")
        self.assertTrue(PdfReader(str(enc)).is_encrypted)
        self.assertTrue(pdf_info(enc, "s3cret!")["encrypted"])
        with self.assertRaises(PasswordProtectedError):
            extract_pages(enc, self.d / "x.pdf", "1")
        with self.assertRaises(PasswordProtectedError):
            extract_pages(enc, self.d / "x.pdf", "1", password="wrong")
        with self.assertRaises(PasswordProtectedError):
            unprotect_pdf(enc, self.d / "plain.pdf", "wrong")
        plain = unprotect_pdf(enc, self.d / "plain.pdf", "s3cret!")
        self.assertFalse(PdfReader(str(plain)).is_encrypted)
        self.assertEqual("A-PAGE-3", page_texts(plain)[2])
        with self.assertRaises(InvalidOptionsError):
            protect_pdf(self.a, self.d / "e2.pdf", "ab")

    def test_compress_reports_sizes_and_keeps_text(self):
        big = make_pdf(self.d / "big.pdf", 40, "BIG")
        out, before, after = compress_pdf(big, self.d / "c.pdf", level="high")
        self.assertEqual(before, big.stat().st_size)
        self.assertEqual(after, out.stat().st_size)
        self.assertEqual("BIG-PAGE-40", page_texts(out)[39])
        with self.assertRaises(InvalidOptionsError):
            compress_pdf(big, self.d / "c2.pdf", level="extreme")


class Images(Base):
    def test_images_to_pdf_and_back(self):
        pngs = []
        for i in range(3):
            p = self.d / f"i{i}.png"
            p.write_bytes(make_png(200 + 20 * i, 120, f"IMG{i}", seed=i))
            pngs.append(p)
        pdf = images_to_pdf(pngs, self.d / "img.pdf")
        self.assertEqual(3, len(PdfReader(str(pdf)).pages))
        outs = pdf_to_images(pdf, self.d, fmt="png", dpi=72, pages="1-2")
        self.assertEqual(["img_page1.png", "img_page2.png"], [o.name for o in outs])
        from PIL import Image
        with Image.open(outs[0]) as im:
            self.assertGreater(im.width, 50)
        with self.assertRaises(OutputPathError):
            pdf_to_images(pdf, self.d, fmt="png", dpi=72, pages="1")

    def test_non_image_is_friendly_error(self):
        bad = self.d / "x.png"
        bad.write_text("nope")
        with self.assertRaises(InvalidFileError):
            images_to_pdf([bad], self.d / "bad.pdf")
        self.no_temp_files_left()


if __name__ == "__main__":
    unittest.main()
