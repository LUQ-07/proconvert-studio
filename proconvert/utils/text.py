"""Text helpers shared by readers and writers."""
from __future__ import annotations

import re
import unicodedata

# Characters that are illegal in XML 1.0 (and therefore in DOCX/PPTX/XLSX parts).
_XML_ILLEGAL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff\ud800-\udfff]")
_PLAIN_NUMBER = re.compile(r"^-?(0|[1-9]\d{0,14})(\.\d{1,10})?$")
_US_GROUPED = re.compile(r"^-?[1-9]\d{0,2}(,\d{3})+\.\d{1,10}$")
_WS = re.compile(r"[ \t\u00a0\u2000-\u200a\u202f\u205f\u3000]+")


# Office documents often store bullets and arrows as private-use code points (U+F0xx) of the Symbol / Wingdings fonts.
# Outside those fonts they render as boxes or "?", so the common ones are mapped to real Unicode characters and every
# other private-use code point (icon fonts etc.) is dropped.
_WINGDINGS = {
    0xF0B7: "\u2022", 0xF0A7: "\u25AA", 0xF076: "\u2756", 0xF06C: "\u25CF", 0xF06E: "\u25A0", 0xF071: "\u2751",
    0xF0A8: "\u25FB", 0xF0D8: "\u27A2", 0xF0E0: "\u2192", 0xF0E8: "\u2794", 0xF0FC: "\u2713", 0xF0FB: "\u2717",
    0xF0D7: "\u25C6", 0xF0B2: "\u25A1", 0xF09F: "\u2022",
}
_PUA = re.compile("[\ue000-\uf8ff]")


def map_symbol_glyphs(text: str) -> str:
    """Map Wingdings/Symbol private-use bullets and arrows to Unicode; drop any other private-use character."""
    if not _PUA.search(text):
        return text
    return _PUA.sub(lambda m: _WINGDINGS.get(ord(m.group()), ""), text)


def xml_safe(text: str) -> str:
    """Remove characters that cannot be stored in Office XML parts."""
    return _XML_ILLEGAL.sub("", text)


def clean_inline(text: object) -> str:
    """Collapse whitespace in a single-line value."""
    if text is None:
        return ""
    return _WS.sub(" ", xml_safe(map_symbol_glyphs(str(text))).replace("\r", " ").replace("\n", " ")).strip()


def clean_block(text: object) -> str:
    """Normalize a paragraph: drop control characters and collapse spaces."""
    if text is None:
        return ""
    return _WS.sub(" ", xml_safe(map_symbol_glyphs(str(text))).replace("\r", "")).strip()


def has_rtl(text: str) -> bool:
    return any(unicodedata.bidirectional(ch) in ("R", "AL") for ch in text)


def parse_plain_number(text: str):
    """Return int/float for unambiguous plain numbers, otherwise None.

    Deliberately conservative: identifiers such as ``007`` or ``1,234`` (which is
    ambiguous between locales) stay text so that no data is silently altered.
    """
    s = text.strip()
    if not s or len(s) > 24:
        return None
    if _PLAIN_NUMBER.match(s):
        return float(s) if "." in s else int(s)
    if _US_GROUPED.match(s):
        return float(s.replace(",", ""))
    return None


def truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: max(0, limit - 1)] + "\u2026"
