"""Benchmark representative workloads. Each case runs in a fresh process; peak RSS is measured per child.

Usage: python tools/benchmark.py [--out docs/BENCHMARKS.md]
Numbers are specific to the machine that ran them and are recorded with its description.
"""
from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CASES = [  # (label, builder, source, target)
    ("150-page text PDF", "big_pdf", "pdf", "docx"),
    ("150-page text PDF", "big_pdf", "pdf", "pptx"),
    ("30,000-row x 8-col XLSX", "big_xlsx", "xlsx", "pdf"),
    ("30,000-row x 8-col XLSX", "big_xlsx", "xlsx", "docx"),
    ("30,000-row x 8-col XLSX", "big_xlsx", "xlsx", "pptx"),
    ("4,000 paragraphs + 100 tables DOCX", "big_docx", "docx", "pdf"),
    ("4,000 paragraphs + 100 tables DOCX", "big_docx", "docx", "xlsx"),
    ("4,000 paragraphs + 100 tables DOCX", "big_docx", "docx", "pptx"),
]

RUNNER = """
import sys, time
sys.path.insert(0, {root!r})
from proconvert.core.pipeline import convert_file
t=time.monotonic()
r=convert_file({src!r}, {dst!r}, temp_root={tmp!r}, overwrite=True)
import resource
print(round(time.monotonic()-t,2), len(r.warnings), resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024)
"""


def render_md(rows, out):
    cpu = platform.processor() or platform.machine()
    header = (f"# Benchmarks\n\nMeasured {time.strftime('%Y-%m-%d')} on: {platform.platform()}, {cpu}, {os.cpu_count()} vCPU, "
              f"Python {platform.python_version()}. Single run per case (no averaging) in a fresh process; "
              "times include library import. These numbers describe *this machine only*; other cases may have been run while other "
              "work shared the single vCPU, so treat them as upper bounds.\n\n"
              "| Workload | Route | Input KB | Output KB | Seconds | Peak RSS MB | Warnings |\n|---|---|---|---|---|---|---|\n")
    body = "\n".join(f"| {l} | {r} | {i} | {o} | {s} | {m} | {w} |" for l, r, i, o, s, m, w in rows)
    Path(out).write_text(header + body + "\n", encoding="utf-8")


def main() -> None:
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    ap.add_argument("--state", default=str(ROOT / "docs" / "benchmark_results.json"), help="resumable results file")
    ap.add_argument("--max-cases", type=int, default=99, help="stop after running this many new cases (for time-limited shells)")
    a = ap.parse_args()
    from tests import make_corpus as mc

    state = Path(a.state)
    rows = [tuple(r) for r in json.loads(state.read_text())] if state.exists() else []
    done = {(r[0], r[1]) for r in rows}
    ran = 0
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        builders = {"big_pdf": lambda: mc.big_pdf(d / "big.pdf", 150), "big_xlsx": lambda: mc.big_xlsx(d / "big.xlsx", 30000, 8),
                    "big_docx": lambda: mc.big_docx(d / "big.docx", 4000, 100)}
        built = {}
        for label, b, s, t in CASES:
            if (label, f"{s}->{t}") in done or ran >= a.max_cases:
                continue
            if b not in built:
                built[b] = builders[b]()
            src, dst = built[b], d / f"out_{b}.{t}"
            code = RUNNER.format(root=str(ROOT), src=str(src), dst=str(dst), tmp=str(d / "tmp"))
            try:
                cp = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=600)
                ok, out, err = cp.returncode == 0, cp.stdout, cp.stderr
            except subprocess.TimeoutExpired:
                ok, out, err = False, "", "timeout after 600 s"
            secs, warns, rss = (out.split() + ["?", "?", "?"])[:3] if ok else ("FAILED/timeout", "", 0)
            rows.append((label, f"{s}->{t}", src.stat().st_size // 1024, dst.stat().st_size // 1024 if (ok and dst.exists()) else 0, secs, rss, warns))
            state.write_text(json.dumps(rows))
            ran += 1
            print(rows[-1], err[-200:] if not ok else "", flush=True)
    if a.out:
        render_md(rows, a.out)


if __name__ == "__main__":
    main()
