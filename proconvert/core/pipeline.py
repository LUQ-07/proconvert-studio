"""The conversion pipeline: validate -> read -> write -> verify -> atomic finalize.

Output is built in an application temp folder, verified by re-opening it with an
independent parser, copied next to the destination as a hidden ``.part`` file and moved
into place with an atomic ``os.replace``. Any failure or cancellation leaves no partial
output and no temp files behind.
"""
from __future__ import annotations

import logging
import os
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..converters.registry import get_reader, get_writer
from ..utils.paths import default_temp_root
from .capabilities import route_for
from .context import DONE, FINALIZING, VALIDATING, VERIFYING, CancelToken, JobContext, ProgressEvent
from .errors import (
    ConversionError,
    EmptyContentError,
    OutputExistsError,
    UnsupportedFormatError,
    wrap_unexpected,
)
from .ir import ir_stats
from .options import ConversionOptions, Limits
from .security import SUPPORTED_FORMATS, extension_format, validate_source, validate_target
from .verify import verify_output

log = logging.getLogger("proconvert.pipeline")


@dataclass
class ConversionResult:
    output_path: str
    source_format: str
    target_format: str
    engine: str
    status: str                      # route tier: "supported" | "experimental"
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    verified: dict = field(default_factory=dict)
    duration_s: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def convert_file(
    source: str | Path,
    target: str | Path,
    options: ConversionOptions | None = None,
    *,
    limits: Limits | None = None,
    overwrite: bool = False,
    temp_root: str | Path | None = None,
    on_progress: Callable[[ProgressEvent], None] | None = None,
    cancel: CancelToken | None = None,
    part_path: str | Path | None = None,
    job_dir: str | Path | None = None,
) -> ConversionResult:
    started = time.monotonic()
    options = options or ConversionOptions()
    limits = limits or Limits()
    ctx = JobContext(options, limits, cancel or CancelToken(), on_progress or (lambda e: None))
    owns_job_dir = job_dir is None
    job_path = Path(job_dir) if job_dir else Path(temp_root or default_temp_root()) / f"job-{uuid.uuid4().hex[:12]}"
    part: Optional[Path] = Path(part_path) if part_path else None
    try:
        ctx.report(VALIDATING, None, "Checking the file")
        src_fmt_guess = extension_format(Path(source))
        dst_fmt = extension_format(Path(target))
        if dst_fmt not in SUPPORTED_FORMATS:
            raise UnsupportedFormatError(f"Output format .{dst_fmt or '(none)'} is not supported.")
        info = validate_source(source, limits)
        route = route_for(info.fmt, dst_fmt)
        if route is None:
            raise UnsupportedFormatError("Choose two different supported formats (PDF, DOCX, PPTX, XLSX).")
        final = validate_target(target, info.path, dst_fmt, overwrite=overwrite)
        if info.has_macros:
            ctx.warn("The file contains macros. Macros are never run and are not copied to the output.")
        ctx.cancel.check()
        job_path.mkdir(parents=True, exist_ok=True)
        staged = job_path / f"result.{dst_fmt}"
        log.info("convert start route=%s size=%d", route.key, info.size)

        ir = get_reader(info.fmt)(info.path, ctx)
        ctx.cancel.check()
        stats = ir_stats(ir)
        if not stats.has_content():
            raise EmptyContentError()
        get_writer(dst_fmt)(ir, staged, ctx)
        ctx.cancel.check()

        ctx.report(VERIFYING, None, "Validating the new file")
        verified = verify_output(staged, dst_fmt)

        ctx.report(FINALIZING, None, "Saving the result")
        ctx.cancel.check()
        if part is None:
            part = final.parent / f".{final.name}.{uuid.uuid4().hex[:8]}.part"
        shutil.copyfile(staged, part)
        if final.exists() and not overwrite:
            raise OutputExistsError(f"'{final.name}' already exists.")
        os.replace(part, final)
        part = None
        ctx.report(DONE, 1.0, "Done")
        duration = time.monotonic() - started
        log.info("convert ok route=%s sec=%.2f warnings=%d", route.key, duration, len(ctx.warnings))
        return ConversionResult(
            str(final), info.fmt, dst_fmt, route.engine, route.status, list(ctx.warnings),
            {"sections": stats.sections, "paragraphs": stats.paragraphs, "tables": stats.tables,
             "table_rows": stats.table_rows, "pictures": stats.pictures, "characters": stats.characters},
            verified, duration,
        )
    except ConversionError as exc:
        log.warning("convert failed code=%s", exc.code)
        raise
    except Exception as exc:
        err = wrap_unexpected(exc)
        log.error("convert crashed: %s", err.technical)
        raise err from exc
    finally:
        if part is not None:
            try:
                part.unlink(missing_ok=True)
            except OSError:
                pass
        if owns_job_dir:
            shutil.rmtree(job_path, ignore_errors=True)
