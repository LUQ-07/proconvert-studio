"""Design tokens (Qt-free so contrast can be unit-tested)."""
from __future__ import annotations

DARK = {
    "bg": "#0E1322", "surface": "#151C30", "surface2": "#1C2540", "border": "#2D3A5C",
    "text": "#EAEFFA", "muted": "#A9B5CF", "accent": "#7C9BFF", "accent_hover": "#99B1FF", "accent_text": "#0A1024",
    "success": "#5ED49A", "warning": "#F4B95A", "danger": "#FF8080", "focus": "#FFD166",
    "badge_text": "#0A1024", "badge_pdf": "#E5534B", "badge_docx": "#4C8DFF", "badge_pptx": "#F08A3C", "badge_xlsx": "#3DB07A", "badge_image": "#B79BFF",
}
LIGHT = {
    "bg": "#F4F6FB", "surface": "#FFFFFF", "surface2": "#EDF1FA", "border": "#C9D3E6",
    "text": "#121C36", "muted": "#47557A", "accent": "#2F4FD8", "accent_hover": "#223FC0", "accent_text": "#FFFFFF",
    "success": "#17704A", "warning": "#7A4F00", "danger": "#B0201A", "focus": "#B35C00",
    "badge_text": "#FFFFFF", "badge_pdf": "#B3261E", "badge_docx": "#1F55C4", "badge_pptx": "#A24B00", "badge_xlsx": "#156B43", "badge_image": "#6A2FB0",
}


def _lin(c: int) -> float:
    v = c / 255
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast_ratio(a: str, b: str) -> float:
    """WCAG 2.x contrast ratio between two #RRGGBB colours."""
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)
