# Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| "The file is protected with a password" | Encrypted PDF/Office file | PDF: enter the password when asked. Office: remove it in Word/PowerPoint/Excel, save a copy. |
| "No convertible content was found" | Empty file, or scanned PDF | Enable OCR (install Tesseract) or accept that pages are inserted as images. |
| "damaged or not what its extension says" | Corrupt/renamed/truncated file | Re-save from the original app or re-download. |
| ".doc/.ppt/.xls not supported" | Legacy format | Open it in Office/LibreOffice and save as .docx/.pptx/.xlsx. |
| "possible ZIP bomb" / "disallowed XML declaration" | Safety rule triggered | Only convert files from trusted sources; re-save the file. |
| "File is larger than the safe limit" | >250 MB or too many pages/rows | Split the file or use a page range. |
| Text looks different, fonts changed | Layout is rebuilt, not copied | Expected; see the compatibility matrix. |
| CJK shows as `?`, Arabic looks reversed in PDF output | Built-in PDF font coverage; no RTL shaping | Choose DOCX/PPTX/XLSX output instead; on the roadmap. |
| Formulas missing in Excel results (cells empty) | Workbook never calculated | Open and save it once in Excel/LibreOffice. |
| Conversion "stopped unexpectedly" | Parser crashed on a malformed file (contained in the worker) | Re-save the file; send a diagnostics export. |
| Linux: app won't start, `xcb` plugin error | Missing system libraries | `sudo apt install libxcb-cursor0 libegl1 libxkbcommon-x11-0` |
| macOS: "cannot be opened because the developer cannot be verified" | Unsigned/un-notarized build | Right-click > Open; use a notarized release. |
| Windows: SmartScreen warning | Unsigned installer/low reputation | "More info" > "Run anyway" only if downloaded from the official source. |
Still stuck: Settings > Advanced > *Export diagnostics* and send it to support (it contains no document content).
