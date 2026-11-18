"""Format-neutral intermediate representation (IR).

Every reader produces a :class:`DocumentIR`; every writer consumes one. Keeping the
IR small and explicit is what lets all 12 routes share one tested pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Union

from ..utils.text import map_symbol_glyphs

SectionKind = Literal["page", "slide", "sheet", "flow"]


@dataclass(frozen=True)
class Run:
    text: str
    bold: bool = False
    italic: bool = False

    def __post_init__(self) -> None:
        # Wingdings/Symbol bullets and arrows stored as private-use code points become real Unicode in every reader
        mapped = map_symbol_glyphs(self.text)
        if mapped is not self.text:
            object.__setattr__(self, "text", mapped)


@dataclass
class Paragraph:
    runs: list[Run]
    heading: int = 0          # 0 = body text, 1..3 = heading level
    bullet: bool = False
    level: int = 0            # list nesting level, 0..2
    number: int | None = None  # ordered list: the item's number (1-based); None for bullets/body text

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)

    @staticmethod
    def plain(text: str, **kw) -> "Paragraph":
        return Paragraph([Run(text)], **kw)


@dataclass
class Table:
    rows: list[list[str]]
    header: bool = True       # first row is a header row (styling hint only)

    @property
    def n_cols(self) -> int:
        return max((len(r) for r in self.rows), default=0)


@dataclass
class Picture:
    data: bytes               # PNG or JPEG bytes
    fmt: str                  # "png" | "jpeg"
    width_px: int
    height_px: int
    display_w_pt: float | None = None   # intended size on the source page, if known
    display_h_pt: float | None = None


Block = Union[Paragraph, Table, Picture]


@dataclass
class Section:
    kind: SectionKind
    label: str
    blocks: list[Block] = field(default_factory=list)


@dataclass
class DocumentIR:
    title: str
    sections: list[Section] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_format: str = ""
    header: str = ""          # running page header/footer text (DOCX); writers that can draw it do so
    footer: str = ""

    def iter_blocks(self):
        for s in self.sections:
            yield from s.blocks


@dataclass(frozen=True)
class IRStats:
    sections: int
    paragraphs: int
    tables: int
    table_rows: int
    pictures: int
    characters: int

    def has_content(self) -> bool:
        return self.characters > 0 or self.tables > 0 or self.pictures > 0

    def summary(self) -> str:
        parts = [f"{self.sections} section(s)", f"{self.paragraphs} paragraph(s)",
                 f"{self.tables} table(s)", f"{self.pictures} image(s)"]
        return ", ".join(parts)


def ir_stats(ir: DocumentIR) -> IRStats:
    paragraphs = tables = rows = pictures = chars = 0
    for b in ir.iter_blocks():
        if isinstance(b, Paragraph):
            t = b.text.strip()
            if t:
                paragraphs += 1
                chars += len(t)
        elif isinstance(b, Table):
            if any(c.strip() for r in b.rows for c in r):
                tables += 1
                rows += len(b.rows)
                chars += sum(len(c.strip()) for r in b.rows for c in r)
        elif isinstance(b, Picture):
            pictures += 1
    return IRStats(len(ir.sections), paragraphs, tables, rows, pictures, chars)
