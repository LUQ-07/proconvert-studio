"""Phase 1 DOCX fidelity: numbered lists, footnotes/endnotes, headers/footers (all built programmatically)."""
import io
import re
import tempfile
import unittest
import zipfile
from pathlib import Path

from docx import Document
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn

from proconvert.converters.docx_reader import read_docx
from proconvert.core.context import JobContext
from proconvert.core.ir import DocumentIR, Paragraph, Section
from proconvert.core.options import ConversionOptions, Limits


def _ctx():
    return JobContext(ConversionOptions(), Limits())


def _add_numbering(doc):
    root = doc.part.numbering_part.element
    abstract = parse_xml(
        f'<w:abstractNum {nsdecls("w")} w:abstractNumId="90"><w:lvl w:ilvl="0"><w:start w:val="1"/>'
        '<w:numFmt w:val="decimal"/></w:lvl><w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/></w:lvl>'
        '</w:abstractNum>')
    bullet = parse_xml(
        f'<w:abstractNum {nsdecls("w")} w:abstractNumId="91"><w:lvl w:ilvl="0"><w:numFmt w:val="bullet"/></w:lvl></w:abstractNum>')
    root.insert(0, bullet)
    root.insert(0, abstract)
    root.append(parse_xml(f'<w:num {nsdecls("w")} w:numId="90"><w:abstractNumId w:val="90"/></w:num>'))
    root.append(parse_xml(f'<w:num {nsdecls("w")} w:numId="91"><w:abstractNumId w:val="91"/></w:num>'))


def _numbered(doc, text, num_id, ilvl=0):
    p = doc.add_paragraph(text)
    ppr = p._p.get_or_add_pPr()
    ppr.append(parse_xml(f'<w:numPr {nsdecls("w")}><w:ilvl w:val="{ilvl}"/><w:numId w:val="{num_id}"/></w:numPr>'))
    return p


def _inject_footnotes(path: Path, notes: list[str]) -> None:
    W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
    for i, t in enumerate(notes, 1):
        body += f'<w:footnote w:id="{i}"><w:p><w:r><w:t>{t}</w:t></w:r></w:p></w:footnote>'
    xml = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:footnotes {W}>{body}</w:footnotes>'
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "[Content_Types].xml":
                data = data.replace(b"</Types>", b'<Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/></Types>')
            elif item.filename == "word/_rels/document.xml.rels":
                data = data.replace(b"</Relationships>", b'<Relationship Id="rIdFn1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" Target="footnotes.xml"/></Relationships>')
            zout.writestr(item, data)
        zout.writestr("word/footnotes.xml", xml)
    tmp.replace(path)


def build(path: Path) -> Path:
    doc = Document()
    _add_numbering(doc)
    doc.add_heading("Report", 1)
    _numbered(doc, "First step", 90)
    _numbered(doc, "Second step", 90)
    _numbered(doc, "Sub a", 90, 1)
    _numbered(doc, "Sub b", 90, 1)
    _numbered(doc, "Third step", 90)
    doc.add_paragraph("Between lists")
    _numbered(doc, "Dot one", 91)
    doc.add_paragraph("Style numbered one", style="List Number")
    doc.add_paragraph("Style numbered two", style="List Number")
    sec = doc.sections[0]
    sec.header.paragraphs[0].text = "ACME Confidential"
    sec.footer.paragraphs[0].text = "Internal use only"
    doc.save(str(path))
    _inject_footnotes(path, ["First footnote text", "Second footnote text"])
    return path


class DocxFidelity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = build(Path(cls.tmp.name) / "fid.docx")
        cls.ctx = _ctx()
        cls.ir = read_docx(cls.path, cls.ctx)
        cls.paras = [b for b in cls.ir.iter_blocks() if isinstance(b, Paragraph)]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def num(self, text):
        return next(p for p in self.paras if p.text == text)

    def test_numbered_list_numbers_restored_with_nesting(self):
        self.assertEqual(1, self.num("First step").number)
        self.assertEqual(2, self.num("Second step").number)
        self.assertEqual(1, self.num("Sub a").number)
        self.assertEqual(2, self.num("Sub b").number)
        self.assertEqual(3, self.num("Third step").number, "outer counter continues after the nested items")
        self.assertFalse(self.num("First step").bullet)

    def test_bullet_numbering_definition_stays_a_bullet(self):
        p = self.num("Dot one")
        self.assertIsNone(p.number)
        self.assertTrue(p.bullet)

    def test_style_based_numbering(self):
        self.assertEqual(1, self.num("Style numbered one").number)
        self.assertEqual(2, self.num("Style numbered two").number)

    def test_footnotes_become_numbered_notes_and_are_reported(self):
        texts = [p.text for p in self.paras]
        self.assertIn("Notes", texts)
        self.assertEqual(1, self.num("First footnote text").number)
        self.assertEqual(2, self.num("Second footnote text").number)
        self.assertTrue(any("footnote" in w.lower() for w in self.ctx.warnings))

    def test_header_and_footer_extracted(self):
        self.assertEqual("ACME Confidential", self.ir.header)
        self.assertEqual("Internal use only", self.ir.footer)

    def test_plain_document_without_numbering_part_still_reads(self):
        doc = Document()
        doc.add_paragraph("just text")
        p = Path(self.tmp.name) / "plain.docx"
        doc.save(str(p))
        ir = read_docx(p, _ctx())
        self.assertEqual("", ir.header)
        self.assertEqual(["just text"], [b.text for b in ir.iter_blocks()])


class WritersKeepNumbersAndHeaders(unittest.TestCase):
    def _ir(self):
        ir = DocumentIR("t", header="HDR-TOKEN", footer="FTR-TOKEN")
        ir.sections.append(Section("flow", "Doc", [
            Paragraph.plain("alpha item", number=1), Paragraph.plain("beta item", number=2),
            Paragraph.plain("bullet item", bullet=True), Paragraph.plain("plain")]))
        return ir

    def test_docx_writer_prefixes_numbers_and_sets_header_footer(self):
        from proconvert.converters.docx_writer import write_docx
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o.docx"
            write_docx(self._ir(), out, _ctx())
            doc = Document(str(out))
            texts = [p.text for p in doc.paragraphs]
            self.assertIn("1.\talpha item", texts)
            self.assertIn("2.\tbeta item", texts)
            self.assertEqual("HDR-TOKEN", doc.sections[0].header.paragraphs[0].text)
            self.assertEqual("FTR-TOKEN", doc.sections[0].footer.paragraphs[0].text)

    def test_pdf_writer_draws_numbers_and_running_text(self):
        from proconvert.converters.pdf_writer import write_pdf
        import pdfplumber
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o.pdf"
            write_pdf(self._ir(), out, _ctx())
            with pdfplumber.open(str(out)) as pdf:
                text = pdf.pages[0].extract_text()
            self.assertRegex(text, r"1\.\s*alpha item")
            self.assertRegex(text, r"2\.\s*beta item")
            self.assertIn("HDR-TOKEN", text)
            self.assertIn("FTR-TOKEN", text)

    def test_round_trip_docx_to_docx_numbers_survive(self):
        from proconvert.converters.docx_writer import write_docx
        with tempfile.TemporaryDirectory() as d:
            src = build(Path(d) / "s.docx")
            ir = read_docx(src, _ctx())
            out = Path(d) / "o.docx"
            write_docx(ir, out, _ctx())
            texts = [p.text for p in Document(str(out)).paragraphs]
            self.assertIn("3.\tThird step", texts)
            self.assertIn("1.\tFirst footnote text", texts)


class PdfNumberedLists(unittest.TestCase):
    def test_numbered_items_survive_ir_to_pdf_to_ir(self):
        from proconvert.converters.pdf_reader import read_pdf
        from proconvert.converters.pdf_writer import write_pdf
        ir = DocumentIR("t")
        ir.sections.append(Section("flow", "Doc", [
            Paragraph.plain("Introductory sentence for the list."),
            Paragraph.plain("Open the settings dialog", number=1),
            Paragraph.plain("Choose the output folder", number=2),
            Paragraph.plain("Press convert", number=3),
            Paragraph.plain("Closing sentence after the list.")]))
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "n.pdf"
            write_pdf(ir, out, _ctx())
            back = read_pdf(out, _ctx())
        items = [b for b in back.iter_blocks() if isinstance(b, Paragraph) and b.number is not None]
        self.assertEqual([1, 2, 3], [p.number for p in items])
        self.assertEqual("Open the settings dialog", items[0].text)

    def test_year_like_text_is_not_a_list_item(self):
        from proconvert.converters.pdf_reader import _NUMBERED
        self.assertIsNone(_NUMBERED.match("2024. was a long year"))
        self.assertIsNotNone(_NUMBERED.match("12) twelfth item"))


class SymbolGlyphs(unittest.TestCase):
    def test_wingdings_private_use_characters_become_real_unicode(self):
        from proconvert.utils.text import clean_block, clean_inline, map_symbol_glyphs
        self.assertEqual("\u2022 item", clean_inline("\uf0b7 item"))
        self.assertEqual("a \u2192 b", clean_block("a \uf0e0 b"))
        self.assertEqual("\u2713 ok", map_symbol_glyphs("\uf0fc ok"))
        self.assertEqual("icon text", map_symbol_glyphs("\ue900icon text"), "unknown private-use code points are dropped")
        self.assertEqual("plain \u00e9\u4e2d", map_symbol_glyphs("plain \u00e9\u4e2d"), "ordinary text is untouched")

    def test_pptx_arrow_glyph_survives_into_the_pdf_without_question_marks(self):
        from pptx import Presentation
        from proconvert.converters.pdf_writer import write_pdf
        from proconvert.converters.pptx_reader import read_pptx
        import pdfplumber
        with tempfile.TemporaryDirectory() as d:
            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[5])
            slide.shapes.title.text = "Arrow test"
            box = slide.shapes.add_textbox(0, 0, 3000000, 500000)
            box.text_frame.text = "cause \uf0e0 effect"
            src = Path(d) / "a.pptx"
            prs.save(str(src))
            ctx = _ctx()
            ir = read_pptx(src, ctx)
            write_pdf(ir, Path(d) / "o.pdf", ctx)
            self.assertFalse(any("replaced with '?'" in w for w in ctx.warnings), ctx.warnings)
            with pdfplumber.open(str(Path(d) / "o.pdf")) as pdf:
                self.assertIn("cause \u2192 effect", pdf.pages[0].extract_text())
