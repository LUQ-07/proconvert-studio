# User guide

**Privacy in one line:** your files are converted on your computer and are never uploaded.

## Convert one file
1. **Convert** (Ctrl+2) or pick a card on the Dashboard.
2. Drop a file on the zone or press *Browse*. The app checks the file; if it is a different type than the selected converter it switches for you.
3. Choose **Convert to**. Routes marked *experimental* show a notice: the result is rebuilt and needs review.
4. For PDFs you may enter pages (e.g. `1-3,7`) and tick OCR for scanned pages (needs Tesseract installed).
5. Pick the folder and file name, press **Convert** (Ctrl+Enter). A progress bar shows the real stage; unmeasurable stages show a busy animation. **Cancel** stops immediately; no partial file is left.
6. When finished: *Open file*, *Show in folder*, or convert another. Notes list anything not carried over (e.g. "2 text boxes are not converted").
Password-protected PDF: the app asks for the password. Office files: remove the password first.

## Batch
Add many files (or drop them), choose one output format and optionally a folder, **Start**. Each file is separate: one failure never stops the rest. *Cancel pending*, *Retry failed*. Existing files are never overwritten in batch mode (a number is appended).

## History
Search, filter, sort, open the result, retry a conversion, export CSV, clear. Only names, paths, formats, times and results are stored - never document content.

## Settings
General (output folder, overwrite prompt, language, appearance), Conversion (image quality, OCR, column detection, header/footer removal, concurrent jobs), Privacy (clear history/temp, local crash reports - off by default), Advanced (log level, temp folder, diagnostics export, system info).
Languages other than English are **draft translations** and are labelled as such.

## What to expect
Layout is rebuilt, not copied: fonts, exact positions, headers/footers, text boxes, comments and macros are not carried over. Tables, headings, lists, bold/italic and pictures are. Read `COMPATIBILITY_MATRIX.md` for each route.

## Where data lives
Windows `%APPDATA%\ProConvertStudio` (settings), `%LOCALAPPDATA%\ProConvertStudio` (history, logs); macOS `~/Library/Application Support/ProConvertStudio`; Linux `~/.config` / `~/.local/share` / `~/.cache` + `/ProConvertStudio`.
