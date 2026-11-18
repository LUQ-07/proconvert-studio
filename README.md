# ProConvert Studio

A free, open-source **document converter for Windows**. Convert between **PDF, Word, PowerPoint and Excel**, turn **images into
PDF / Word / PowerPoint**, and read a **table from a picture into Excel**. Everything runs **on your own computer**: your files are
never uploaded, and neither Microsoft Office nor LibreOffice is needed.

Current version: **1.0.0** · License: [MIT](LICENSE) · Languages of the interface: English, Français, Español, العربية (right-to-left)

## What it can do

| Source | to PDF | to Word | to PowerPoint | to Excel |
|---|---|---|---|---|
| PDF | - | **supported** | experimental | experimental |
| Word | **supported** | - | experimental | experimental |
| PowerPoint | **supported** | **supported** | - | experimental |
| Excel | **supported** | **supported** | experimental | - |
| Images (PNG, JPG, BMP, TIFF, WebP) | **supported** | **supported** | **supported** | experimental (OCR) |

* **Supported** means the text, tables and pictures are carried over and the conversion is covered by automated tests. The
  layout is rebuilt, not copied pixel for pixel.
* **Experimental** means the structure is reconstructed automatically; always review the result.
* "PDF to Word" is supported for PDFs that contain real text. Scanned PDFs need OCR (see below). Measurements on a real
  67-page document and the limits are in [docs/FIDELITY_REPORT.md](docs/FIDELITY_REPORT.md).

Other features: batch conversion, drag and drop, conversion history, dark / light / system theme, a command line interface,
PDF tools (merge, split, extract, rotate, watermark, page numbers, password protect, compress) in the engine, OCR for scanned
pages (optional, needs [Tesseract](https://github.com/tesseract-ocr/tesseract)).

## Install

**From a release (no Python needed):** download the Windows installer or the zip from the
[Releases](https://github.com/LUQ-07/prodoc-suite/releases) page, check its SHA-256 sum, and run it.

**From source (Windows, Git Bash):**
```bash
git clone https://github.com/LUQ-07/prodoc-suite.git
cd prodoc-suite
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements/gui.txt
python launch.py
```
Python 3.11 or newer is required.

## Use it

* **Graphical app:** `python launch.py`, then *Convert*, *Batch* or *Images to PDF / Office*.
* **Command line** (no Qt needed):
  ```bash
  python -m proconvert convert report.docx report.pdf
  python -m proconvert convert slides.pptx slides.docx --overwrite
  python -m proconvert --self-test        # converts built-in samples through every route
  ```
  Run `python -m proconvert convert --help` for the options (page range, password, OCR, quality).

## Safety by design
Input files are never modified; an existing output file is never overwritten without confirmation; every conversion has
explicit limits (file size, pages, time) and runs in a separate process so a broken file cannot crash the app; the app makes
no network requests and collects no data. See [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md) and
[docs/PRIVACY.md](docs/PRIVACY.md).

## Known limitations (read before relying on it)
The honest list lives in [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md). Highlights: scanned PDFs need OCR; tables in pictures are
read with OCR and can contain mistakes (and fail on photos taken at an angle); the experimental routes rebuild structure by
guessing; Windows is the only supported platform.

## Develop
```bash
python -m pip install -r requirements/dev.txt -r requirements/gui.txt
python tools/run_tests.py       # full test-suite, rewrites docs/TEST_REPORT.md
```
Layout: `proconvert/` (`core`, `converters`, `pdftools`, `workers`, `services`, `settings`, `history`, `localization`, `ui`) ·
`tests/` · `tools/` · `packaging/` · `docs/` · `requirements/`. Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
Build a Windows executable: [docs/BUILD_GUIDE.md](docs/BUILD_GUIDE.md).

## Contribute
Bug reports, translations, test documents and code are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md). Security problems:
[SECURITY.md](SECURITY.md). Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md).

## License
[MIT](LICENSE) © 2026 LUQ-07. The libraries the program uses keep their own licenses; they are listed in
[LICENSES.md](LICENSES.md).
