# Fidelity report: PDF -> Word / PowerPoint (real-document evaluation)

Measured with `tools/score_fidelity.py` (text only: word recall = source words found in the output, precision = output
words that exist in the source, running headers/footers and page numbers ignored on both sides) plus visual inspection
of the result rendered through LibreOffice. Numbers below were produced by the code in this repository; nothing is estimated.

## Documents used
1. **A real 67-page French course handout** (cover with picture, running header, page numbers, headings, bullets drawn with
   Wingdings glyphs, indented unmarked sub-lists). The file itself is NOT in the repository.
2. **A real 46-slide presentation with 33 pictures**, used for PowerPoint -> PDF / Word / Excel and,
   after being converted to PDF, as a second PDF input.
3. A synthetic course handout generated in `tests/test_pdf_course_regression.py` (kept in the repository as a regression test).

## PDF -> Word, document 1
| | Before this work | After |
|---|---|---|
| Running header "Maladies Transmissibles IP2" | repeated as a paragraph on every page | moved to the Word header |
| Page numbers | 66 stray one-number paragraphs | removed |
| Wingdings bullets / arrows (U+F0xx) | became boxes or "?" | real bullets / arrows |
| Indented sub-items ("Hyperthermie", "Frisson"...) | glued into one long paragraph | one nested list item each |
| Word recall / precision | not measured | **99.88 % / 99.98 %** |
| Output | 47 Word pages (text reflowed) | 46 Word pages; 223 headings, 938 list items, 2 pictures |

## PDF -> PowerPoint, document 1
| | Before | After |
|---|---|---|
| Slides for 67 PDF pages | 174 | 108 |
| Empty slides / slides titled "Page N" | many | none (regression-tested) |
| Header "Maladies Transmissibles IP2" | text box on every page | small footer on each slide |
| Word recall / precision | not measured | **99.88 % / 99.97 %** |

## Second PDF (cancer deck exported to PDF by this program, then converted back)
Recall measured at 92.9 % only because the scorer counted 112 `(cid:NN)` glyph placeholders of the PDF text layer as words;
after excluding them the same comparison shows no lost words. 33 pictures were carried over.

## PowerPoint -> PDF / Word (document 2): works (already Supported)
46 PDF pages (one per slide, pictures kept), Word with slide titles as headings, bullets and 33 pictures; text with a
Wingdings arrow no longer produces "?" in the PDF.

## Decision
* **PDF -> Word: promoted to Supported** for PDFs that have a text layer. Reasons: measured text fidelity above 99.8 % on a
  real 67-page document, correct structure (headings, nested lists, header/footer), regression tests.
* **PDF -> PowerPoint: stays Experimental.** The text is complete, but slides are generated automatically with a plain layout
  (text-dense, no design), exactly like Word -> PowerPoint, which is also Experimental. Promoting one without the other would
  be inconsistent.
* Not covered by this evidence (still true for the "Supported" PDF -> Word route): scanned PDFs (need OCR), borderless
  space-aligned tables (come through as text), three-plus columns, rotated text, vector charts, Arabic/Hebrew shaping.
  Only ONE real PDF was evaluated; more real documents may reveal new cases.
