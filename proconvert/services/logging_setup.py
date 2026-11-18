"""Rotating file logging with automatic redaction of personal data."""
from __future__ import annotations

import logging
import re
import sys
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from ..utils.paths import crash_dir, log_dir

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


class RedactingFilter(logging.Filter):
    """Replace the user's home directory and e-mail addresses in every log record."""

    def __init__(self) -> None:
        super().__init__()
        home = str(Path.home())
        self._home = home if len(home) > 3 else ""

    def redact(self, text: str) -> str:
        if self._home:
            text = text.replace(self._home, "~").replace(self._home.replace("\\", "/"), "~")
        return _EMAIL.sub("<email>", text)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.redact(record.getMessage())
        record.args = ()
        return True


def setup_logging(level: str = "INFO", directory: Path | None = None) -> Path:
    directory = directory or log_dir()
    directory.mkdir(parents=True, exist_ok=True)
    logfile = directory / "proconvert.log"
    root = logging.getLogger("proconvert")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()
    handler = RotatingFileHandler(logfile, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter())
    root.addHandler(handler)
    root.propagate = False
    return logfile


def install_crash_handler(enabled: bool) -> None:
    """Log uncaught exceptions; additionally write a redacted local report when enabled. Never uploads."""
    redactor = RedactingFilter()
    log = logging.getLogger("proconvert.crash")

    def hook(exc_type, exc, tb):
        text = redactor.redact("".join(traceback.format_exception(exc_type, exc, tb)))
        log.critical("Unhandled exception:\n%s", text)
        if enabled:
            try:
                crash_dir().mkdir(parents=True, exist_ok=True)
                (crash_dir() / f"crash-{datetime.now():%Y%m%d-%H%M%S}.txt").write_text(text, encoding="utf-8")
            except OSError:
                pass

    sys.excepthook = hook
