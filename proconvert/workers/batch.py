"""Thread-based batch queue. Each item runs as an isolated :class:`ConversionJob` process.

Qt-free so it is fully unit-testable; the UI wraps ``on_update`` with a Qt signal.
"""
from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from ..core.context import ProgressEvent
from ..core.errors import CancelledError, ConversionError, wrap_unexpected
from ..core.options import ConversionOptions, Limits
from ..core.pipeline import ConversionResult
from ..utils.files import unique_path
from .process_job import ConversionJob


class ItemStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


FINISHED = {ItemStatus.DONE, ItemStatus.FAILED, ItemStatus.CANCELLED, ItemStatus.SKIPPED}


@dataclass
class BatchItem:
    id: int
    source: Path
    target: Path
    options: ConversionOptions
    overwrite: bool = False
    status: ItemStatus = ItemStatus.PENDING
    message: str = ""
    progress: Optional[float] = None
    result: Optional[ConversionResult] = None
    error: Optional[dict] = None
    duration_s: float = 0.0
    _job: Optional[ConversionJob] = field(default=None, repr=False, compare=False)


def plan_target(source: Path, out_dir: Path | None, dst_fmt: str, overwrite: bool) -> Path:
    """Pick the output path for a batch item. Existing files are never replaced unless ``overwrite``."""
    folder = out_dir or source.parent
    candidate = folder / f"{source.stem}.{dst_fmt}"
    return candidate if overwrite else unique_path(candidate)


class BatchQueue:
    def __init__(self, max_workers: int = 2, on_update: Optional[Callable[[BatchItem], None]] = None,
                 temp_root: str | Path | None = None, limits: Optional[Limits] = None,
                 job_factory: Optional[Callable[[BatchItem], ConversionJob]] = None) -> None:
        self.max_workers = max(1, max_workers)
        self.on_update = on_update or (lambda item: None)
        self.temp_root, self.limits = temp_root, limits
        self._factory = job_factory or self._default_job
        self._items: list[BatchItem] = []
        self._ids = itertools.count(1)
        self._lock = threading.RLock()
        self._threads: list[threading.Thread] = []
        self._stop_all = False

    def _default_job(self, item: BatchItem) -> ConversionJob:
        return ConversionJob(item.source, item.target, item.options, limits=self.limits,
                             overwrite=item.overwrite, temp_root=self.temp_root)

    # ---------------------------------------------------------------- queue editing
    def add(self, source: Path, target: Path, options: ConversionOptions, *, overwrite: bool = False,
            skip_reason: str = "") -> BatchItem:
        item = BatchItem(next(self._ids), Path(source), Path(target), options, overwrite)
        if skip_reason:
            item.status, item.message = ItemStatus.SKIPPED, skip_reason
        with self._lock:
            self._items.append(item)
        self.on_update(item)
        return item

    def remove(self, item_id: int) -> bool:
        with self._lock:
            for it in self._items:
                if it.id == item_id and it.status != ItemStatus.RUNNING:
                    self._items.remove(it)
                    return True
        return False

    def clear(self) -> None:
        with self._lock:
            self._items = [i for i in self._items if i.status == ItemStatus.RUNNING]

    @property
    def items(self) -> list[BatchItem]:
        with self._lock:
            return list(self._items)

    @property
    def is_active(self) -> bool:
        with self._lock:
            return any(i.status in (ItemStatus.PENDING, ItemStatus.RUNNING) for i in self._items) and \
                any(t.is_alive() for t in self._threads)

    def summary(self) -> dict[str, int]:
        out = {s.value: 0 for s in ItemStatus}
        for i in self.items:
            out[i.status.value] += 1
        out["total"] = len(self.items)
        return out

    def overall_fraction(self) -> float:
        items = [i for i in self.items if i.status != ItemStatus.SKIPPED]
        if not items:
            return 0.0
        done = sum(1.0 if i.status in FINISHED else (i.progress or 0.0) if i.status == ItemStatus.RUNNING else 0.0 for i in items)
        return done / len(items)

    # ---------------------------------------------------------------- execution
    def start(self) -> None:
        with self._lock:
            self._stop_all = False
            self._threads = [t for t in self._threads if t.is_alive()]
            pending = sum(1 for i in self._items if i.status == ItemStatus.PENDING)
            for _ in range(min(self.max_workers - len(self._threads), pending)):
                t = threading.Thread(target=self._worker, daemon=True, name="batch-worker")
                self._threads.append(t)
                t.start()

    def _next(self) -> Optional[BatchItem]:
        with self._lock:
            if self._stop_all:
                return None
            for it in self._items:
                if it.status == ItemStatus.PENDING:
                    it.status = ItemStatus.RUNNING
                    return it
        return None

    def _worker(self) -> None:
        while (item := self._next()) is not None:
            self.on_update(item)
            job = self._factory(item)
            item._job = job

            def progress(ev: ProgressEvent, item=item) -> None:
                item.progress = ev.fraction
                item.message = ev.detail
                self.on_update(item)

            try:
                item.result = job.run(progress)
                item.duration_s = item.result.duration_s
                item.status, item.message, item.progress = ItemStatus.DONE, "", 1.0
            except CancelledError as exc:
                item.status, item.message, item.error = ItemStatus.CANCELLED, exc.user_message, exc.to_dict()
            except Exception as exc:  # noqa: BLE001
                err: ConversionError = wrap_unexpected(exc)
                item.status, item.message, item.error = ItemStatus.FAILED, err.user_message, err.to_dict()
            finally:
                item._job = None
            self.on_update(item)

    def cancel_pending(self) -> None:
        with self._lock:
            changed = [i for i in self._items if i.status == ItemStatus.PENDING]
            for i in changed:
                i.status, i.message = ItemStatus.CANCELLED, "Cancelled before it started."
        for i in changed:
            self.on_update(i)

    def cancel_all(self) -> None:
        with self._lock:
            self._stop_all = True
            running = [i._job for i in self._items if i.status == ItemStatus.RUNNING and i._job]
        self.cancel_pending()
        for job in running:
            job.cancel()

    def retry_failed(self) -> int:
        n = 0
        with self._lock:
            for i in self._items:
                if i.status in (ItemStatus.FAILED, ItemStatus.CANCELLED):
                    i.status, i.message, i.error, i.progress = ItemStatus.PENDING, "", None, None
                    n += 1
        if n:
            self.start()
        return n

    def wait(self, timeout: Optional[float] = None) -> bool:
        import time
        end = None if timeout is None else time.monotonic() + timeout
        while True:
            with self._lock:
                alive = [t for t in self._threads if t.is_alive()]
            if not alive:
                return True
            if end is not None and time.monotonic() > end:
                return False
            alive[0].join(0.1)
