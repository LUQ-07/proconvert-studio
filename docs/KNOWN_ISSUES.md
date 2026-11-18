# Known issues and limitations (honest list)

## 1.0.0 release status (read this first)
* Verified by automated tests in a Linux sandbox: conversion engines, image engine (also rendered through LibreOffice to confirm one image per page), history, settings, localisation completeness, release requirements (version, removed update/hardware UI, compatibility grid, ad-free, no network imports), MSIX manifest well-formedness.
* **NOT verified:** the real Qt user interface (only a Qt-stub smoke test exists - the new Images page, the Help grid and the removed sections have never been seen on screen; drag-and-drop reordering, high-DPI and RTL layout are untested); the frozen `.exe` and MSIX on real Windows 10/11; installation/uninstallation; the Windows App Certification Kit; the Store submission. CI results from GitHub reflect only what was seen on `windows-latest`.
* **Conversion quality:** PDF -> Word was promoted to Supported (text-layer PDFs; evidence and limits in docs/FIDELITY_REPORT.md, based on ONE real 67-page document plus a synthetic regression corpus). The other 6 routes stay Experimental: PDF -> PowerPoint/Excel, Word -> PowerPoint/Excel, PowerPoint -> Excel, Excel -> PowerPoint.
* The sidebar slide animation, the Back/menu buttons and the new icon were checked only through logic tests and image previews; their look inside the real window (RTL mirroring of the Back arrow, high-DPI sharpness, theme colours) is unverified.
* **Picture -> Excel (experimental):** needs Tesseract. The Microsoft Store package does NOT bundle Tesseract yet, so on a customer's PC this feature is unavailable until the engine is bundled (or installed by the user); the app says so instead of failing. Verified only on SYNTHETIC tables rendered by the test-suite (ruled, horizontal rules only, borderless; rotated up to 2.5 degrees; noise, uneven lighting, Gaussian blur with JPEG quality 45, small 16 px text): all cells exact with English text. **Known failure: perspective distortion** (a table photographed at an angle): the lines are no longer straight, the grid is not found, the program falls back to guessing columns from the text and returns a wrong table with a low-confidence warning. Not supported / not verified: real photographs, handwriting, merged cells (their text lands in one cell), several tables in one picture (only one is read), non-English language packs (only `eng` was installed here).
* Images: processed in-process (not in a separate OS process like documents); protected by explicit pixel/size/count limits. Thumbnails are generated synchronously when files are added (many very large images can make the UI pause briefly). Word output centres images with paragraph spacing; Word's own rendering has not been checked (LibreOffice rendering was). GIF is not supported. Transparency is flattened onto white.
* Uninstalling the MSIX removes per-package settings/history (see docs/MICROSOFT_STORE.md).

## Scope decision
Windows only, shipped through the Microsoft Store. macOS/Linux packaging was removed; the Python code itself is still portable. Product name stays ProConvert Studio; no PDF reader/annotation features are planned. MSIX packaging and Store submission are NOT done.

## Status of the phased work request (updated in this session)
Environment of this session: Linux, Python 3.12, **no network** (pip cannot install; PySide6, pytest-qt, hypothesis, pip-audit, pip-licenses, PyInstaller all unavailable), no Windows/macOS machine.
* **Phase 0 (real-system validation): NOT DONE.** The GUI was not run (PySide6 missing), no installer was built. A CI workflow was *written and its YAML syntax/structure checked* but never executed; whatever it finds on a real runner is still unknown. pypdf >= 6.14.1 and `pip-audit` remain unrun (installed: pypdf 5.9.0).
* **Phase 1 (fidelity): PARTIAL.** Done and tested: DOCX numbered lists, footnotes/endnotes (as a Notes list), header/footer text; PDF numbered-list detection. Not started: PDF table confidence scoring, 3+ columns/sidebars, footnotes/rotated text/links in PDF, DOCX text boxes/nested tables, XLSX charts/widths/merges/styles, PPTX shapes/notes, visual-fidelity mode, Quality Report, CJK/Arabic PDF output.
* **Phases 2-4: NOT STARTED.**
* **ProDoc Suite brief (second request): only the PDF-management engine exists** (`proconvert/pdftools`, tested, no UI). NOT done: rename to ProDoc Suite, PDF reader/viewer, annotations, signatures, Windows installer changes / file association / MSIX, printing, LibreOffice/Office engine detection, new language selector work, recent/favorites. PDF/A is not offered (no validating engine). Watermark/page-number text in Arabic/Hebrew is not shaped (same limitation as PDF output). Compression ratio depends on the file; already-optimised PDFs may grow.
* On extraction of the ZIP, `packaging/**/*.sh` had lost their executable bit and 3 packaging tests failed until `chmod +x` was applied; the shipped ZIP stores them without the bit, so re-run `chmod +x` after unzipping.

## Not verified (blocks a public release)
1. **The PySide6 UI has never been run.** It compiles, imports, constructs and runs its handlers against a fake Qt (`tests/test_ui_smoke.py`), and its design tokens meet WCAG AA by test. Rendering, layout, Qt API correctness, drag-and-drop, high-DPI, keyboard focus order, RTL layout, tray notifications and theme switching are **unverified**. Expect some first-run fixes.
2. **No installer or frozen build exists.** Spec, Inno Setup, macOS and Linux scripts are unrun; only the `.deb` assembly was exercised with a dummy payload (and that found one real bug).
3. **Windows and macOS were never used.** Engine code is portable Python but untested there; Windows-only code paths (RAM query, `os.startfile`, `explorer /select`) are untested.
4. **Dependency versions**: the suite ran on pypdf 5.9.0 while the manifest requires >= 6.14.1 (security). Re-run on the pinned set + `pip-audit`.
5. **Translations** (fr/es/ar) are unreviewed drafts. RTL layout is unverified.
6. There is no update mechanism (download a new release), no support mailbox (use GitHub issues), and the executables are not code-signed, so Windows SmartScreen may warn on first run.

## Product limitations
* Layout is rebuilt, not copied. Multi-column PDFs are handled for two columns only; space-aligned PDF tables are not detected (ruled tables only); no PDF vector graphics/charts; annotations/forms ignored.
* DOCX: text boxes, equations, nested tables not converted (reported); footnotes become an end-of-document Notes list (no in-text markers); header/footer is plain text from the first section that has one, page-number fields are not carried; numbering restored by counting items (restarts via `lvlOverride` and non-decimal formats such as roman/letters are shown as plain numbers).
* PPTX: shapes/SmartArt/animations/notes not converted; charts become data tables.
* XLSX: formulas not evaluated (stored results used); charts/images not converted; hidden sheets skipped; Excel number formats only partly supported.
* PDF output: bundled DejaVu fonts cover Latin/Greek/Cyrillic; CJK replaced by `?`; RTL not shaped; very long table cells are shortened (reported).
* Word output caps tables at 5,000 rows, PowerPoint at 600 rows/500 slides, PDF at 50,000 rows (all reported).
* PDF text ordering is heuristic: sidebars, footnotes, rotated text and complex layouts can interleave.
* Memory/time: see `BENCHMARKS.md` (one machine, one run each). Memory cap is Linux-only and off by default.
* Cancel terminates the worker process; very large outputs being copied at the final step finish the copy first.
* Window geometry is not persisted; notifications use the tray API where available.
