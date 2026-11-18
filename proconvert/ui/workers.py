"""Qt wrappers that run the Qt-free job/queue classes off the UI thread."""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from ..converters.image_tools import ImageLayout, convert_images
from ..core.context import CancelToken
from ..core.errors import wrap_unexpected
from ..workers.batch import BatchItem
from ..workers.process_job import ConversionJob


class ConversionThread(QThread):
    """Runs one :class:`ConversionJob` (itself a separate OS process) without blocking the UI."""

    progress = Signal(object)      # ProgressEvent
    succeeded = Signal(object)     # ConversionResult
    failed = Signal(object)        # ConversionError

    def __init__(self, job: ConversionJob, parent=None) -> None:
        super().__init__(parent)
        self.job = job

    def cancel(self) -> None:
        self.job.cancel()

    def run(self) -> None:  # noqa: D401 - Qt entry point
        try:
            result = self.job.run(self.progress.emit)
        except BaseException as exc:  # noqa: BLE001 - must never crash the thread silently
            self.failed.emit(wrap_unexpected(exc))
        else:
            self.succeeded.emit(result)


class BatchBridge(QObject):
    """Marshals BatchQueue callbacks (worker threads) onto the Qt event loop via a queued signal."""

    item_changed = Signal(object)

    def callback(self, item: BatchItem) -> None:
        self.item_changed.emit(item)


class FunctionThread(QThread):
    """Run any short blocking callable and report its result."""

    done = Signal(object, object)   # (result, exception)

    def __init__(self, fn, parent=None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            self.done.emit(self._fn(), None)
        except Exception as exc:  # noqa: BLE001
            self.done.emit(None, exc)


class ImageConversionThread(QThread):
    """Runs the Qt-free image engine (images -> PDF/DOCX) off the UI thread; cancellable, never raises into Qt."""

    progress = Signal(float, str)
    succeeded = Signal(object)     # ImageResult
    failed = Signal(object)        # ConversionError

    def __init__(self, images: list[str], out: str, fmt: str, layout: ImageLayout, overwrite: bool, parent=None,
                 language: str = "eng") -> None:
        super().__init__(parent)
        self._args = (list(images), out, fmt, layout)
        self._language = language
        self._overwrite = overwrite
        self._token = CancelToken()

    def cancel(self) -> None:
        self._token.cancel()

    def run(self) -> None:  # noqa: D401 - Qt entry point
        images, out, fmt, layout = self._args
        try:
            result = convert_images(images, out, fmt, layout, overwrite=self._overwrite, cancel=self._token, progress=self.progress.emit,
                                    language=self._language)
        except BaseException as exc:  # noqa: BLE001
            self.failed.emit(wrap_unexpected(exc))
        else:
            self.succeeded.emit(result)
