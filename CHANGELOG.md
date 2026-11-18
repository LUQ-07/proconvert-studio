# Changelog
Format: [Keep a Changelog](https://keepachangelog.com/) - versioning: [Semantic Versioning 2.0](https://semver.org/). Release cadence: monthly or as needed; security fixes out of band.

## [1.0.0] - first official release (release candidate; see docs/KNOWN_ISSUES.md for what is unverified)
### Added
- **Images to PDF / Word** (`proconvert/converters/image_tools.py`, UI page "Images to PDF / Word"): PNG, JPG/JPEG, BMP, TIFF (multi-page), WebP; one image per page; add many, preview, reorder (drag or buttons), remove; A4 / Letter / fit-to-image, portrait / landscape / automatic, margins, top/centre position, optional no-upscaling; JPEG embedded unchanged, other formats lossless, no distortion; atomic output, no silent overwrite, cancel, progress, result verification; entries appear in History (retry supported).
- Help: the compatibility table is now a Source x Target grid with Supported / Experimental indicators, generated from the real route model (`compatibility_grid()`), in all four languages.
- DOCX: numbered lists keep their numbers; footnotes/endnotes appended as a numbered Notes list; header/footer text carried to Word and PDF output. PDF reader detects numbered items.
- `proconvert.pdftools`: merge, split, extract, delete, reorder, rotate, duplicate pages, watermark, page numbers, metadata, AES-256 protect/unprotect, compress, images<->PDF (engine only, no UI).
- MSIX packaging for the Microsoft Store: manifest template, `build_msix.ps1`, tile generator, static tests, CI smoke job, `docs/MICROSOFT_STORE.md`.
- GitHub Actions CI (Windows only).
- **Images to PowerPoint** (one picture per slide, 16:9 or A4/Letter, never stretched) and **picture of a table to Excel** (`converters/image_table.py`: straightening, ruled / horizontal-rule / borderless tables, one OCR pass with Tesseract, cell assignment, digit repair, one sheet per picture; experimental). New dependency: numpy (BSD).
- Help table: new "Images" row (PDF, Word, PowerPoint: Supported; Excel: Experimental), derived from `capabilities.image_row()`.
- `LICENSE.txt` (proprietary, all rights reserved; draft pending legal review) and a copyright line on the About page (`config.COPYRIGHT_HOLDER`).
- PDF reader: running headers/footers detected in the top/bottom 10 % band (not 8 %), kept as the document header/footer; Wingdings/Symbol bullets and arrows mapped to Unicode in every reader; unmarked indented lines under a list item become nested items; short lines are not glued into the previous item. `tools/score_fidelity.py` and `docs/FIDELITY_REPORT.md`.
- PowerPoint writer: no empty slides (title + subtitle share a slide), PDF pages no longer force new slides or "Page N" titles, 14 pt body text, the source header shown as a slide footer.
- `config.DISABLED_ROUTES`: one setting that removes any conversion from the Convert page, Batch, Dashboard, Help table, CLI and self-test (default: nothing removed). Tests adapt to it.
### Changed
- **Open source:** released under the MIT License (`LICENSE`); public-repository files added (`README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, issue and pull-request templates, `.gitignore`, `docs/PRIVACY.md`). The About page shows the MIT license and a link to the source; Help has a "Report a problem" button that opens the GitHub issue page.
- **PDF -> Word is now Supported** (PDF -> PowerPoint stays Experimental); see docs/FIDELITY_REPORT.md for the evidence and limits.
- **Navigation:** a top bar with a menu button (Ctrl+B) that slides the sidebar in/out (remembered between sessions) and a Back button (Alt+Left) that returns to the previous screen; the current page title is shown in the bar.
- **Licensing UI hidden while licensing is off:** the licence card on About, the dashboard line and the sidebar badge no longer show anything ("Licensing is not enabled in this build" is gone). The licence manager itself is unchanged and can be switched on later.
- **New application icon** (document sheets + conversion badge) regenerated as PNG/ICO/SVG and Store tiles by `tools/make_icons.py` + `tools/make_store_assets.py`; the stale macOS icon was removed.
- Version 1.0.0 everywhere; all beta labels removed from code, translations, installer and docs.
- **Windows-only (Microsoft Store).** macOS/Linux packaging and CI jobs removed.
- Settings: the "Hardware and application information" section (and its copy button) removed; remaining settings unchanged.
### Removed
- Everything commercial: the licensing / trial / activation feature (`proconvert/licensing`, its UI, settings, strings and tests), `tools/license_tool.py`, the marketing, pricing and legal-draft documents (`docs/marketing`, `docs/legal`), the commercial distribution checklist, and `LICENSE.txt` (proprietary notice).
- In-app update check/download UI, the update service, its settings option, config constants, locale strings and tests (updates are delivered by the Microsoft Store). Old settings files containing the removed option still load.
### Fixed
- `tools/run_tests.py` no longer crashes on Windows (`/dev/null`); macOS path-symlink test comparison; PyInstaller spec now collects the whole PDF stack (PDF routes failed in the first frozen CI build).
### Not done (see docs/KNOWN_ISSUES.md)
- Experimental routes were NOT upgraded to Supported: no change to the conversion engines was made for them, so they remain Experimental by design and by the table you specified.
- The Qt UI, frozen build, MSIX and Store submission have not been verified on a real Windows machine by the author.

## [3.0.0-beta.1] - 2026-10-23
Complete rewrite of 2.0 (see `docs/AUDIT_REPORT.md`).
### Added
- Shared read -> model -> write pipeline for all 12 routes; text, headings, bullets, bold/italic, tables, images preserved; charts in PPTX converted to data tables; two-column PDF ordering; repeating PDF header/footer removal; optional OCR.
- Separate-process workers with real cancel, timeout and crash containment; batch queue with retry.
- Input validation (signature, ZIP-bomb, XML DTD ban), atomic output, post-write verification, friendly errors.
- SQLite history, validated settings, diagnostics export, redacted logs, offline licensing (off by default), signed update checker (off until configured).
- Premium PySide6 UI (dark/light/system), English + draft French/Spanish/Arabic (RTL).
- Windows/macOS/Linux packaging scripts; test suite; documentation; legal and marketing drafts.
### Changed
- PyMuPDF (AGPL) and Microsoft Office COM automation removed.
### Security
- `pypdf>=6.14.1` required (published DoS advisories); formula-injection and entity-expansion defences.
### Known gaps
- GUI and installers not yet run on real systems; see `docs/KNOWN_ISSUES.md`.

## [2.0] - uploaded prototype (superseded)
