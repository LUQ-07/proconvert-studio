# FAQ
**Does it upload my files?** No. Processing is local; there is no telemetry. The application makes no network requests at all; updates come through the Microsoft Store.
**Do I need Word, Excel, PowerPoint or LibreOffice?** No.
**Will the output look identical to the original?** No. Content (text, tables, images, headings, lists) is carried over; layout is rebuilt. See the compatibility matrix.
**Why are some conversions "experimental"?** They reconstruct structure the source does not contain (e.g. PDF -> Excel or Word -> PowerPoint). Always check them.
**Can it read scanned PDFs?** Pages are inserted as images by default; with a Tesseract install and OCR enabled it recognizes text (no table detection).
**Arabic/Hebrew/Chinese in PDF output?** Not reliably in this version (see Troubleshooting).
**Is it free?** Yes. ProConvert Studio is free and open source under the MIT license: no trial, no activation, no ads.
**Which languages?** English is complete. French, Spanish, Arabic are complete drafts not yet reviewed by native speakers and are labelled so.
**Is it safe to open files from strangers?** It is built defensively (limits, isolation, bans on risky XML) but no parser is risk-free; see `SECURITY_MODEL.md`.
**Can I script it?** `proconvert convert in out` (CLI).
