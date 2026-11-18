"""PPTX -> IR using python-pptx.

One IR section per slide: title, text (with bullets and levels), tables, pictures, and
chart *data* (charts are converted to data tables). Shapes, SmartArt, animations and
speaker notes are not converted; SmartArt is counted and reported.
"""
from __future__ import annotations

from pathlib import Path

from ..core.context import READING, JobContext
from ..core.errors import ConversionError, DependencyMissingError, InvalidFileError, UnsafeFileError
from ..core.images import normalize_image
from ..core.ir import Block, DocumentIR, Paragraph, Run, Section, Table
from ..utils.text import clean_block, clean_inline


def _pos(shape):
    try:
        return (shape.top or 0, shape.left or 0)
    except Exception:
        return (0, 0)


def _iter_shapes(shapes, MSO):
    for shape in sorted(shapes, key=_pos):
        try:
            is_group = shape.shape_type == MSO.GROUP
        except Exception:
            is_group = False
        if is_group:
            yield from _iter_shapes(shape.shapes, MSO)
        else:
            yield shape


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return str(int(v)) if v == int(v) and abs(v) < 1e15 else f"{v:.10g}"
    return str(v)


def _chart_table(chart) -> tuple[str, Table] | None:
    try:
        plot = chart.plots[0]
        cats = [clean_inline(str(c)) for c in plot.categories]
        series = list(plot.series)
        if not series:
            return None
        rows = [[""] + [clean_inline(s.name) for s in series]]
        vals = [list(s.values) for s in series]
        for i, c in enumerate(cats):
            rows.append([c] + [_fmt(v[i]) if i < len(v) else "" for v in vals])
        title = ""
        try:
            if chart.has_title and chart.chart_title.has_text_frame:
                title = clean_inline(chart.chart_title.text_frame.text)
        except Exception:
            pass
        return title, Table(rows)
    except Exception:
        return None


def read_pptx(path: Path, ctx: JobContext) -> DocumentIR:
    try:
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE as MSO
        from pptx.enum.shapes import PP_PLACEHOLDER
        from pptx.oxml.ns import qn
    except ImportError as exc:  # pragma: no cover
        raise DependencyMissingError(technical=str(exc)) from exc

    try:
        prs = Presentation(str(path))
    except ConversionError:
        raise
    except Exception as exc:
        name = type(exc).__name__
        if "Entit" in name or "Forbidden" in name:
            raise UnsafeFileError("The presentation contains disallowed XML constructs.", technical=f"{name}: {exc}") from exc
        raise InvalidFileError("The PowerPoint file is damaged or uses an unsupported structure.", technical=f"{name}: {exc}") from exc

    slides = list(prs.slides)
    ir = DocumentIR(path.stem, source_format="pptx")
    smartart = charts_as_tables = charts_failed = 0
    for n, slide in enumerate(slides, 1):
        ctx.cancel.check()
        ctx.report(READING, (n - 1) / max(len(slides), 1), f"Slide {n} of {len(slides)}")
        blocks: list[Block] = []
        title_id = None
        try:
            ts = slide.shapes.title
            if ts is not None and ts.has_text_frame:
                title_id = ts.shape_id
                t = clean_inline(ts.text_frame.text)
                if t:
                    blocks.append(Paragraph.plain(t, heading=1))
        except Exception:
            pass
        for shape in _iter_shapes(slide.shapes, MSO):
            if title_id is not None and getattr(shape, "shape_id", None) == title_id:
                continue
            try:
                if shape.has_text_frame and shape.text_frame.text.strip():
                    body_ph = False
                    try:
                        body_ph = shape.is_placeholder and shape.placeholder_format.type in (PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.OBJECT)
                    except Exception:
                        pass
                    for p in shape.text_frame.paragraphs:
                        text = clean_block(p.text.replace("\v", " "))
                        if not text:
                            continue
                        ppr = p._p.pPr
                        explicit_none = ppr is not None and ppr.find(qn("a:buNone")) is not None
                        explicit_char = ppr is not None and (ppr.find(qn("a:buChar")) is not None or ppr.find(qn("a:buAutoNum")) is not None)
                        bullet = explicit_char or (body_ph and not explicit_none)
                        runs = []
                        for r in p.runs:
                            rt = r.text.replace("\v", " ")
                            if rt:
                                runs.append(Run(rt, bool(r.font.bold), bool(r.font.italic)))
                        if not runs or clean_block("".join(r.text for r in runs)) != text:
                            runs = [Run(text)]
                        else:
                            runs[0] = Run(runs[0].text.lstrip(), runs[0].bold, runs[0].italic)
                            runs[-1] = Run(runs[-1].text.rstrip(), runs[-1].bold, runs[-1].italic)
                        blocks.append(Paragraph(runs, bullet=bullet, level=max(0, min(int(p.level or 0), 2))))
                    continue
                if getattr(shape, "has_table", False) and shape.has_table:
                    rows = [[("" if getattr(c, "is_spanned", False) else clean_inline(c.text)) for c in row.cells] for row in shape.table.rows]
                    if any(c for r in rows for c in r):
                        blocks.append(Table(rows))
                    continue
                if getattr(shape, "has_chart", False) and shape.has_chart:
                    res = _chart_table(shape.chart)
                    if res:
                        title, tbl = res
                        if title:
                            blocks.append(Paragraph([Run(title, bold=True)]))
                        blocks.append(tbl)
                        charts_as_tables += 1
                    else:
                        charts_failed += 1
                    continue
                st = None
                try:
                    st = shape.shape_type
                except Exception:
                    pass
                if st == MSO.PICTURE or hasattr(shape, "image"):
                    if ctx.options.include_images:
                        try:
                            pic = normalize_image(
                                shape.image.blob, ctx,
                                display_w_pt=(shape.width or 0) / 12700 or None,
                                display_h_pt=(shape.height or 0) / 12700 or None,
                            )
                            if pic:
                                blocks.append(pic)
                        except (AttributeError, ValueError):
                            pass
                    continue
                if st == MSO.EMBEDDED_OLE_OBJECT or (shape.__class__.__name__ == "GraphicFrame"):
                    smartart += 1
            except ConversionError:
                raise
            except Exception:
                ctx.warn(f"A shape on slide {n} could not be read and was skipped.")
        ir.sections.append(Section("slide", f"Slide {n}", blocks))

    if charts_as_tables:
        ctx.warn(f"{charts_as_tables} chart(s) were converted to data tables (the chart graphics are not reproduced).")
    if charts_failed:
        ctx.warn(f"{charts_failed} chart(s) could not be read and are not included.")
    if smartart:
        ctx.warn(f"{smartart} SmartArt/embedded object(s) are not converted.")
    return ir
