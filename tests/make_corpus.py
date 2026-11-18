"""Deterministic test-corpus generator. Every file is built programmatically (no binary fixtures)."""
from __future__ import annotations

import io
import os
import random
import zipfile
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = Path(__file__).resolve().parent.parent / "proconvert" / "assets" / "fonts" / "DejaVuSans.ttf"


def make_png(w=320, h=200, text="IMG", seed=1) -> bytes:
    rnd = random.Random(seed)
    img = Image.new("RGB", (w, h), (rnd.randint(40, 215), rnd.randint(40, 215), rnd.randint(40, 215)))
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, w - 10, h - 10], outline=(255, 255, 255), width=4)
    d.text((24, 24), text, fill=(255, 255, 255), font=ImageFont.truetype(str(FONT), 28))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# ----------------------------------------------------------------------------- PDF
def text_pdf(path: Path, pages=5) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ss = getSampleStyleSheet()
    story = [Paragraph("Quarterly Business Review", ss["Title"]), Paragraph("SENTINEL-PDF-INTRO opening paragraph of the review. " * 4, ss["BodyText"])]
    for p in range(1, pages + 1):
        story.append(Paragraph(f"Section {p} Overview", ss["Heading1"]))
        story.append(Paragraph((f"SENTINEL-PDF-P{p} This paragraph discusses topic {p} in some detail, "
                                "covering goals, results and next steps for the team. ") * 6, ss["BodyText"]))
        story.append(Paragraph("First bullet point item", ss["Bullet"], bulletText="\u2022"))
        story.append(Paragraph("Second bullet point item", ss["Bullet"], bulletText="\u2022"))
        if p == 2:
            t = Table([["Region", "Revenue", "Growth"], ["North", "1200", "4.5"], ["South", "980", "3.1"], ["West", "1500", "6.2"]])
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.8, colors.black)]))
            story += [Spacer(1, 10), t, Spacer(1, 10)]
        if p == 3:
            story += [RLImage(io.BytesIO(make_png(300, 180, "FIG")), width=240, height=144)]
        story.append(PageBreak())

    def deco(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.drawString(50, 815, "Acme Corp Confidential Header")
        canvas.drawString(280, 25, f"Page {doc.page}")

    SimpleDocTemplate(str(path), pagesize=A4, title="QBR").build(story, onFirstPage=deco, onLaterPages=deco)
    return path


def two_column_pdf(path: Path) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import BaseDocTemplate, Frame, FrameBreak, PageTemplate, Paragraph

    ss = getSampleStyleSheet()
    w, h = A4
    gap = 30
    colw = (w - 100 - gap) / 2
    f1 = Frame(50, 60, colw, h - 160, id="l")
    f2 = Frame(50 + colw + gap, 60, colw, h - 160, id="r")
    doc = BaseDocTemplate(str(path), pagesize=A4)
    doc.addPageTemplates([PageTemplate(frames=[f1, f2])])
    left = [Paragraph(f"LEFTCOL paragraph {i}. " + "Alpha beta gamma delta epsilon zeta eta theta. " * 5, ss["BodyText"]) for i in range(1, 7)]
    right = [Paragraph(f"RIGHTCOL paragraph {i}. " + "Kappa lambda mu nu xi omicron pi rho. " * 5, ss["BodyText"]) for i in range(1, 7)]
    doc.build(left + [FrameBreak()] + right)
    return path


def scanned_pdf(path: Path) -> Path:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    img = Image.new("L", (1240, 1754), 255)
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(FONT), 54)
    for i, line in enumerate(["INVOICE SCANNED DOCUMENT", "Total amount due 4821", "Thank you for your business"]):
        d.text((100, 200 + i * 120), line, fill=0, font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    from reportlab.lib.utils import ImageReader
    c = canvas.Canvas(str(path), pagesize=A4)
    c.drawImage(ImageReader(buf), 0, 0, width=A4[0], height=A4[1])
    c.save()
    return path


def encrypted_pdf(src: Path, path: Path, password="s3cret") -> Path:
    from pypdf import PdfReader, PdfWriter

    w = PdfWriter()
    for p in PdfReader(str(src)).pages:
        w.add_page(p)
    w.encrypt(password, algorithm="AES-256")
    with open(path, "wb") as fh:
        w.write(fh)
    return path


def big_pdf(path: Path, pages=150) -> Path:
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate

    ss = getSampleStyleSheet()
    story = []
    for p in range(pages):
        story.append(Paragraph(f"Chapter {p}", ss["Heading1"]))
        story.append(Paragraph(f"BIGPDF-{p} " + "lorem ipsum dolor sit amet consectetur adipiscing elit " * 60, ss["BodyText"]))
        story.append(PageBreak())
    SimpleDocTemplate(str(path)).build(story)
    return path


# ----------------------------------------------------------------------------- DOCX
def rich_docx(path: Path) -> Path:
    from docx import Document
    from docx.shared import Inches

    d = Document()
    d.add_heading("Project Handbook", 1)
    d.add_paragraph("SENTINEL-DOCX-INTRO This handbook explains the project.")
    p = d.add_paragraph()
    p.add_run("Bold part ").bold = True
    p.add_run("italic part").italic = True
    d.add_heading("Details", 2)
    d.add_paragraph("First list item", style="List Bullet")
    d.add_paragraph("Nested list item", style="List Bullet 2")
    t = d.add_table(rows=3, cols=3)
    t.style = "Table Grid"
    for i in range(3):
        for j in range(3):
            t.cell(i, j).text = f"DOCX-R{i}C{j}"
    t.cell(0, 0).merge(t.cell(0, 1))
    d.add_paragraph("Figure below.")
    d.add_picture(io.BytesIO(make_png(400, 240, "DOCX")), width=Inches(3))
    d.add_paragraph("Formula-like text: =SUM(A1:A9)")
    d.save(str(path))
    return path


def big_docx(path: Path, paragraphs=4000, tables=100) -> Path:
    from docx import Document

    d = Document()
    for i in range(paragraphs):
        d.add_paragraph(f"BIGDOC-{i} " + "lorem ipsum dolor sit amet " * 10)
    for t in range(tables):
        tb = d.add_table(rows=10, cols=4)
        for r in range(10):
            for c in range(4):
                tb.cell(r, c).text = f"t{t}r{r}c{c}"
    d.save(str(path))
    return path


# ----------------------------------------------------------------------------- PPTX
def rich_pptx(path: Path) -> Path:
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE
    from pptx.util import Inches

    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = "SENTINEL-PPTX-TITLE Launch Plan"
    s.placeholders[1].text = "Subtitle line"
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "Agenda"
    tf = s.placeholders[1].text_frame
    tf.text = "PPTX-BULLET-ONE"
    tf.add_paragraph().text = "PPTX-BULLET-TWO"
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "Numbers"
    tbl = s.shapes.add_table(3, 3, Inches(1), Inches(2), Inches(6), Inches(1.5)).table
    for i in range(3):
        for j in range(3):
            tbl.cell(i, j).text = f"PPTX-R{i}C{j}"
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "Picture"
    s.shapes.add_picture(io.BytesIO(make_png(400, 300, "PPTX")), Inches(1), Inches(2), Inches(4))
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "Chart"
    cd = CategoryChartData()
    cd.categories = ["Q1", "Q2", "Q3"]
    cd.add_series("Sales", (10, 20, 30))
    s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(2), Inches(6), Inches(4), cd)
    prs.save(str(path))
    return path


# ----------------------------------------------------------------------------- XLSX
def _inject_cached(path: Path, values: dict[str, dict[str, object]]) -> None:
    """Write cached results for formula cells (openpyxl never calculates)."""
    from lxml import etree

    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename in values:
                root = etree.fromstring(data)
                for c in root.iter(f"{{{ns}}}c"):
                    ref = c.get("r")
                    if ref in values[item.filename] and c.find(f"{{{ns}}}f") is not None:
                        v = c.find(f"{{{ns}}}v")
                        if v is None:
                            v = etree.SubElement(c, f"{{{ns}}}v")
                        val = values[item.filename][ref]
                        v.text = str(val)
                        if isinstance(val, str):
                            c.set("t", "str")
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            zout.writestr(item, data)
    os.replace(tmp, path)


def rich_xlsx(path: Path, cached=True) -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws.append(["Item", "Qty", "Price", "Total", "Margin", "Date"])
    rows = [("Widget", 3, 9.5, 28.5, 0.256, date(2026, 1, 15)), ("Gadget", 10, 1234.5, 12345, 0.1, date(2026, 2, 1)),
            ("Gizmo", 7, 3.25, 22.75, 0.5, date(2026, 3, 9))]
    for i, (name, q, pr, tot, mar, dt) in enumerate(rows, 2):
        ws.append([name, q, pr, f"=B{i}*C{i}", mar, dt])
        ws[f"C{i}"].number_format = "$#,##0.00"
        ws[f"E{i}"].number_format = "0.0%"
    ws["A6"] = "=\"=EVIL()\""   # evaluates to text that starts with '='
    notes = wb.create_sheet("Notes")
    notes["A1"] = "SENTINEL-XLSX-NOTE"
    wb.create_sheet("Hidden").sheet_state = "hidden"
    wb["Hidden"]["A1"] = "secret hidden"
    wb.create_sheet("Blank")
    wb.save(str(path))
    if cached:
        _inject_cached(path, {"xl/worksheets/sheet1.xml": {"D2": 28.5, "D3": 12345, "D4": 22.75, "A6": "=EVIL()"}})
    return path


def big_xlsx(path: Path, rows=30000, cols=8) -> Path:
    from openpyxl import Workbook

    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Data")
    ws.append([f"Col{c}" for c in range(cols)])
    for r in range(rows):
        ws.append([f"row{r}" if c == 0 else r * c + 0.5 for c in range(cols)])
    wb.save(str(path))
    return path


# ----------------------------------------------------------------------------- hostile / broken
def zip_bomb_docx(src: Path, path: Path, mb=120) -> Path:
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            zout.writestr(item, zin.read(item.filename))
        with zout.open("word/bomb.bin", "w") as fh:
            chunk = b"\0" * (1 << 20)
            for _ in range(mb):
                fh.write(chunk)
    return path


def xml_entity_bomb_xlsx(src: Path, path: Path) -> Path:
    """Plant a billion-laughs style DTD in workbook.xml (present in every XLSX)."""
    dtd = (b'<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
           b'<!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">]>')
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "xl/workbook.xml":
                head, _, rest = data.partition(b"?>")
                data = head + b"?>" + dtd + rest
            zout.writestr(item, data)
    return path


def build_all(d: Path) -> dict[str, Path]:
    d.mkdir(parents=True, exist_ok=True)
    c: dict[str, Path] = {}
    c["text_pdf"] = text_pdf(d / "text.pdf")
    c["two_col_pdf"] = two_column_pdf(d / "twocol.pdf")
    c["scanned_pdf"] = scanned_pdf(d / "scanned.pdf")
    c["encrypted_pdf"] = encrypted_pdf(c["text_pdf"], d / "encrypted.pdf")
    c["docx"] = rich_docx(d / "rich.docx")
    c["pptx"] = rich_pptx(d / "rich.pptx")
    c["xlsx"] = rich_xlsx(d / "rich.xlsx")
    c["xlsx_uncached"] = rich_xlsx(d / "uncached.xlsx", cached=False)
    for ext in ("pdf", "docx", "pptx", "xlsx"):
        (d / f"empty.{ext}").write_bytes(b"")
        c[f"empty_{ext}"] = d / f"empty.{ext}"
    (d / "garbage.pdf").write_bytes(b"%PDF-1.4\n" + os.urandom(2048))
    c["garbage_pdf"] = d / "garbage.pdf"
    (d / "garbage.docx").write_bytes(os.urandom(4096))
    c["garbage_docx"] = d / "garbage.docx"
    data = c["docx"].read_bytes()
    (d / "truncated.docx").write_bytes(data[: len(data) // 2])
    c["truncated_docx"] = d / "truncated.docx"
    (d / "disguised.xlsx").write_bytes(data)       # a DOCX wearing an .xlsx extension
    c["disguised_xlsx"] = d / "disguised.xlsx"
    (d / "legacy.doc").write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 600)
    c["legacy_doc"] = d / "legacy.doc"
    (d / "ole.docx").write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\0" * 600)
    c["ole_docx"] = d / "ole.docx"
    c["bomb_docx"] = zip_bomb_docx(c["docx"], d / "bomb.docx")
    c["entity_xlsx"] = xml_entity_bomb_xlsx(c["xlsx"], d / "entity.xlsx")
    return c
