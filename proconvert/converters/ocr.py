"""Optional OCR adapter.

OCR is never required. It is used only when the user enables it *and* a Tesseract
executable can be found (bundled next to the app, or on PATH). Tesseract and
pytesseract are Apache-2.0 licensed. No text is sent anywhere: Tesseract runs locally.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from ..utils.paths import resource_path

_LANG = re.compile(r"^[A-Za-z_]{2,12}(\+[A-Za-z_]{2,12}){0,3}$")


def tesseract_path() -> str | None:
    bundled = resource_path("bin/tesseract")
    for candidate in (bundled, Path(str(bundled) + ".exe")):
        if candidate.is_file():
            return str(candidate)
    return shutil.which("tesseract")


def is_available() -> bool:
    if tesseract_path() is None:
        return False
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        return False
    return True


def valid_language(lang: str) -> bool:
    return bool(_LANG.match(lang or ""))


def recognize(image, language: str = "eng", timeout: int = 120) -> str:
    """Run Tesseract on a PIL image and return plain text."""
    import pytesseract

    if not valid_language(language):
        language = "eng"
    pytesseract.pytesseract.tesseract_cmd = tesseract_path() or "tesseract"
    return pytesseract.image_to_string(image, lang=language, timeout=timeout)
