"""All 12 routes end to end: output exists, re-opens with an independent parser, holds the expected content."""
import unittest
from pathlib import Path

from docx import Document
from openpyxl import load_workbook
from pptx import Presentation
from pypdf import PdfReader

from proconvert import config
from proconvert.core.capabilities import all_routes, route_for
from proconvert.core.extract import extract_text
from proconvert.core.options import ConversionOptions

from .base import TmpCase, corpus, squash

SOURCE = {"pdf": ("text_pdf", "SENTINEL-PDF-P1"), "docx": ("docx", "SENTINEL-DOCX-INTRO"),
          "pptx": ("pptx", "SENTINEL-PPTX-TITLE"), "xlsx": ("xlsx", "SENTINEL-XLSX-NOTE")}
TABLE_TOKEN = {"pdf": "Revenue", "docx": "DOCX-R2C2", "pptx": "PPTX-R2C2", "xlsx": "$1,234.50"}


class AllRoutes(TmpCase):
    def test_every_route_produces_valid_output_with_content(self):
        for r in all_routes():
            with self.subTest(route=r.key):
                key, token = SOURCE[r.source]
                res = self.conv(corpus()[key], f"{r.source}_to.{r.target}")
                out = Path(res.output_path)
                self.assertTrue(out.is_file() and out.stat().st_size > 0)
                self.assertEqual(r.status, res.status)
                text = squash(extract_text(out))
                self.assertIn(squash(token), text)
                self.assertIn(squash(TABLE_TOKEN[r.source]), text, "table content must survive")
        self.assertNoLeftovers()

    def test_all_sources_of_twelve_have_tests(self):
        self.assertEqual(12 - len(config.DISABLED_ROUTES), len(all_routes()))


class RouteDetails(TmpCase):
    def test_pdf_to_docx_keeps_structure_and_image(self):
        out = Path(self.conv(corpus()["text_pdf"], "o.docx").output_path)
        d = Document(str(out))
        styles = [p.style.name for p in d.paragraphs]
        self.assertIn("Heading 1", styles)
        self.assertIn("List Bullet", styles)
        self.assertEqual(1, len(d.tables))
        self.assertEqual("North", d.tables[0].cell(1, 0).text)
        self.assertEqual(1, len(d.inline_shapes))

    def test_pdf_to_xlsx_numbers_are_numbers(self):
        out = Path(self.conv(corpus()["text_pdf"], "o.xlsx").output_path)
        wb = load_workbook(str(out))
        ws = wb["Page 2"]
        vals = {c.value for row in ws.iter_rows() for c in row}
        self.assertIn(1200, vals)
        self.assertIn(4.5, vals)

    def test_docx_to_xlsx_layout(self):
        out = Path(self.conv(corpus()["docx"], "o.xlsx").output_path)
        wb = load_workbook(str(out))
        self.assertEqual(["Document", "Table 1"], wb.sheetnames)
        self.assertEqual("DOCX-R2C2", wb["Table 1"]["C3"].value)
        self.assertEqual(1, len(wb["Document"]._images))

    def test_docx_to_pptx_headings_become_slides(self):
        out = Path(self.conv(corpus()["docx"], "o.pptx").output_path)
        prs = Presentation(str(out))
        titles = [s.shapes.title.text for s in prs.slides]
        self.assertIn("Project Handbook", titles)
        self.assertIn("Details", titles)

    def test_pptx_to_docx_slide_titles_and_chart_data(self):
        res = self.conv(corpus()["pptx"], "o.docx")
        d = Document(res.output_path)
        self.assertIn("Agenda", [p.text for p in d.paragraphs])
        self.assertTrue(any("chart" in w for w in res.warnings))
        self.assertTrue(any(c.text == "30" for t in d.tables for r in t.rows for c in r.cells))

    def test_xlsx_to_pdf_number_formats(self):
        res = self.conv(corpus()["xlsx"], "o.pdf")
        text = extract_text(res.output_path)
        self.assertIn("$1,234.50", text)
        self.assertIn("25.6%", text)

    def test_xlsx_to_docx_and_pptx(self):
        d = Document(self.conv(corpus()["xlsx"], "o.docx").output_path)
        self.assertEqual("Item", d.tables[0].cell(0, 0).text)
        prs = Presentation(self.conv(corpus()["xlsx"], "o.pptx").output_path)
        self.assertEqual(2, len(prs.slides))

    def test_experimental_flag_on_result(self):
        for (src, dst), expected in ((("pdf", "pptx"), "experimental"), (("pdf", "docx"), "supported"), (("docx", "pdf"), "supported")):
            if route_for(src, dst) is None:          # removed through config.DISABLED_ROUTES
                continue
            key = {"pdf": "text_pdf", "docx": "docx"}[src]
            self.assertEqual(expected, self.conv(corpus()[key], f"flag.{dst}").status, f"{src}->{dst}")

    def test_quality_preset_downsizes_images(self):
        from proconvert.core.context import JobContext
        from proconvert.core.images import normalize_image
        from proconvert.core.options import Limits
        from .make_corpus import make_png
        big = make_png(3000, 2000)
        ctx = JobContext(ConversionOptions(quality="standard"), Limits())
        pic = normalize_image(big, ctx)
        self.assertEqual(1600, max(pic.width_px, pic.height_px))
        pic2 = normalize_image(big, JobContext(ConversionOptions(quality="original"), Limits()))
        self.assertEqual(3000, pic2.width_px)


class WriterSafety(TmpCase):
    def test_formula_text_never_becomes_formula(self):
        from proconvert.core.context import JobContext
        from proconvert.core.ir import DocumentIR, Paragraph, Section, Table
        from proconvert.core.options import Limits
        from proconvert.converters.xlsx_writer import write_xlsx
        import zipfile
        ir = DocumentIR("t", [Section("page", "P", [Paragraph.plain("=HYPERLINK(\"http://evil\",\"x\")"),
                                                    Table([["=1+1", "@SUM(A1)"], ["+cmd", "-2+3"]])])])
        p = self.tmp / "f.xlsx"
        write_xlsx(ir, p, JobContext(ConversionOptions(), Limits()))
        with zipfile.ZipFile(p) as z:
            xml = z.read("xl/worksheets/sheet1.xml").decode()
        self.assertNotIn("<f>", xml)
        ws = load_workbook(str(p))["P"]
        self.assertEqual("=1+1", ws["A2"].value)
        self.assertEqual("s", ws["A2"].data_type)

    def test_unicode_and_control_characters(self):
        from proconvert.core.context import JobContext
        from proconvert.core.ir import DocumentIR, Paragraph, Section
        from proconvert.core.options import Limits
        from proconvert.converters.docx_writer import write_docx
        from proconvert.converters.pdf_writer import write_pdf
        text = "Caf\u00e9 \u0394\u03b5\u03b9\u03b3\u03bc\u03b1 \u041f\u0440\u0438\u0432\u0435\u0442 ctrl\x01\x08 end"
        ir = DocumentIR("t", [Section("flow", "d", [Paragraph.plain(text)])])
        ctx = JobContext(ConversionOptions(), Limits())
        write_docx(ir, self.tmp / "u.docx", ctx)
        write_pdf(ir, self.tmp / "u.pdf", ctx)
        self.assertIn("\u041f\u0440\u0438\u0432\u0435\u0442", extract_text(self.tmp / "u.docx"))
        self.assertIn("Caf\u00e9", extract_text(self.tmp / "u.pdf"))
        self.assertEqual([], ctx.warnings)

    def test_cjk_and_rtl_are_reported_not_silent(self):
        from proconvert.core.context import JobContext
        from proconvert.core.ir import DocumentIR, Paragraph, Section
        from proconvert.core.options import Limits
        from proconvert.converters.pdf_writer import write_pdf
        ir = DocumentIR("t", [Section("flow", "d", [Paragraph.plain("\u4e2d\u6587 \u0645\u0631\u062d\u0628\u0627")])])
        ctx = JobContext(ConversionOptions(), Limits())
        write_pdf(ir, self.tmp / "c.pdf", ctx)
        joined = " ".join(ctx.warnings)
        self.assertIn("cannot be drawn", joined)
        self.assertIn("Right-to-left", joined)

    def test_huge_cell_does_not_crash_pdf_layout(self):
        from proconvert.core.context import JobContext
        from proconvert.core.ir import DocumentIR, Section, Table
        from proconvert.core.options import Limits
        from proconvert.converters.pdf_writer import write_pdf
        ir = DocumentIR("t", [Section("sheet", "S", [Table([["h1", "h2", "h3"], ["x" * 20000 + " word " * 4000, "b", "c"]])])])
        ctx = JobContext(ConversionOptions(), Limits())
        write_pdf(ir, self.tmp / "h.pdf", ctx)
        self.assertTrue(any("shortened" in w for w in ctx.warnings))

    def test_wide_table_goes_landscape_and_pptx_splits_columns(self):
        from proconvert.core.context import JobContext
        from proconvert.core.ir import DocumentIR, Section, Table
        from proconvert.core.options import Limits
        from proconvert.converters.pdf_writer import write_pdf
        from proconvert.converters.pptx_writer import write_pptx
        rows = [[f"H{c}" for c in range(20)]] + [[f"v{r}-{c}" for c in range(20)] for r in range(5)]
        ir = DocumentIR("w", [Section("sheet", "Wide", [Table(rows)])])
        ctx = JobContext(ConversionOptions(), Limits())
        write_pdf(ir, self.tmp / "w.pdf", ctx)
        pg = PdfReader(str(self.tmp / "w.pdf")).pages[0]
        self.assertGreater(float(pg.mediabox.width), float(pg.mediabox.height))
        write_pptx(ir, self.tmp / "w.pptx", ctx)
        text = squash(extract_text(self.tmp / "w.pptx"))
        for c in range(20):
            self.assertIn(f"H{c}", text)

    def test_pptx_pagination_never_loses_text(self):
        from proconvert.core.context import JobContext
        from proconvert.core.ir import DocumentIR, Paragraph, Section
        from proconvert.core.options import Limits
        from proconvert.converters.pptx_writer import write_pptx
        paras = [Paragraph.plain(f"PARA{i} " + "word " * 80) for i in range(60)]
        ir = DocumentIR("long", [Section("flow", "d", paras)])
        write_pptx(ir, self.tmp / "l.pptx", JobContext(ConversionOptions(), Limits()))
        prs = Presentation(str(self.tmp / "l.pptx"))
        self.assertGreater(len(prs.slides), 3)
        text = extract_text(self.tmp / "l.pptx")
        for i in range(60):
            self.assertIn(f"PARA{i} ", text)


if __name__ == "__main__":
    unittest.main()
