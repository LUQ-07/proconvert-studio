"""Conversion capability matrix: the single source of truth for routes, fidelity and limits.

The UI reads this to label routes ("Experimental"), and ``tools/gen_matrix.py`` renders
``docs/COMPATIBILITY_MATRIX.md`` from it. Fidelity tiers are deliberately conservative:

* ``supported``     - the source content classes (text, tables, images) map naturally onto
                      the target and are verified by automated tests. Layout is still *not*
                      reproduced pixel-for-pixel.
* ``experimental``  - the route reconstructs structure the source does not contain
                      (PDF -> anything, anything -> automatic slides, prose -> spreadsheet).
                      Results need human review.
"""
from __future__ import annotations

from dataclasses import dataclass

from .. import config

SUPPORTED = "supported"
EXPERIMENTAL = "experimental"

CATEGORY_ORDER = ("pdf", "docx", "pptx", "xlsx")
CATEGORY_TITLES = {
    "pdf": "PDF Converter", "docx": "Word Converter",
    "pptx": "PowerPoint Converter", "xlsx": "Excel Converter",
}

_READ_ENGINE = {
    "pdf": "pdfplumber + pdfminer.six + pypdf (text, ruled tables, images)",
    "docx": "python-docx (paragraphs, runs, tables, inline images)",
    "pptx": "python-pptx (titles, text, tables, pictures, chart data)",
    "xlsx": "openpyxl read-only (cell values, number formats)",
}
_WRITE_ENGINE = {
    "pdf": "ReportLab (BSD) with bundled DejaVu fonts",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "xlsx": "openpyxl",
}

_SOURCE_LIMITS = {
    "pdf": (
        "Text is re-flowed; original page layout, fonts and exact positioning are not reproduced.",
        "Only tables drawn with ruled lines are detected; space-aligned tables come through as text.",
        "Scanned (image-only) pages are inserted as images unless OCR is enabled and an OCR engine is installed.",
        "Vector graphics and charts are not converted; only embedded raster images are.",
        "Annotations, form fields, links and bookmarks are not converted.",
        "Headings come from font size, lists from bullet/number markers and indentation; running headers, footers and page numbers are moved out of the text.",
    ),
    "docx": (
        "Text boxes, comments and equations are not converted; nested tables are omitted (reported).",
        "Header/footer text is kept as running text (Word/PDF output only); footnotes and endnotes become a numbered Notes list at the end.",
        "Tracked changes are accepted; numbered lists keep their numbers (restored from the numbering definitions).",
        "Page layout, fonts and styles are not reproduced.",
    ),
    "pptx": (
        "Slide geometry, shapes, SmartArt, animations, transitions and speaker notes are not converted.",
        "Charts become data tables (the chart image is not reproduced).",
    ),
    "xlsx": (
        "Formulas are not converted; the last stored result is used, so the workbook must have been saved by a spreadsheet application.",
        "Charts, pivot tables, conditional formatting, merged-cell layout and column widths are not converted.",
        "Only common number formats (decimals, thousands, percent, currency, dates) are applied.",
        "Empty rows and columns are removed; hidden sheets are skipped.",
    ),
}
_TARGET_LIMITS = {
    "pdf": ("Built-in fonts cover Latin, Greek and Cyrillic; CJK characters are replaced and right-to-left text (Arabic, Hebrew) is not shaped correctly.",),
    "docx": ("Output uses the default Word template styling.",),
    "pptx": ("Slides are generated automatically with a plain, undecorated layout.",),
    "xlsx": ("Prose is placed one paragraph per row; tables become cell ranges.",),
}
_ROUTE_EXTRA = {
    ("docx", "xlsx"): ("Tables are written to their own sheets; text is written to a 'Document' sheet.",),
    ("pptx", "xlsx"): ("Each slide becomes a sheet.",),
    ("xlsx", "pptx"): (f"Tables are paginated across slides; output is capped at 600 table rows.",),
    ("xlsx", "pdf"): ("Very wide sheets switch the document to landscape and use small type.",),
    ("pdf", "xlsx"): ("Each PDF page becomes a sheet; tables that continue across pages are not joined.",),
}

_SUPPORTED_ROUTES = {
    # ("pdf", "docx") was promoted after the real-document evaluation in docs/FIDELITY_REPORT.md (text PDFs only; see limits)
    ("pdf", "docx"), ("docx", "pdf"), ("pptx", "pdf"), ("pptx", "docx"), ("xlsx", "pdf"), ("xlsx", "docx"),
}

_LICENSE_NOTES = {
    "pdf_read": "pdfplumber (MIT), pdfminer.six (MIT), pypdf (BSD-3-Clause), pypdfium2 (Apache-2.0/BSD-3-Clause; OCR rendering only)",
    "docx": "python-docx (MIT)",
    "pptx": "python-pptx (MIT)",
    "xlsx": "openpyxl (MIT)",
    "pdf_write": "ReportLab open-source edition (BSD-3-Clause); DejaVu fonts (Bitstream Vera license, redistribution allowed)",
}


@dataclass(frozen=True)
class Route:
    source: str
    target: str
    status: str
    engine: str
    fidelity: str
    limitations: tuple[str, ...]
    licensing: str

    @property
    def key(self) -> str:
        return f"{self.source}->{self.target}"

    @property
    def experimental(self) -> bool:
        return self.status == EXPERIMENTAL


def _licensing(src: str, dst: str) -> str:
    read = _LICENSE_NOTES["pdf_read"] if src == "pdf" else _LICENSE_NOTES[src]
    write = _LICENSE_NOTES["pdf_write"] if dst == "pdf" else _LICENSE_NOTES[dst]
    return f"Read: {read}. Write: {write}."


def _build() -> dict[tuple[str, str], Route]:
    routes: dict[tuple[str, str], Route] = {}
    for src in CATEGORY_ORDER:
        for dst in CATEGORY_ORDER:
            if src == dst or (src, dst) in config.DISABLED_ROUTES:
                continue
            status = SUPPORTED if (src, dst) in _SUPPORTED_ROUTES else EXPERIMENTAL
            fidelity = ("Content-level: text, tables and images carried over; layout is not identical"
                        if status == SUPPORTED else
                        "Experimental: structure is reconstructed heuristically; review the result")
            lims = _SOURCE_LIMITS[src] + _TARGET_LIMITS[dst] + _ROUTE_EXTRA.get((src, dst), ())
            routes[(src, dst)] = Route(
                src, dst, status, f"{_READ_ENGINE[src]} -> neutral model -> {_WRITE_ENGINE[dst]}",
                fidelity, lims, _licensing(src, dst),
            )
    return routes


ROUTES: dict[tuple[str, str], Route] = _build()


def route_for(source: str, target: str) -> Route | None:
    return ROUTES.get((source, target))


def targets_for(source: str) -> list[str]:
    return [d for d in CATEGORY_ORDER if (source, d) in ROUTES]


def all_routes() -> list[Route]:
    return [ROUTES[(s, d)] for s in CATEGORY_ORDER for d in CATEGORY_ORDER if (s, d) in ROUTES]


def compatibility_grid() -> list[list[str | None]]:
    """The Help-page matrix, derived from ROUTES (never typed by hand).

    Rows follow CATEGORY_ORDER (the source), columns follow CATEGORY_ORDER (the target).
    A cell is ``None`` for source == target, otherwise ``"supported"`` or ``"experimental"``.
    """
    grid: list[list[str | None]] = []
    for src in CATEGORY_ORDER:
        row: list[str | None] = []
        for dst in CATEGORY_ORDER:
            if src == dst:
                row.append(None)
            else:
                route = ROUTES.get((src, dst))
                row.append(None if route is None else (EXPERIMENTAL if route.experimental else SUPPORTED))
        grid.append(row)
    return grid


IMAGE_OUTPUTS = {"pdf": SUPPORTED, "docx": SUPPORTED, "pptx": SUPPORTED, "xlsx": EXPERIMENTAL}   # converters/image_tools.py, image_table.py


def image_row() -> list[str | None]:
    """Help-table row for images, in CATEGORY_ORDER columns. PDF, Word and PowerPoint are supported; Excel (a table read from
    the picture with OCR) is experimental because the text recognition can make mistakes and needs Tesseract."""
    return [IMAGE_OUTPUTS.get(target) for target in CATEGORY_ORDER]
