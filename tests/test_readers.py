import unittest

from proconvert.converters.xlsx_reader import format_value
from proconvert.core.context import JobContext
from proconvert.core.ir import Paragraph, Picture, Table, ir_stats
from proconvert.core.options import ConversionOptions, Limits
from proconvert.converters.registry import get_reader

from .base import corpus, squash


def read(key, fmt, **opt):
    ctx = JobContext(ConversionOptions(**opt), Limits())
    return get_reader(fmt)(corpus()[key], ctx), ctx


def paras(ir):
    return [b for b in ir.iter_blocks() if isinstance(b, Paragraph)]


class PdfReader(unittest.TestCase):
    def test_text_headings_bullets_and_spaces(self):
        ir, _ = read("text_pdf", "pdf")
        self.assertEqual(5, len(ir.sections))
        texts = [p.text for p in paras(ir)]
        self.assertTrue(any("SENTINEL-PDF-P1 This paragraph discusses" in t for t in texts), "words must be separated by spaces")
        heads = [p for p in paras(ir) if p.heading]
        self.assertIn("Quarterly Business Review", [h.text for h in heads])
        self.assertTrue(any(h.text == "Section 3 Overview" for h in heads))
        bullets = [p for p in paras(ir) if p.bullet]
        self.assertEqual(10, len(bullets))
        self.assertEqual("First bullet point item", bullets[0].text)

    def test_ruled_table_extracted_and_not_duplicated_as_text(self):
        ir, _ = read("text_pdf", "pdf")
        tables = [b for b in ir.iter_blocks() if isinstance(b, Table)]
        self.assertEqual(1, len(tables))
        self.assertEqual(["Region", "Revenue", "Growth"], tables[0].rows[0])
        self.assertEqual(["West", "1500", "6.2"], tables[0].rows[3])
        self.assertFalse(any(p.text.strip() == "North" for p in paras(ir)))

    def test_image_extracted_with_size(self):
        ir, _ = read("text_pdf", "pdf")
        pics = [b for b in ir.iter_blocks() if isinstance(b, Picture)]
        self.assertEqual(1, len(pics))
        self.assertEqual((300, 180), (pics[0].width_px, pics[0].height_px))
        self.assertAlmostEqual(240, pics[0].display_w_pt, delta=1)

    def test_running_headers_removed_with_warning(self):
        ir, ctx = read("text_pdf", "pdf")
        self.assertFalse(any("Acme Corp" in p.text for p in paras(ir)))
        self.assertTrue(any("repeating header" in w for w in ctx.warnings))
        ir2, _ = read("text_pdf", "pdf", strip_headers_footers=False)
        self.assertTrue(any("Acme Corp" in p.text for p in paras(ir2)))

    def test_two_column_reading_order(self):
        ir, _ = read("two_col_pdf", "pdf")
        order = [("L" if "LEFTCOL" in p.text else "R") for p in paras(ir) if "COL" in p.text]
        self.assertEqual("LLLLLLRRRRRR", "".join(order))
        ir2, _ = read("two_col_pdf", "pdf", detect_columns=False)
        order2 = "".join(("L" if "LEFTCOL" in p.text else "R") for p in paras(ir2) if "COL" in p.text)
        self.assertNotEqual("LLLLLLRRRRRR", order2, "without detection columns interleave (proves the feature does work)")

    def test_page_selection(self):
        ir, _ = read("text_pdf", "pdf", pdf_pages="2-3")
        self.assertEqual(["Page 2", "Page 3"], [s.label for s in ir.sections])

    def test_scanned_pdf_includes_page_image_and_warns(self):
        ir, ctx = read("scanned_pdf", "pdf")
        self.assertEqual(0, ir_stats(ir).characters)
        self.assertEqual(1, ir_stats(ir).pictures)
        self.assertTrue(any("scanned" in w.lower() for w in ctx.warnings))

    def test_ocr_when_available(self):
        from proconvert.converters import ocr
        if not ocr.is_available():
            self.skipTest("no OCR engine installed")
        ir, ctx = read("scanned_pdf", "pdf", ocr_enabled=True)
        self.assertIn("INVOICE", squash("".join(p.text for p in paras(ir))).upper())
        self.assertTrue(any("OCR" in w for w in ctx.warnings))


class DocxReader(unittest.TestCase):
    def test_structure(self):
        ir, _ = read("docx", "docx")
        ps = paras(ir)
        self.assertEqual(1, ps[0].heading)
        mixed = next(p for p in ps if p.text.startswith("Bold part"))
        self.assertTrue(mixed.runs[0].bold and mixed.runs[1].italic)
        bullets = [p for p in ps if p.bullet]
        self.assertEqual([0, 1], [b.level for b in bullets])
        t = next(b for b in ir.iter_blocks() if isinstance(b, Table))
        self.assertEqual("DOCX-R2C2", t.rows[2][2])
        self.assertEqual("", t.rows[0][1], "merged cell must not repeat its text")
        self.assertEqual(1, sum(isinstance(b, Picture) for b in ir.iter_blocks()))


class PptxReader(unittest.TestCase):
    def test_slides(self):
        ir, ctx = read("pptx", "pptx")
        self.assertEqual(5, len(ir.sections))
        self.assertEqual("SENTINEL-PPTX-TITLE Launch Plan", ir.sections[0].blocks[0].text)
        s2 = ir.sections[1].blocks
        self.assertTrue(s2[1].bullet and s2[1].text == "PPTX-BULLET-ONE")
        self.assertTrue(any(isinstance(b, Table) for b in ir.sections[2].blocks))
        self.assertTrue(any(isinstance(b, Picture) for b in ir.sections[3].blocks))

    def test_chart_becomes_data_table(self):
        ir, ctx = read("pptx", "pptx")
        tbl = next(b for b in ir.sections[4].blocks if isinstance(b, Table))
        self.assertEqual([["", "Sales"], ["Q1", "10"], ["Q2", "20"], ["Q3", "30"]], tbl.rows)
        self.assertTrue(any("chart" in w for w in ctx.warnings))


class XlsxReader(unittest.TestCase):
    def test_values_formats_and_skips(self):
        ir, ctx = read("xlsx", "xlsx")
        self.assertEqual(["Sales", "Notes"], [s.label for s in ir.sections])
        rows = ir.sections[0].blocks[0].rows
        self.assertEqual(["Item", "Qty", "Price", "Total", "Margin", "Date"], rows[0])
        self.assertEqual(["Widget", "3", "$9.50", "28.5", "25.6%", "2026-01-15"], rows[1])
        self.assertEqual("$1,234.50", rows[2][2])
        self.assertEqual("12345", rows[2][3])
        self.assertEqual("=EVIL()", rows[4][0], "text results that look like formulas are kept as text")
        warns = " ".join(ctx.warnings)
        self.assertIn("hidden sheet", warns)
        self.assertIn("empty sheet", warns)
        self.assertNotIn("no stored result", warns)

    def test_uncached_formulas_reported(self):
        ir, ctx = read("xlsx_uncached", "xlsx")
        self.assertTrue(any("no stored result" in w for w in ctx.warnings))

    def test_row_limit_is_reported_not_silent(self):
        ctx = JobContext(ConversionOptions(), Limits(max_sheet_rows=2))
        ir = get_reader("xlsx")(corpus()["xlsx"], ctx)
        self.assertEqual(2, len(ir.sections[0].blocks[0].rows))
        self.assertTrue(any("safety limit" in w for w in ctx.warnings))

    def test_number_formatting(self):
        cases = [((1234.5, "#,##0.00"), "1,234.50"), ((0.256, "0.0%"), "25.6%"), ((5, "General"), "5"),
                 ((0.1 + 0.2, "General"), "0.3"), ((-3.14159, "0.00"), "-3.14"), ((1234567, "#,##0"), "1,234,567"),
                 ((True, None), "TRUE"), ((None, None), "")]
        for (v, f), want in cases:
            self.assertEqual(want, format_value(v, f), (v, f))


if __name__ == "__main__":
    unittest.main()
