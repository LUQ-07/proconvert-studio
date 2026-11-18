"""User-facing error taxonomy.

Every failure the user can see is a :class:`ConversionError` carrying a plain-English
message and troubleshooting advice. Technical detail (exception type and text, never a
raw stack trace) is kept separately for the log file and the diagnostics export.
"""
from __future__ import annotations

import errno
from typing import Any


class ConversionError(Exception):
    code = "conversion_failed"
    default_message = "The conversion could not be completed."
    troubleshooting = (
        "Try the conversion again. If it keeps failing, open Settings > Advanced, export a "
        "diagnostics report and attach it to a bug report on the project page (Help > Report a problem)."
    )

    def __init__(self, message: str | None = None, *, technical: str | None = None,
                 troubleshooting: str | None = None) -> None:
        super().__init__(message or self.default_message)
        self.user_message = message or self.default_message
        self.technical = technical
        if troubleshooting:
            self.troubleshooting = troubleshooting

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.user_message,
                "troubleshooting": self.troubleshooting, "technical": self.technical}


class UnsupportedFormatError(ConversionError):
    code = "unsupported_format"
    default_message = "This file type or conversion is not supported."
    troubleshooting = "Choose a PDF, DOCX, PPTX or XLSX file. Legacy .doc, .ppt and .xls files must be re-saved in the newer format first."


class InvalidFileError(ConversionError):
    code = "invalid_file"
    default_message = "The file is damaged or is not what its extension says."
    troubleshooting = (
        "Open the file in its original application and save a fresh copy, then try again. "
        "If the file came from an email or download, download it again."
    )


class PasswordProtectedError(ConversionError):
    code = "password_protected"
    default_message = "The file is protected with a password."
    troubleshooting = "For a PDF, enter the password when asked. For Office files, remove the password in Word, PowerPoint or Excel and save a copy."


class FileTooLargeError(ConversionError):
    code = "file_too_large"
    default_message = "The file is larger than the safe processing limit."
    troubleshooting = "Split the document into smaller parts, or select a page range, and try again."


class UnsafeFileError(ConversionError):
    code = "unsafe_file"
    default_message = "The file was rejected because it looks unsafe to process."
    troubleshooting = "Only convert files from sources you trust. If you are sure the file is legitimate, re-save it from its original application."


class EmptyContentError(ConversionError):
    code = "empty_content"
    default_message = "No convertible content was found in the file."
    troubleshooting = (
        "The document may be empty, or a scanned PDF containing only images. For scanned PDFs, "
        "enable OCR in Settings > Conversion (requires an installed OCR engine)."
    )


class OutputPathError(ConversionError):
    code = "output_path"
    default_message = "The output location is not valid."
    troubleshooting = "Choose an existing folder and a file name without special characters."


class OutputExistsError(ConversionError):
    code = "output_exists"
    default_message = "A file with that name already exists."
    troubleshooting = "Choose a different name, or confirm that the existing file may be replaced."


class PermissionDeniedError(ConversionError):
    code = "permission_denied"
    default_message = "The application does not have permission to read the file or write to the folder."
    troubleshooting = "Choose a folder you can write to (for example Documents), and make sure the file is not locked by another program."


class DiskFullError(ConversionError):
    code = "disk_full"
    default_message = "There is not enough free disk space to finish the conversion."
    troubleshooting = "Free up disk space or choose another drive, then try again."


class ResourceLimitError(ConversionError):
    code = "resource_limit"
    default_message = "The document needs more memory or time than is allowed."
    troubleshooting = "Close other applications, or convert a smaller part of the document."


class DependencyMissingError(ConversionError):
    code = "dependency_missing"
    default_message = "A required component of the application is missing."
    troubleshooting = "Reinstall ProConvert Studio. If the problem remains, report it on the project page (Help > Report a problem)."


class InvalidOptionsError(ConversionError):
    code = "invalid_options"
    default_message = "One of the conversion options is not valid."
    troubleshooting = "Check the page range (for example 1-3,7) and the other options, then try again."


class CancelledError(ConversionError):
    code = "cancelled"
    default_message = "The conversion was cancelled."
    troubleshooting = "No output file was created."


class ConversionTimeoutError(ConversionError):
    code = "timeout"
    default_message = "The conversion took too long and was stopped."
    troubleshooting = "Try a smaller document or select a page range."


class EngineCrashError(ConversionError):
    code = "engine_crash"
    default_message = "The converter stopped unexpectedly."
    troubleshooting = "The file may be malformed. Try re-saving it from its original application, then convert again."


_CODES: dict[str, type[ConversionError]] = {
    c.code: c for c in ConversionError.__subclasses__()
}
_CODES[ConversionError.code] = ConversionError


def error_from_dict(data: dict[str, Any]) -> ConversionError:
    cls = _CODES.get(data.get("code", ""), ConversionError)
    return cls(data.get("message"), technical=data.get("technical"),
               troubleshooting=data.get("troubleshooting"))


def wrap_unexpected(exc: BaseException) -> ConversionError:
    """Map an arbitrary exception to a friendly ConversionError (idempotent)."""
    if isinstance(exc, ConversionError):
        return exc
    tech = f"{type(exc).__name__}: {exc}"
    if isinstance(exc, MemoryError):
        return ResourceLimitError(technical=tech)
    if isinstance(exc, OSError):
        if exc.errno == errno.ENOSPC:
            return DiskFullError(technical=tech)
        if exc.errno in (errno.EACCES, errno.EPERM, errno.EROFS):
            return PermissionDeniedError(technical=tech)
        if exc.errno in (errno.ENAMETOOLONG, errno.ENOENT, errno.ENOTDIR, errno.EINVAL):
            return OutputPathError(technical=tech)
    if isinstance(exc, ImportError):
        return DependencyMissingError(technical=tech)
    return ConversionError(technical=tech)
