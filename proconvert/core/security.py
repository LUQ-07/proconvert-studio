"""Input and output validation.

Checks performed before any parser touches a file:
  * extension is one of the four supported formats,
  * file is non-empty, readable and below the size limit,
  * the *content* matches the extension (PDF header / OOXML package markers),
  * Office packages pass ZIP-bomb limits (entry count, total size, compression ratio),
  * output path is a safe, writable, non-colliding location.

Security model limits are documented in docs/SECURITY_MODEL.md.
"""
from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass
from pathlib import Path

from ..utils.files import is_safe_filename
from .errors import (
    EmptyContentError,
    FileTooLargeError,
    InvalidFileError,
    OutputExistsError,
    OutputPathError,
    PasswordProtectedError,
    PermissionDeniedError,
    UnsafeFileError,
    UnsupportedFormatError,
)
from .options import Limits

SUPPORTED_FORMATS = ("pdf", "docx", "pptx", "xlsx")
FORMAT_LABELS = {"pdf": "PDF", "docx": "Word (DOCX)", "pptx": "PowerPoint (PPTX)", "xlsx": "Excel (XLSX)"}
_OOXML_MARKERS = {"docx": "word/document.xml", "pptx": "ppt/presentation.xml", "xlsx": "xl/workbook.xml"}
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_LEGACY = {"doc": "Word 97-2003 (.doc)", "ppt": "PowerPoint 97-2003 (.ppt)", "xls": "Excel 97-2003 (.xls)"}


@dataclass(frozen=True)
class SourceInfo:
    path: Path
    fmt: str
    size: int
    has_macros: bool = False


def extension_format(path: Path) -> str:
    return path.suffix.lower().lstrip(".")


def check_zip_safety(zf: zipfile.ZipFile, limits: Limits) -> None:
    infos = zf.infolist()
    if len(infos) > limits.max_zip_entries:
        raise UnsafeFileError(f"The document package contains an unusual number of parts ({len(infos):,}).")
    total = 0
    for info in infos:
        total += info.file_size
        if total > limits.max_zip_uncompressed_bytes:
            raise UnsafeFileError("The document would expand to an unsafe size when opened (possible ZIP bomb).")
        if info.file_size > limits.ratio_check_min_bytes:
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > limits.max_zip_entry_ratio:
                raise UnsafeFileError("The document contains an extremely compressed part (possible ZIP bomb).")


def reject_xml_dtds(zf: zipfile.ZipFile) -> None:
    """Office XML never needs a DTD. Rejecting DOCTYPE/ENTITY declarations up front defeats
    entity-expansion ("billion laughs") and external-entity tricks regardless of parser behaviour."""
    for info in zf.infolist():
        name = info.filename.lower()
        if not name.endswith((".xml", ".rels", ".vml")) or info.file_size == 0:
            continue
        with zf.open(info) as fh:
            head = fh.read(8192).lower()
        if b"<!doctype" in head or b"<!entity" in head:
            raise UnsafeFileError("The document contains a disallowed XML declaration (possible entity-expansion attack).")


def _sniff_ooxml(path: Path, limits: Limits) -> tuple[str, bool]:
    try:
        with zipfile.ZipFile(path) as zf:
            check_zip_safety(zf, limits)
            reject_xml_dtds(zf)
            names = {n.lower() for n in zf.namelist()}
            has_macros = any(n.endswith("vbaproject.bin") for n in names)
            if "[content_types].xml" not in names:
                raise InvalidFileError("The file is not a valid Office document (missing package manifest).")
            for fmt, marker in _OOXML_MARKERS.items():
                if marker in names:
                    return fmt, has_macros
    except zipfile.BadZipFile as exc:
        raise InvalidFileError("The file is damaged (the Office package cannot be read).", technical=str(exc)) from exc
    raise InvalidFileError("The file does not contain a Word, PowerPoint or Excel document.")


def validate_source(path: str | Path, limits: Limits | None = None) -> SourceInfo:
    limits = limits or Limits()
    p = Path(path).expanduser()
    try:
        p = p.resolve()
    except OSError as exc:
        raise InvalidFileError("The file path is not valid.", technical=str(exc)) from exc
    if not p.exists():
        raise InvalidFileError("The file could not be found. It may have been moved or deleted.")
    if not p.is_file():
        raise InvalidFileError("The selected item is not a file.")
    ext = extension_format(p)
    if ext in _LEGACY:
        raise UnsupportedFormatError(f"{_LEGACY[ext]} files are not supported. Open the file in its application and save it as the modern format.")
    if ext not in SUPPORTED_FORMATS:
        raise UnsupportedFormatError(f"Files of type .{ext or '(none)'} are not supported.")
    try:
        size = p.stat().st_size
        with p.open("rb") as fh:
            head = fh.read(1100)
    except PermissionError as exc:
        raise PermissionDeniedError(technical=str(exc)) from exc
    except OSError as exc:
        raise InvalidFileError("The file cannot be read.", technical=str(exc)) from exc
    if size == 0:
        raise EmptyContentError("The file is empty (0 bytes).")
    if size > limits.max_input_bytes:
        raise FileTooLargeError(f"The file is {size / 1048576:.0f} MB, which is above the {limits.max_input_bytes // 1048576} MB safety limit.")

    if ext == "pdf":
        if b"%PDF-" not in head:
            if head.startswith(_OLE_MAGIC) or head.startswith(b"PK"):
                raise InvalidFileError("The file has a .pdf extension but is not a PDF document.")
            raise InvalidFileError("The file is not a valid PDF (no PDF header found).")
        return SourceInfo(p, "pdf", size)

    if head.startswith(_OLE_MAGIC):
        raise PasswordProtectedError(
            "This Office file is encrypted with a password, or is an old binary-format document saved with a modern extension."
        )
    if not (head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06")):
        raise InvalidFileError(f"The file is not a valid .{ext} document.")
    actual, macros = _sniff_ooxml(p, limits)
    if actual != ext:
        raise InvalidFileError(
            f"The extension says .{ext} but the content is a {FORMAT_LABELS[actual]} document. Rename the file correctly and try again."
        )
    return SourceInfo(p, ext, size, macros)


def validate_target(target: str | Path, source: Path | None, fmt_out: str, *, overwrite: bool) -> Path:
    t = Path(target).expanduser()
    ok, why = is_safe_filename(t.name)
    if not ok:
        raise OutputPathError(why)
    if extension_format(t) != fmt_out:
        raise OutputPathError(f"The output file name must end with .{fmt_out}.")
    try:
        parent = t.parent.resolve()
    except OSError as exc:
        raise OutputPathError("The output folder path is not valid.", technical=str(exc)) from exc
    if not parent.is_dir():
        raise OutputPathError("The output folder does not exist.")
    if not os.access(parent, os.W_OK | os.X_OK):
        raise PermissionDeniedError("You do not have permission to save files in the output folder.")
    final = parent / t.name
    if source is not None:
        try:
            same = final == source or (final.exists() and os.path.samefile(final, source))
        except OSError:
            same = False
        if same:
            raise OutputPathError("The output file must be different from the source file.")
    if final.is_symlink():
        raise OutputPathError("The output path is a symbolic link; choose a regular file name.")
    if final.exists():
        if final.is_dir():
            raise OutputPathError("A folder with that name already exists.")
        if not overwrite:
            raise OutputExistsError(f"'{final.name}' already exists.")
    return final
