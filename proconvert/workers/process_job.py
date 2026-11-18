"""Run one conversion in a separate OS process.

Why a process and not just a thread:
  * real cancellation (the child is terminated; threads cannot be killed),
  * crash isolation (a malformed file that crashes a native parser cannot take down the UI),
  * a hard timeout and, on Linux, an optional memory ceiling,
  * the parent removes the child's temp folder and partial output even if the child dies.

Uses the ``spawn`` start method on every platform so behaviour is identical (and PyInstaller-safe;
the frozen entry point must call ``multiprocessing.freeze_support()``).
"""
from __future__ import annotations

import multiprocessing as mp
import queue
import shutil
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from ..core.context import ProgressEvent
from ..core.errors import (
    CancelledError,
    ConversionTimeoutError,
    EngineCrashError,
    error_from_dict,
    wrap_unexpected,
)
from ..core.options import ConversionOptions, Limits
from ..core.pipeline import ConversionResult, convert_file
from ..utils.paths import default_temp_root


def _child_main(q, params: dict) -> None:  # runs in the child process
    try:
        mem = params["limits"].memory_limit_mb
        if mem and sys.platform.startswith("linux"):
            import resource
            limit = mem * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
        last = [0.0, ""]

        def emit(ev: ProgressEvent) -> None:
            now = time.monotonic()
            if ev.stage != last[1] or now - last[0] >= 0.08:
                last[0], last[1] = now, ev.stage
                q.put(("progress", ev.stage, ev.fraction, ev.detail))

        res = convert_file(
            params["source"], params["target"], params["options"], limits=params["limits"],
            overwrite=params["overwrite"], on_progress=emit,
            part_path=params["part_path"], job_dir=params["job_dir"],
        )
        q.put(("done", res.to_dict()))
    except BaseException as exc:  # noqa: BLE001 - everything must reach the parent as data
        q.put(("error", wrap_unexpected(exc).to_dict()))


class ConversionJob:
    _target = staticmethod(_child_main)   # overridable in tests to simulate a crashing worker

    def __init__(self, source: str | Path, target: str | Path, options: Optional[ConversionOptions] = None, *,
                 limits: Optional[Limits] = None, overwrite: bool = False,
                 temp_root: str | Path | None = None, timeout: Optional[float] = None) -> None:
        self.source, self.target = Path(source), Path(target)
        self.options = options or ConversionOptions()
        self.limits = limits or Limits()
        self.overwrite = overwrite
        self.temp_root = Path(temp_root) if temp_root else default_temp_root()
        self.timeout = timeout if timeout is not None else float(self.limits.timeout_seconds)
        self._cancel = threading.Event()
        self.job_dir = self.temp_root / f"job-{uuid.uuid4().hex[:12]}"
        self.part_path = self.target.parent / f".{self.target.name}.{uuid.uuid4().hex[:8]}.part"
        self.pid: Optional[int] = None

    def cancel(self) -> None:
        self._cancel.set()

    @staticmethod
    def _kill(proc) -> None:
        if proc.is_alive():
            proc.terminate()
            proc.join(2.0)
        if proc.is_alive():
            proc.kill()
            proc.join(2.0)

    def run(self, on_progress: Optional[Callable[[ProgressEvent], None]] = None) -> ConversionResult:
        on_progress = on_progress or (lambda e: None)
        mpctx = mp.get_context("spawn")
        q = mpctx.Queue()
        params = {
            "source": str(self.source), "target": str(self.target), "options": self.options,
            "limits": self.limits, "overwrite": self.overwrite,
            "part_path": str(self.part_path), "job_dir": str(self.job_dir),
        }
        proc = mpctx.Process(target=self._target, args=(q, params), daemon=True)
        deadline = time.monotonic() + self.timeout
        try:
            proc.start()
            self.pid = proc.pid
            while True:
                if self._cancel.is_set():
                    self._kill(proc)
                    raise CancelledError()
                if time.monotonic() > deadline:
                    self._kill(proc)
                    raise ConversionTimeoutError()
                try:
                    msg = q.get(timeout=0.1)
                except queue.Empty:
                    if proc.is_alive():
                        continue
                    try:
                        msg = q.get(timeout=0.5)  # drain a message sent just before exit
                    except queue.Empty:
                        raise EngineCrashError(technical=f"worker exited with code {proc.exitcode}") from None
                kind = msg[0]
                if kind == "progress":
                    on_progress(ProgressEvent(msg[1], msg[2], msg[3]))
                elif kind == "done":
                    return ConversionResult(**msg[1])
                elif kind == "error":
                    raise error_from_dict(msg[1])
        finally:
            self._kill(proc)
            try:
                q.close()
                q.cancel_join_thread()
            except Exception:  # noqa: BLE001
                pass
            shutil.rmtree(self.job_dir, ignore_errors=True)
            try:
                self.part_path.unlink(missing_ok=True)
            except OSError:
                pass
