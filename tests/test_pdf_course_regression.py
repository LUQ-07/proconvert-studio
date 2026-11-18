"""PDF -> Word / PowerPoint regression on a synthetic 'course handout' that mimics a real French course PDF:
running header + page numbers, headings, wrapped paragraphs, bullets with indented unmarked sub-items, numbered
items, a ruled table and a picture. The numbers below are measured, not guesses (see docs/FIDELITY_REPORT.md)."""
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path

from docx import Document
from PIL import Image
from pptx import Presentation
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import score_fidelity as sf  # noqa: E402

from proconvert.converters.docx_writer import write_docx  # noqa: E402
from proconvert.converters.pdf_reader import read_pdf  # noqa: E402
from proconvert.converters.pptx_writer import write_pptx  # noqa: E402
from proconvert.core.context import JobContext  # noqa: E402
from proconvert.core.ir import Paragraph as IRPara  # noqa: E402
from proconvert.core.ir import Picture, Table as IRTable  # noqa: E402
from proconvert.core.options import ConversionOptions, Limits  # noqa: E402

HEADER = "Maladies Transmissibles IP2"


def build_handout(path: Path, pages: int = 6) -> Path:
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=10, leading=13)
    h1 = ParagraphStyle("h1", parent=body, fontName="Helvetica-Bold", fontSize=18, leading=22, spaceBefore=6, spaceAfter=8)
    h3 = ParagraphStyle("h3", parent=body, fontName="Helvetica-Bold", fontSize=12, leading=15, spaceBefore=8, spaceAfter=4)
    item = ParagraphStyle("item", parent=body, leftIndent=18, bulletIndent=6, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=body, leftIndent=70, spaceAfter=1)

    def deco(c, doc):
        c.saveState()
        c.setFont("Helvetica", 8)
        c.drawString(25 * mm, A4[1] - 15 * mm, HEADER)
        c.drawRightString(A4[0] - 25 * mm, 12 * mm, str(doc.page))
        c.restoreState()

    png = io.BytesIO()
    Image.new("RGB", (240, 120), (30, 120, 200)).save(png, "PNG")
    png.seek(0)
    story = []
    for n in range(1, pages + 1):
        story.append(Paragraph(f"MALADIE NUMERO {n}", h1))
        story.append(Paragraph("I- DEFINITION", h3))
        story.append(Paragraph(f"C'est une maladie infectieuse contagieuse numero {n} due a un agent causal connu. " * 4, body))
        story.append(Paragraph("II- LES SIGNES CLINIQUES", h3))
        story.append(Paragraph(f"Incubation silencieuse de {n} a {n + 2} jours", item, bulletText="\u2022"))
        story.append(Paragraph("Periode d'invasion : debut brutal", item, bulletText="\u2022"))
        for s in ("Hyperthermie", "Frisson", "Cephalees", "Myalgies", "Toux seche"):
            story.append(Paragraph(f"{s} {n}", sub))
        story.append(Paragraph("III- TRAITEMENT", h3))
        for k, t in enumerate(("Repos et boissons chaudes", "Antipyretiques", "Hospitalisation si signes de gravite"), 1):
            story.append(Paragraph(f"{k}. {t} pour la maladie {n}", item))
        if n == 2:
            t = Table([["Medicament", "Dose", "Duree"], ["Penicilline G", "500 mille UI", "10 j"], ["Macrolide", "30 mg/kg", "10 j"]])
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, colors.black), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]))
            story += [Spacer(1, 6), t, Spacer(1, 6)]
        if n == 3:
            story.append(RLImage(io.BytesIO(png.getvalue()), width=60 * mm, height=30 * mm))
        story.append(Spacer(1, 14 * mm))
        from reportlab.platypus import PageBreak
        story.append(PageBreak())
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=25 * mm, rightMargin=25 * mm, topMargin=30 * mm, bottomMargin=25 * mm).build(story, onFirstPage=deco, onLaterPages=deco)
    return path


def ctx():
    return JobContext(ConversionOptions(), Limits())


class CourseHandoutRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.pdf = build_handout(Path(cls.tmp.name) / "handout.pdf")
        cls.ctx = ctx()
        cls.ir = read_pdf(cls.pdf, cls.ctx)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def paras(self):
        return [b for b in self.ir.iter_blocks() if isinstance(b, IRPara)]

    def test_running_header_and_page_numbers_leave_the_body(self):
        self.assertEqual(HEADER, self.ir.header)
        texts = [p.text for p in self.paras()]
        self.assertNotIn(HEADER, texts)
        self.assertFalse([t for t in texts if re.fullmatch(r"\d{1,3}", t)], "page numbers must not appear as paragraphs")

    def test_headings_lists_and_nested_items(self):
        ps = self.paras()
        self.assertEqual(6, sum(1 for p in ps if p.heading == 1 and p.text.startswith("MALADIE NUMERO")))
        subs = [p for p in ps if p.bullet and p.level == 1]
        self.assertEqual(30, len(subs), "each indented line is its own sub-item (5 per page x 6)")
        self.assertEqual("Hyperthermie 1", subs[0].text)
        self.assertEqual(12, sum(1 for p in ps if p.bullet and p.level == 0))
        nums = [p for p in ps if p.number is not None]
        self.assertEqual([1, 2, 3] * 6, [p.number for p in nums])

    def test_table_and_picture_are_found(self):
        tables = [b for b in self.ir.iter_blocks() if isinstance(b, IRTable)]
        self.assertEqual(1, len(tables))
        self.assertEqual(["Medicament", "Dose", "Duree"], tables[0].rows[0])
        self.assertEqual(1, sum(1 for b in self.ir.iter_blocks() if isinstance(b, Picture)))

    def test_word_output_text_fidelity_and_structure(self):
        out = Path(self.tmp.name) / "o.docx"
        write_docx(self.ir, out, ctx())
        s = sf.score(self.pdf, out)
        self.assertGreaterEqual(s["recall"], 0.995, s)
        self.assertGreaterEqual(s["precision"], 0.995, s)
        d = Document(str(out))
        self.assertEqual(HEADER, d.sections[0].header.paragraphs[0].text)
        self.assertEqual(1, len(d.tables))
        self.assertEqual(1, len(d.inline_shapes))
        self.assertGreaterEqual(sum(1 for p in d.paragraphs if p.style.name == "List Bullet 2"), 30)

    def test_powerpoint_output_has_no_empty_or_page_titled_slides(self):
        out = Path(self.tmp.name) / "o.pptx"
        write_pptx(self.ir, out, ctx())
        s = sf.score(self.pdf, out)
        self.assertGreaterEqual(s["recall"], 0.995, s)
        self.assertGreaterEqual(s["precision"], 0.995, s)
        prs = Presentation(str(out))
        self.assertLessEqual(len(prs.slides), 20, "6 pages must not explode into dozens of slides")
        for i, slide in enumerate(prs.slides, 1):
            title = slide.shapes.title.text_frame.text if slide.shapes.title is not None else ""
            self.assertFalse(re.fullmatch(r"Page \d+( \(continued\))?", title), f"slide {i}: '{title}'")
            body = [sh for sh in slide.shapes if sh.shape_type in (13, 19) or (sh.has_text_frame and sh.text_frame.text.strip() and sh != slide.shapes.title and sh.text_frame.text != HEADER)]
            self.assertTrue(body, f"slide {i} is empty")
            self.assertTrue(any(sh.has_text_frame and sh.text_frame.text == HEADER for sh in slide.shapes), f"slide {i} lost the running header")


if __name__ == "__main__":
    unittest.main()
