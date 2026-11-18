"""Progress reporting, cancellation and the per-job context object."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

from .errors import CancelledError
from .options import ConversionOptions, Limits

# Stage ids (stable identifiers; the UI maps them to translated text)
VALIDATING = "validating"
READING = "reading"
WRITING = "writing"
VERIFYING = "verifying"
FINALIZING = "finalizing"
DONE = "done"

# Share of the overall bar each stage occupies. Reading and writing report real
# per-page / per-section counts inside their share; stages that cannot be measured
# report ``None`` which the UI renders as an indeterminate indicator.
STAGE_RANGES = {
    VALIDATING: (0.00, 0.03),
    READING: (0.03, 0.50),
    WRITING: (0.50, 0.90),
    VERIFYING: (0.90, 0.96),
    FINALIZING: (0.96, 1.00),
    DONE: (1.00, 1.00),
}


@dataclass(frozen=True)
class ProgressEvent:
    stage: str
    fraction: Optional[float]   # overall 0..1, or None when not measurable
    detail: str = ""


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise CancelledError()


@dataclass
class JobContext:
    options: ConversionOptions
    limits: Limits
    cancel: CancelToken = field(default_factory=CancelToken)
    emit: Callable[[ProgressEvent], None] = lambda event: None
    warnings: list[str] = field(default_factory=list)
    image_bytes: int = 0

    def report(self, stage: str, local_fraction: Optional[float], detail: str = "") -> None:
        lo, hi = STAGE_RANGES[stage]
        overall = None if local_fraction is None else lo + (hi - lo) * max(0.0, min(1.0, local_fraction))
        self.emit(ProgressEvent(stage, overall, detail))

    def warn(self, message: str) -> None:
        if message not in self.warnings and len(self.warnings) < 200:
            self.warnings.append(message)
