"""Images -> PowerPoint, and picture of a table -> Excel (OCR)."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np
from openpyxl import load_workbook
from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation

from proconvert.converters import image_table as IT
from proconvert.converters import ocr
from proconvert.converters.image_tools import ImageLayout, convert_images, slide_size
from proconvert.core.context import CancelToken
from proconvert.core.errors import (CancelledError, DependencyMissingError, InvalidFileError, InvalidOptionsError,
                                    OutputExistsError)

FONT = Path(__file__).resolve().parent.parent / "proconvert" / "assets" / "fonts" / "DejaVuSans.ttf"
DATA = [["Product", "Region", "Units", "Price"], ["Apples", "North", "1200", "4.50"], ["Oranges", "South", "850", "3.25"],
        ["Bananas", "East", "2300", "1.10"], ["Cherries", "West", "410", "12.00"]]
needs_ocr = unittest.skipUnless(ocr.is_available(), "Tesseract/pytesseract not installed")


def table_image(path, data=DATA, style="ruled", col_w=(260, 200, 160, 160), row_h=64, font_size=30, angle=0.0, noise=0, shade=False,
                margin=60):
    w, h = sum(col_w) + 2 * margin, row_h * len(data) + 2 * margin
    im = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(str(FONT), font_size)
    xs = [margin]
    for cw in col_w:
        xs.append(xs[-1] + cw)
    ys = [margin + i * row_h for i in range(len(data) + 1)]
    if style == "ruled":
        for y in ys:
            d.line([(xs[0], y), (xs[-1], y)], fill=0, width=2)
        for x in xs:
            d.line([(x, ys[0]), (x, ys[-1])], fill=0, width=2)
    elif style == "h-rules":
        for y in (ys[0], ys[1], ys[-1]):
            d.line([(xs[0], y), (xs[-1], y)], fill=0, width=2)
    for r, row in enumerate(data):
        for c, t in enumerate(row):
            tw = d.textlength(t, font=f)
            x = xs[c] + 14 if c < 2 else xs[c + 1] - 14 - tw
            d.text((x, ys[r] + (row_h - font_size) // 2 - 2), t, fill=0, font=f)
    if shade:
        g = np.linspace(0.75, 1.0, w)[None, :]
        im = Image.fromarray((np.asarray(im, dtype=np.float32) * g).astype(np.uint8))
    if angle:
        im = im.rotate(angle, resample=Image.BICUBIC, fillcolor=255)
    if noise:
        a = np.asarray(im, dtype=np.float32) + np.random.default_rng(1).normal(0, noise, (h, w))
        im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    im.save(path)
    return Path(path)


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.d = Path(self._t.name)

    def tearDown(self):
        self._t.cleanup()

    def img(self, name, size=(400, 200), color=(200, 30, 30), **save):
        p = self.d / name
        Image.new("RGB", size, color).save(p, **save)
        return p


class ImagesToPowerPoint(Base):
    def test_one_slide_per_image_widescreen_by_default_for_fit(self):
        imgs = [self.img("a.jpg", (800, 400)), self.img("b.png", (300, 600)), self.img("c.bmp", (100, 100))]
        res = convert_images(imgs, self.d / "o.pptx", "pptx", ImageLayout("Fit", margin_mm=5))
        prs = Presentation(str(res.output_path))
        self.assertEqual(3, len(prs.slides))
        self.assertEqual(3, res.pages)
        self.assertEqual((12192000, 6858000), (prs.slide_width, prs.slide_height))        # 13.333 x 7.5 in
        for slide in prs.slides:
            pics = [s for s in slide.shapes if s.shape_type == 13]
            self.assertEqual(1, len(pics))
            p = pics[0]
            self.assertGreaterEqual(p.left, 0)
            self.assertGreaterEqual(p.top, 0)
            self.assertLessEqual(p.left + p.width, prs.slide_width)
            self.assertLessEqual(p.top + p.height, prs.slide_height)

    def test_aspect_ratio_alignment_and_original_jpeg_bytes(self):
        jpg = self.img("a.jpg", (900, 300), quality=90)
        res = convert_images([jpg], self.d / "o.pptx", "pptx", ImageLayout("A4", "auto", 10))
        prs = Presentation(str(res.output_path))
        pic = [s for s in prs.slides[0].shapes if s.shape_type == 13][0]
        self.assertAlmostEqual(3.0, pic.width / pic.height, places=2)
        self.assertAlmostEqual((prs.slide_width - 2 * pic.left) / prs.slide_width, (pic.width * 0 + prs.slide_width - 2 * pic.left) / prs.slide_width)
        self.assertLess(abs((pic.left + pic.width / 2) - prs.slide_width / 2), 2000, "horizontally centred")
        self.assertLess(abs((pic.top + pic.height / 2) - prs.slide_height / 2), 2000, "vertically centred")
        self.assertTrue(pic.image.blob == jpg.read_bytes(), "the original JPEG must be embedded unchanged")
        self.assertEqual("a.jpg", pic._element.nvPicPr.cNvPr.get("descr"))                  # alt text

    def test_slide_sizes(self):
        self.assertEqual((960.0, 540.0), slide_size(ImageLayout("Fit")))
        w, h = slide_size(ImageLayout("A4", "auto"))
        self.assertGreater(w, h)
        w, h = slide_size(ImageLayout("Letter", "portrait"))
        self.assertEqual((612.0, 792.0), (w, h))

    def test_no_silent_overwrite_and_sources_unchanged(self):
        src = self.img("a.png")
        before = src.read_bytes()
        out = self.d / "o.pptx"
        convert_images([src], out, "pptx")
        with self.assertRaises(OutputExistsError):
            convert_images([src], out, "pptx")
        convert_images([src, src], out, "pptx", overwrite=True)
        self.assertEqual(2, len(Presentation(str(out)).slides))
        self.assertEqual(before, src.read_bytes())

    @unittest.skipUnless(shutil.which("soffice"), "LibreOffice not installed")
    def test_renders_with_one_page_per_slide(self):
        import pypdf
        imgs = [self.img("a.jpg", (1600, 900)), self.img("b.png", (900, 1600))]
        pptx = convert_images(imgs, self.d / "r.pptx", "pptx", ImageLayout("Fit", margin_mm=5)).output_path
        r = subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(self.d), str(pptx)],
                           capture_output=True, text=True, timeout=180, env=dict(os.environ, HOME=str(self.d)))
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual(2, len(pypdf.PdfReader(str(self.d / "r.pdf")).pages))


class TableHelpers(unittest.TestCase):
    def test_repair_digits_only_in_numeric_columns(self):
        rows = [["Item", "Qty", "Price"], ["Olive", "1O0", "4.5O"], ["Lime", "l2", "3.25"], ["Oil", "2O", "1.10"]]
        n = IT.repair_digits(rows)
        self.assertEqual(["Olive", "100", "4.50"], rows[1])
        self.assertEqual("12", rows[2][1])
        self.assertEqual("20", rows[3][1])
        self.assertEqual(["Item", "Qty", "Price"], rows[0], "header cells are not touched")
        self.assertEqual(["Olive", "Lime", "Oil"], [r[0] for r in rows[1:]], "text columns are never touched")
        self.assertEqual(4, n)

    def test_repair_digits_also_fixes_a_numeric_first_column(self):
        rows = [["No.", "Name"], ["1", "A"], ["2", "B"], ["l0", "C"], ["1l", "D"]]
        IT.repair_digits(rows)
        self.assertEqual(["1", "2", "10", "11"], [r[0] for r in rows[1:]])

    def test_repair_digits_leaves_text_alone(self):
        rows = [["Name", "Note"], ["Olga", "Loop"], ["Ollie", "Ill"], ["Ol", "Io"]]
        self.assertEqual(0, IT.repair_digits(rows))
        self.assertEqual([["Name", "Note"], ["Olga", "Loop"], ["Ollie", "Ill"], ["Ol", "Io"]], rows)

    def test_skew_estimation_and_grid_detection(self):
        with tempfile.TemporaryDirectory() as d:
            for angle in (0.0, 1.5, -2.5):
                p = table_image(Path(d) / f"t{angle}.png", angle=angle)
                gray = IT._prepare(p, [])
                dark = IT._dark_mask(gray)
                self.assertAlmostEqual(-angle, IT.estimate_skew(dark), delta=0.31)
            straight = IT._dark_mask(IT._prepare(table_image(Path(d) / "s.png"), []))
            grid = IT.detect_grid(straight)
            self.assertEqual(6, len(grid.hlines))
            self.assertEqual(5, len(grid.vlines))


@needs_ocr
class ImagesToExcel(Base):
    def read(self, path):
        wb = load_workbook(str(path))
        ws = wb.worksheets[0]
        return wb, [[("" if c.value is None else c.value) for c in row] for row in ws.iter_rows()]

    def check(self, **style):
        src = table_image(self.d / "t.png", **style)
        res = convert_images([src], self.d / "o.xlsx", "xlsx")
        wb, rows = self.read(res.output_path)
        self.assertEqual(1, len(wb.worksheets))
        self.assertEqual(DATA[0], rows[0])
        self.assertEqual([[r[0], r[1], float(r[2]), float(r[3])] for r in DATA[1:]], [[a, b, float(c), float(d)] for a, b, c, d in rows[1:]])
        return res, rows

    def test_ruled_table_exact_and_numbers_are_numbers(self):
        res, rows = self.check(style="ruled")
        self.assertIsInstance(rows[1][2], int)
        self.assertEqual(1200, rows[1][2])
        self.assertEqual(4.5, rows[1][3])
        self.assertTrue(any("experimental" in w for w in res.warnings), "the user must be told to review OCR output")

    def test_horizontal_rules_only(self):
        self.check(style="h-rules")

    def test_borderless_table_with_a_warning(self):
        res, _ = self.check(style="borderless")
        self.assertTrue(any("no table lines" in w for w in res.warnings))

    def test_rotated_noisy_shaded_pictures(self):
        self.check(style="ruled", angle=1.5)
        os.remove(self.d / "o.xlsx")
        self.check(style="ruled", angle=-2.5, noise=10, shade=True)

    def test_two_pictures_two_sheets_named_after_the_files(self):
        a = table_image(self.d / "first.png")
        b = table_image(self.d / "second.png", style="h-rules")
        res = convert_images([a, b], self.d / "o.xlsx", "xlsx")
        wb = load_workbook(str(res.output_path))
        self.assertEqual(["first", "second"], wb.sheetnames)
        self.assertEqual(2, res.pages)

    def test_picture_without_a_table_is_a_friendly_error_and_leaves_nothing(self):
        blank = self.img("blank.png", (900, 600), (255, 255, 255))
        with self.assertRaises(InvalidFileError):
            convert_images([blank], self.d / "o.xlsx", "xlsx")
        self.assertFalse((self.d / "o.xlsx").exists())
        self.assertEqual([], [p.name for p in self.d.iterdir() if p.name.startswith(".pdftool-")])

    def test_one_bad_picture_among_good_ones_is_skipped_with_a_warning(self):
        good = table_image(self.d / "good.png")
        blank = self.img("blank.png", (900, 600), (255, 255, 255))
        res = convert_images([blank, good], self.d / "o.xlsx", "xlsx")
        self.assertEqual(["good"], load_workbook(str(res.output_path)).sheetnames)
        self.assertTrue(any("blank.png" in w and "no table" in w for w in res.warnings))

    def test_cancel_and_no_overwrite(self):
        src = table_image(self.d / "t.png")
        tok = CancelToken()
        tok.cancel()
        with self.assertRaises(CancelledError):
            convert_images([src], self.d / "c.xlsx", "xlsx", cancel=tok)
        self.assertFalse((self.d / "c.xlsx").exists())
        convert_images([src], self.d / "o.xlsx", "xlsx")
        with self.assertRaises(OutputExistsError):
            convert_images([src], self.d / "o.xlsx", "xlsx")

    def test_bad_language_option(self):
        with self.assertRaises(InvalidOptionsError):
            convert_images([table_image(self.d / "t.png")], self.d / "o.xlsx", "xlsx", language="eng; rm -rf")

    def test_missing_language_pack_is_reported_as_missing_component(self):
        with self.assertRaises(DependencyMissingError):
            convert_images([table_image(self.d / "t.png")], self.d / "o.xlsx", "xlsx", language="zzz")
        self.assertFalse((self.d / "o.xlsx").exists())


class ExcelWithoutOcr(Base):
    def test_missing_tesseract_is_a_clear_error(self):
        original = ocr.is_available
        ocr.is_available = lambda: False
        try:
            with self.assertRaises(DependencyMissingError):
                convert_images([self.img("a.png")], self.d / "o.xlsx", "xlsx")
        finally:
            ocr.is_available = original
        self.assertFalse((self.d / "o.xlsx").exists())


if __name__ == "__main__":
    unittest.main()
