"""Conversion options and safety limits (both plain, picklable dataclasses)."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

MB = 1024 * 1024

QUALITY_PRESETS: dict[str, tuple[int | None, int]] = {
    # name: (max image edge in px or None for original, JPEG quality)
    "standard": (1600, 75),
    "high": (3000, 85),
    "original": (None, 92),
}


@dataclass(frozen=True)
class Limits:
    """Resource ceilings that protect the user's machine from oversized or hostile files."""
    max_input_bytes: int = 250 * MB
    max_zip_entries: int = 20_000
    max_zip_uncompressed_bytes: int = 1024 * MB
    max_zip_entry_ratio: int = 300          # per-entry compression ratio above which large entries are rejected
    ratio_check_min_bytes: int = 20 * MB    # ratio rule only applies to entries bigger than this
    max_pdf_pages: int = 3000
    max_sheet_rows: int = 100_000
    max_total_cells: int = 3_000_000
    max_image_pixels: int = 120_000_000
    max_total_image_bytes: int = 400 * MB
    max_images_per_page: int = 60
    max_docx_table_rows: int = 5_000
    max_pdf_table_rows: int = 50_000
    max_pptx_table_rows: int = 600
    max_pptx_slides: int = 500
    max_cell_chars_pdf: int = 2_000
    max_cell_chars_pptx: int = 300
    timeout_seconds: int = 900
    memory_limit_mb: int = 0                # 0 = no limit (POSIX only when set)


@dataclass
class ConversionOptions:
    quality: str = "high"
    pdf_pages: str = ""                     # e.g. "1-3,7"; empty = all pages
    pdf_password: str | None = field(default=None, repr=False)
    ocr_enabled: bool = False
    ocr_language: str = "eng"
    detect_columns: bool = True
    strip_headers_footers: bool = True
    include_images: bool = True
    page_size: str = "A4"                   # output PDF page size: "A4" | "Letter"

    @property
    def image_max_px(self) -> int | None:
        return QUALITY_PRESETS.get(self.quality, QUALITY_PRESETS["high"])[0]

    @property
    def jpeg_quality(self) -> int:
        return QUALITY_PRESETS.get(self.quality, QUALITY_PRESETS["high"])[1]

    def to_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        return d

    def with_(self, **kw) -> "ConversionOptions":
        return replace(self, **kw)

    def redacted(self) -> dict[str, Any]:
        d = self.to_dict()
        if d.get("pdf_password"):
            d["pdf_password"] = "***"
        return d
