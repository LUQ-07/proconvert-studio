# Benchmarks

Measured 2026-10-23 on: Linux-6.18.44-fc-v153-x86_64-with-glibc2.39, x86_64, 1 vCPU, Python 3.12.3. Single run per case (no averaging) in a fresh process; times include library import. These numbers describe *this machine only*; other cases may have been run while other work shared the single vCPU, so treat them as upper bounds.

| Workload | Route | Input KB | Output KB | Seconds | Peak RSS MB | Warnings |
|---|---|---|---|---|---|---|
| 150-page text PDF | pdf->docx | 99 | 38 | 17.35 | 69 | 0 |
| 150-page text PDF | pdf->pptx | 99 | 338 | 18.14 | 75 | 0 |
| 30,000-row x 8-col XLSX | xlsx->pdf | 1387 | 2928 | 69.11 | 204 | 0 |
| 30,000-row x 8-col XLSX | xlsx->docx | 1387 | 190 | 10.25 | 228 | 1 |
| 30,000-row x 8-col XLSX | xlsx->pptx | 1387 | 125 | 6.67 | 94 | 1 |
| 4,000 paragraphs + 100 tables DOCX | docx->pdf | 63 | 278 | 2.74 | 78 | 0 |
| 4,000 paragraphs + 100 tables DOCX | docx->xlsx | 63 | 116 | 1.51 | 70 | 0 |
| 4,000 paragraphs + 100 tables DOCX | docx->pptx | 63 | 559 | 3.29 | 72 | 1 |

## Optimization history (measured on this same machine during development)
| Change | Before | After |
|---|---|---|
| PDF line extraction: `extract_text_lines()` -> `extract_words()` + own grouping (150-page PDF, peak memory) | 695 MB | 62 MB (reader alone) / 69 MB (full route) |
| DOCX reader: cache python-docx style lookups (1,500 paragraphs + 40 tables, read time) | 16.7 s | 0.43 s |
| DOCX 4,000 paragraphs + 100 tables -> PDF (full route) | ~25 s | 2.7 s |
| DOCX writer: address `<w:tc>` directly instead of `row.cells` (2,000-row table) | 5.25 s | 1.41 s |
| XLSX 30,000 rows -> DOCX (after lowering the Word table cap 20,000 -> 5,000 rows) | 23.4 s / 684 MB | 10.3 s / 228 MB |

Raw data: `docs/benchmark_results.json`. Reproduce: `python tools/benchmark.py --out docs/BENCHMARKS.md` (resumable; delete the JSON to start over). Not measured: Windows/macOS, typical customer hardware, files larger than those above, cold-start time of the GUI or of a frozen build.
