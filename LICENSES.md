# Third-party licenses (dependency inventory)

ProConvert Studio is free software released under the MIT License (see `LICENSE`). Components below keep their own licenses. Full license texts: `proconvert/assets/THIRD_PARTY_NOTICES.txt` (regenerate with `tools/gen_notices.py` in the release venv). **Verify every row against the exact pinned versions with `pip-licenses` before each release; the "declared" column was read from installed metadata on 2026-10-23, the PySide6/PyInstaller rows are from the projects' published terms and are unverified here.**

| Component | Used for | License (declared) | Redistribution notes |
|---|---|---|---|
| PySide6 / Qt 6 | GUI | LGPL-3.0 (GPL/commercial alternatives) - *not installed here, unverified* | OK with dynamic linking (one-folder build), ship license text + notices, allow replacing Qt libs, no tivoization; use only QtCore/QtGui/QtWidgets. **Get counsel sign-off.** Do not ship GPL-only Qt modules (Charts, Data Visualization): excluded in the spec. |
| pdfplumber 0.11.9 | PDF text/tables | MIT | Keep notice |
| pdfminer.six 20251230 | PDF parsing | MIT | Keep notice |
| pypdf (>=6.14.1; tested 5.9.0) | PDF structure, passwords, images | BSD-3-Clause | Keep notice |
| pypdfium2 5.6.0 (optional OCR) | PDF page rendering | BSD-3-Clause / Apache-2.0 (+ PDFium notices) | Ship bundled licenses |
| python-docx 1.2.0 | DOCX | MIT | |
| python-pptx 1.0.2 | PPTX | MIT | |
| openpyxl 3.1.5 (+ et_xmlfile) | XLSX | MIT | |
| ReportLab 4.4.10 | PDF output | BSD (open-source edition) | The commercial "ReportLab PLUS" products are separate; not used |
| Pillow 12.1.1 | Images | MIT-CMU (HPND) | |
| numpy >= 1.26 | Table detection in pictures | BSD-3-Clause | Check the exact wheel's bundled libraries (OpenBLAS: BSD) with pip-licenses before release |
| lxml 6.0.2 | XML | BSD-3-Clause (+ libxml2/libxslt MIT) | |
| cryptography 46.0.6 | AES PDFs, signatures | Apache-2.0 OR BSD-3-Clause (+ OpenSSL) | |
| defusedxml 0.7.1 | XML hardening | PSF-2.0 | |
| pytesseract 0.3.13 (optional) | OCR wrapper | Apache-2.0 | |
| Tesseract (optional, external) | OCR engine | Apache-2.0 | Only if you bundle it; ship its notices and language data licenses |
| DejaVu Sans (bundled fonts) | PDF output font | Bitstream Vera + public-domain additions (permissive; fonts must not be sold on their own) | License file bundled |
| PyInstaller (build only) | Packaging | GPL-2.0+ with bootloader exception | The exception lets programs built with it use any license, including this MIT one |
| Inno Setup (build only) | Windows installer | Inno Setup license (free incl. commercial) - unverified here | |

Not used: PyMuPDF (AGPL), Microsoft Office, LibreOffice.
