import io
import os
import unittest
import zipfile
from pathlib import Path

from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from openpyxl import load_workbook

from proconvert.converters.xlsx_writer import sheet_name
from proconvert.core.extract import extract_text
from proconvert.workers.process_job import ConversionJob

from .base import TmpCase, corpus, squash

W = nsdecls("w")


class Edge(TmpCase):
    def test_unicode_and_spaces_in_paths_through_worker_process(self):
        src = self.tmp / "Rapport trimestriel \u00e9t\u00e9 \u2013 \u4e2d\u6587 (v2).docx"
        src.write_bytes(corpus()["docx"].read_bytes())
        out = self.tmp / "Sortie \u00e9t\u00e9 \u0645\u0631\u062d\u0628\u0627.pdf"
        res = ConversionJob(src, out, temp_root=self.work).run()
        self.assertTrue(out.is_file())
        self.assertIn("SENTINEL", extract_text(out))
        # The engine returns the RESOLVED path. On macOS the temp dir lives under the symlink
        # /var -> /private/var, so compare real locations, not raw strings.
        self.assertTrue(os.path.isabs(res.output_path))
        self.assertEqual(os.path.realpath(out), os.path.realpath(res.output_path))
        self.assertTrue(os.path.samefile(out, res.output_path))

    def test_tracked_changes_are_accepted_and_reported(self):
        d = Document()
        p = d.add_paragraph("Keep ")
        p._p.append(parse_xml(f'<w:ins {W} w:id="1" w:author="a" w:date="2026-01-01T00:00:00Z"><w:r><w:t>INSERTED </w:t></w:r></w:ins>'))
        p._p.append(parse_xml(f'<w:del {W} w:id="2" w:author="a" w:date="2026-01-01T00:00:00Z"><w:r><w:delText>DELETED</w:delText></w:r></w:del>'))
        p._p.append(parse_xml(f'<w:r {W}><w:t>end</w:t></w:r>'))
        src = self.tmp / "tc.docx"
        d.save(src)
        res = self.conv(src, "o.pdf")
        text = squash(extract_text(res.output_path))
        self.assertIn("KeepINSERTEDend", text)
        self.assertNotIn("DELETED", text)
        self.assertTrue(any("tracked changes" in w for w in res.warnings))

    def test_nested_table_and_textbox_are_reported_not_silent(self):
        d = Document()
        t = d.add_table(rows=1, cols=1)
        inner = t.cell(0, 0).add_table(rows=1, cols=1)
        inner.cell(0, 0).text = "INNER"
        t.cell(0, 0).paragraphs[0].add_run("OUTER")
        d.add_paragraph("body text here")
        body = d.element.body
        body.insert(0, parse_xml(f'<w:p {W}><w:r><w:pict><w:txbxContent><w:p><w:r><w:t>BOXED</w:t></w:r></w:p></w:txbxContent></w:pict></w:r></w:p>'))
        src = self.tmp / "n.docx"
        d.save(src)
        res = self.conv(src, "o.pdf")
        joined = " ".join(res.warnings)
        self.assertIn("nested table", joined)
        self.assertIn("text box", joined)
        self.assertIn("OUTER", squash(extract_text(res.output_path)))

    def test_xlsx_without_dimension_element(self):
        src = self.tmp / "nodim.xlsx"
        with zipfile.ZipFile(corpus()["xlsx"]) as zin, zipfile.ZipFile(src, "w", zipfile.ZIP_DEFLATED) as zout:
            for i in zin.infolist():
                data = zin.read(i.filename)
                if i.filename.startswith("xl/worksheets/sheet"):
                    import re
                    data = re.sub(rb"<dimension[^>]*/>", b"", data)
                zout.writestr(i, data)
        res = self.conv(src, "o.docx")
        self.assertIn("Widget", extract_text(res.output_path))

    def test_sheet_names_are_valid_and_unique(self):
        used: set[str] = set()
        names = [sheet_name(n, used) for n in ("Report: Q1/Q2", "report: q1/q2", "x" * 50, "x" * 50, "", "'quoted'")]
        self.assertEqual(len(names), len({n.lower() for n in names}))
        for n in names:
            self.assertTrue(1 <= len(n) <= 31 and not any(c in n for c in "[]:*?/\\"))
            self.assertFalse(n.startswith("'") or n.endswith("'"))

    def test_wide_pdf_table_to_xlsx_and_empty_cells(self):
        from proconvert.core.context import JobContext
        from proconvert.core.ir import DocumentIR, Section, Table
        from proconvert.core.options import ConversionOptions, Limits
        from proconvert.converters.xlsx_writer import write_xlsx
        ir = DocumentIR("t", [Section("page", "Page 1", [Table([["a", "", "c"], ["", "", ""], ["1", "007", "1,234.50"]])])])
        write_xlsx(ir, self.tmp / "w.xlsx", JobContext(ConversionOptions(), Limits()))
        ws = load_workbook(self.tmp / "w.xlsx")["Page 1"]
        self.assertEqual(1, ws["A3"].value)
        self.assertEqual("007", ws["B3"].value, "leading-zero identifiers stay text")
        self.assertEqual(1234.5, ws["C3"].value)

    def test_converting_twice_with_autonumbered_names_never_clobbers(self):
        from proconvert.workers.batch import plan_target
        first = plan_target(corpus()["docx"], self.tmp, "pdf", False)
        first.write_bytes(b"x")
        self.assertNotEqual(first, plan_target(corpus()["docx"], self.tmp, "pdf", False))


if __name__ == "__main__":
    unittest.main()
