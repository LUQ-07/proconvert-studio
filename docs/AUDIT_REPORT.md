# Phase 1 audit of ProConvert Studio 2.0 (the uploaded ZIP)

Scope: the entire archive (15 files, 547 lines of Python: `app.py` 284, `engine.py` 237, tests 23).

## Blocking defects (found and what this rewrite does)

| # | Finding in 2.0 | Why it matters | Resolution in 3.0 |
|---|---|---|---|
| 1 | Depends on **PyMuPDF** (`import fitz`) | PyMuPDF is AGPL-3.0 (or a paid Artifex license). A permissively licensed app cannot link it without becoming AGPL itself (replaced by pypdf + pdfplumber + reportlab) | Removed. PDF reading uses pdfplumber/pdfminer.six (MIT), pypdf (BSD-3); OCR rendering uses pypdfium2 (Apache/BSD). |
| 2 | Some routes call **Microsoft Word/PowerPoint/Excel via COM** (`win32com`) | Violates "must not require Office"; Windows-only; fragile; Office licensing. | Removed. All 12 routes use the shared pure-Python pipeline. |
| 3 | Conversions were **text-only**; images and most table structure were dropped | Silent content loss. | Neutral document model with paragraphs, runs (bold/italic), headings, lists, tables, images. |
| 4 | **Fabricated progress** (`setValue(100)` at the end, fixed steps in between) and no cancellation | Violates "no fabricated percentages". | Real stage events (per page/slide/sheet counts); unmeasurable stages are indeterminate; each job runs in a killable worker process. |
| 5 | **Silent truncation** at 15,000 lines | Output looked complete but was not. | Every limit is explicit and produces a visible warning (`Limits` in `core/options.py`). |
| 6 | No input validation: extension trusted, no signature check, no ZIP-bomb, no path rules | Malformed or hostile files reach parsers. | `core/security.py`: signature + package checks, ZIP-bomb limits, DTD/entity rejection, output-path rules. |
| 7 | Spreadsheet cells written from untrusted text | Text beginning with `=` becomes a live formula (formula injection). | Writer stores all text as string cells; covered by a test. |
| 8 | Output written directly to the destination | A crash or cancel leaves a partial/corrupt file. | Build in temp, verify by re-opening, atomic replace; cleanup on every path. |
| 9 | History kept as a JSON file in `~/.proconvert_studio` | No search/sort/filter, no CSV safety, easy to corrupt. | SQLite with parameterised queries and a CSV exporter that neutralises formulas. |
| 10 | Settings in `QSettings` mixed with UI code | Not testable, no validation. | `settings/store.py`: validated, atomic JSON; Qt-free. |
| 11 | Arabic/French/Spanish "translations" covered a handful of strings | Presented as supported but mostly English. | Full-coverage JSON catalogs, honestly labelled "draft translation" because no native speaker has reviewed them. |
| 12 | No logging, diagnostics, crash handling or installer | Not distributable. | Added (local logging with redaction, user-triggered diagnostics export, crash handler, Windows installer). |
| 13 | 4 test functions | Nothing verified. | See `docs/TEST_REPORT.md`. |

## What was reused
The product name, the idea of a Qt desktop app with four converter categories, and the build-script concept. Essentially no code was carried over: the architecture was replaced rather than patched, because the defects above are structural.

## Residual risks identified (still open)
See `docs/KNOWN_ISSUES.md` - notably that the Qt UI and all installers could not be executed in the authoring environment.
