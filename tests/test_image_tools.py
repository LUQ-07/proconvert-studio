"""Image -> PDF / DOCX engine."""
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import pypdf
from docx import Document
from PIL import Image

from proconvert.converters.image_tools import (ImageLayout, check_image_file, convert_images, image_info,
                                               make_thumbnail, place)
from proconvert.core.context import CancelToken
from proconvert.core.errors import (CancelledError, InvalidFileError, InvalidOptionsError, OutputExistsError,
                                    OutputPathError, ResourceLimitError)


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.d = Path(self._t.name)

    def tearDown(self):
        self._t.cleanup()

    def img(self, name, size=(400, 200), color=(200, 30, 30), mode="RGB", **save):
        p = self.d / name
        Image.new(mode, size, color).save(p, **save)
        return p

    def pdf_pages(self, path):
        r = pypdf.PdfReader(str(path))
        return [(round(float(p.mediabox.width)), round(float(p.mediabox.height))) for p in r.pages]


class PdfOutput(Base):
    def test_all_formats_one_image_per_page_in_given_order(self):
        tiff = self.d / "e.tiff"
        frames = [Image.new("RGB", (200, 300), (i * 50, 0, 0)) for i in range(3)]
        frames[0].save(tiff, save_all=True, append_images=frames[1:])
        imgs = [self.img("a.jpg", (800, 400)), self.img("b.png", (300, 600)), self.img("c.bmp", (100, 100)),
                self.img("d.webp", (64, 64)), tiff]
        res = convert_images(imgs, self.d / "o.pdf", "pdf")
        self.assertEqual(7, res.pages)                      # 4 single images + 3 TIFF frames
        self.assertEqual(7, len(self.pdf_pages(res.output_path)))

    def test_order_is_respected(self):
        wide, tall = self.img("w.png", (800, 200)), self.img("t.png", (200, 800))
        a = self.pdf_pages(convert_images([wide, tall], self.d / "1.pdf", "pdf").output_path)
        b = self.pdf_pages(convert_images([tall, wide], self.d / "2.pdf", "pdf").output_path)
        self.assertEqual(a[0], b[1])
        self.assertEqual(a[1], b[0])
        self.assertGreater(a[0][0], a[0][1])               # wide image -> landscape page in auto mode

    def test_jpeg_is_embedded_unchanged_and_others_losslessly(self):
        jpg = self.img("a.jpg", (640, 480), quality=90)
        png = Image.new("RGB", (64, 48))
        png.putdata([(x * 4 % 256, y * 5 % 256, (x + y) % 256) for y in range(48) for x in range(64)])
        png_path = self.d / "b.png"
        png.save(png_path)
        out = convert_images([jpg, png_path], self.d / "o.pdf", "pdf").output_path
        pages = pypdf.PdfReader(str(out)).pages
        xobj = pages[0]["/Resources"]["/XObject"]
        stream = next(iter(xobj.values())).get_object()
        self.assertIn("/DCTDecode", [str(f) for f in stream["/Filter"]], "JPEG must stay DCT encoded")
        jpeg_stream = stream.get_data()
        self.assertTrue(jpeg_stream == jpg.read_bytes(), "the original JPEG data must be embedded, not re-compressed")
        with Image.open(io.BytesIO(pages[1].images[0].data)) as back:
            self.assertEqual(png.size, back.size)
            self.assertTrue(list(back.convert("RGB").getdata()) == list(png.getdata()), "non-JPEG images must be lossless")

    def test_no_distortion_aspect_ratio_kept(self):
        for size in ((900, 300), (300, 900), (500, 500)):
            for ps in ("A4", "Letter", "Fit"):
                for orient in ("auto", "portrait", "landscape"):
                    pw, ph, x, y, w, h = place(size[0], size[1], 96.0, ImageLayout(page_size=ps, orientation=orient, margin_mm=12))
                    self.assertAlmostEqual(size[0] / size[1], w / h, places=6, msg=(size, ps, orient))
                    self.assertGreaterEqual(x, 0)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(x + w, pw + 1e-6)
                    self.assertLessEqual(y + h, ph + 1e-6)

    def test_page_sizes_orientation_and_fit(self):
        wide = self.img("w.png", (800, 400))
        a4 = self.pdf_pages(convert_images([wide], self.d / "a4.pdf", "pdf", ImageLayout("A4", "portrait")).output_path)[0]
        self.assertEqual((595, 842), a4)
        let = self.pdf_pages(convert_images([wide], self.d / "l.pdf", "pdf", ImageLayout("Letter", "landscape")).output_path)[0]
        self.assertEqual((792, 612), let)
        fit = self.pdf_pages(convert_images([wide], self.d / "f.pdf", "pdf", ImageLayout("Fit", margin_mm=0)).output_path)[0]
        self.assertEqual(round(800 * 72 / 96), fit[0])     # no dpi in file -> 96 dpi assumed
        self.assertEqual(round(400 * 72 / 96), fit[1])

    def test_margins_and_no_upscale(self):
        small = (100, 100)
        _, _, _, _, w_up, _ = place(*small, 96.0, ImageLayout("A4", margin_mm=10))
        _, _, _, _, w_no, _ = place(*small, 96.0, ImageLayout("A4", margin_mm=10, allow_upscale=False))
        self.assertGreater(w_up, w_no)
        self.assertAlmostEqual(100 * 72 / 96, w_no)
        with self.assertRaises(InvalidOptionsError):
            place(100, 100, 96.0, ImageLayout("A4", margin_mm=60))
        with self.assertRaises(InvalidOptionsError):
            convert_images([self.img("a.png")], self.d / "x.pdf", "pdf", ImageLayout("A4", margin_mm=-1))

    def test_position_center_vs_top(self):
        _, _, _, y_c, _, h = place(800, 200, 96.0, ImageLayout("A4", "portrait", 10, "center"))
        _, _, _, y_t, _, _ = place(800, 200, 96.0, ImageLayout("A4", "portrait", 10, "top"))
        self.assertGreater(y_c, y_t)
        self.assertAlmostEqual(10 * 72 / 25.4, y_t)

    def test_transparency_and_exif_rotation(self):
        rgba = self.d / "t.png"
        Image.new("RGBA", (200, 100), (0, 0, 255, 0)).save(rgba)         # fully transparent
        res = convert_images([rgba], self.d / "t.pdf", "pdf")
        self.assertTrue(any("transparency" in w for w in res.warnings))
        jpg = self.d / "r.jpg"
        im = Image.new("RGB", (400, 200), (10, 200, 10))
        exif = im.getexif()
        exif[0x0112] = 6                                                  # rotate 90 CW when displayed
        im.save(jpg, exif=exif)
        res2 = convert_images([jpg], self.d / "r.pdf", "pdf", ImageLayout("A4", "auto"))
        w, h = self.pdf_pages(res2.output_path)[0]
        self.assertGreater(h, w, "after the EXIF rotation the picture is portrait, so the page must be portrait")


class DocxOutput(Base):
    def test_one_section_and_picture_per_image(self):
        imgs = [self.img("a.jpg", (800, 400)), self.img("b.png", (300, 600)), self.img("c.bmp", (100, 100))]
        res = convert_images(imgs, self.d / "o.docx", "docx", ImageLayout("A4", "auto", 12))
        doc = Document(str(res.output_path))
        self.assertEqual(3, len(doc.sections))
        self.assertEqual(3, len(doc.inline_shapes))
        self.assertGreater(doc.sections[0].page_width, doc.sections[0].page_height)    # wide -> landscape
        self.assertGreater(doc.sections[1].page_height, doc.sections[1].page_width)
        for shape in doc.inline_shapes:
            self.assertGreater(shape.width, 0)
            self.assertGreater(shape.height, 0)

    def test_picture_keeps_aspect_ratio_and_original_bytes(self):
        jpg = self.img("a.jpg", (900, 300), quality=90)
        doc = Document(str(convert_images([jpg], self.d / "o.docx", "docx").output_path))
        s = doc.inline_shapes[0]
        self.assertAlmostEqual(3.0, s.width / s.height, places=2)
        with open(self.d / "o.docx", "rb") as fh:
            import zipfile
            z = zipfile.ZipFile(fh)
            media = [n for n in z.namelist() if n.startswith("word/media/")]
            self.assertEqual(jpg.read_bytes(), z.read(media[0]))

    @unittest.skipUnless(shutil.which("soffice"), "LibreOffice not installed")
    def test_rendered_page_count_matches_image_count(self):
        imgs = [self.img("a.jpg", (1600, 900)), self.img("b.png", (900, 1600)), self.img("c.bmp", (500, 500))]
        docx = convert_images(imgs, self.d / "r.docx", "docx", ImageLayout("A4", "auto", 10)).output_path
        r = subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(self.d), str(docx)],
                           capture_output=True, text=True, timeout=180,
                           env=dict(os.environ, HOME=str(self.d)))
        self.assertEqual(0, r.returncode, r.stderr)
        pdf_pages = self.pdf_pages(self.d / "r.pdf")
        self.assertEqual(3, len(pdf_pages), "every image must land on its own page (no overflow)")
        self.assertGreater(pdf_pages[0][0], pdf_pages[0][1])


class Safety(Base):
    def test_existing_output_not_overwritten_without_consent(self):
        src = self.img("a.png")
        out = self.d / "o.pdf"
        convert_images([src], out, "pdf")
        first = out.read_bytes()
        with self.assertRaises(OutputExistsError):
            convert_images([src], out, "pdf")
        self.assertEqual(first, out.read_bytes())
        convert_images([src, src], out, "pdf", overwrite=True)
        self.assertEqual(2, len(pypdf.PdfReader(str(out)).pages))

    def test_sources_unchanged_and_no_temp_files(self):
        src = self.img("a.jpg", quality=90)
        before = src.read_bytes()
        convert_images([src], self.d / "o.pdf", "pdf")
        convert_images([src], self.d / "o.docx", "docx")
        self.assertEqual(before, src.read_bytes())
        self.assertEqual([], [p.name for p in self.d.iterdir() if p.name.startswith(".pdftool-")])

    def test_bad_inputs_are_friendly_errors(self):
        txt = self.d / "x.png"
        txt.write_text("not an image")
        with self.assertRaises(InvalidFileError):
            convert_images([txt], self.d / "o.pdf", "pdf")
        gif = self.img("a.gif", (10, 10), mode="P")
        with self.assertRaises(InvalidFileError):
            convert_images([gif], self.d / "o.pdf", "pdf")                # GIF is not in the supported list
        with self.assertRaises(InvalidFileError):
            check_image_file(self.d / "missing.png")
        empty = self.d / "e.png"
        empty.write_bytes(b"")
        with self.assertRaises(InvalidFileError):
            check_image_file(empty)
        with self.assertRaises(InvalidOptionsError):
            convert_images([], self.d / "o.pdf", "pdf")
        with self.assertRaises(InvalidOptionsError):
            convert_images([self.img("ok.png")], self.d / "o.pdf", "odt")
        with self.assertRaises(OutputPathError):
            convert_images([self.img("ok2.png")], self.d / "nofolder" / "o.pdf", "pdf")
        with self.assertRaises(OutputPathError):
            convert_images([self.img("ok3.png")], self.d / "o.docx", "pdf")        # extension must match format
        self.assertEqual([], list(self.d.glob("o.*")))

    def test_corrupt_image_in_the_middle_leaves_no_output(self):
        good = self.img("g.png")
        bad = self.d / "b.png"
        bad.write_bytes(good.read_bytes()[:60])                                   # truncated PNG
        with self.assertRaises(InvalidFileError):
            convert_images([good, bad], self.d / "o.pdf", "pdf")
        self.assertFalse((self.d / "o.pdf").exists())

    def test_pixel_limit(self):
        import proconvert.converters.image_tools as T
        old = T.MAX_PIXELS
        T.MAX_PIXELS = 1000
        try:
            with self.assertRaises((ResourceLimitError, InvalidFileError)):
                convert_images([self.img("big.png", (100, 100))], self.d / "o.pdf", "pdf")
        finally:
            T.MAX_PIXELS = old
        self.assertFalse((self.d / "o.pdf").exists())

    def test_cancel_leaves_nothing_behind(self):
        tok = CancelToken()
        imgs = [self.img(f"{i}.png") for i in range(5)]
        seen = []

        def progress(frac, text):
            seen.append(frac)
            if len(seen) == 3:
                tok.cancel()
        with self.assertRaises(CancelledError):
            convert_images(imgs, self.d / "o.pdf", "pdf", cancel=tok, progress=progress)
        self.assertFalse((self.d / "o.pdf").exists())
        self.assertEqual([], [p.name for p in self.d.iterdir() if p.name.startswith(".pdftool-")])

    def test_progress_is_monotonic_and_ends_at_one(self):
        seen = []
        convert_images([self.img(f"{i}.png") for i in range(4)], self.d / "o.pdf", "pdf", progress=lambda f, t: seen.append(f))
        self.assertEqual(sorted(seen), seen)
        self.assertEqual(1.0, seen[-1])

    def test_unicode_and_spaces_in_names(self):
        p = self.d / "صورة été 1.png"
        Image.new("RGB", (50, 50), (1, 2, 3)).save(p)
        res = convert_images([p], self.d / "Sortie été مرحبا.pdf", "pdf")
        self.assertTrue(res.output_path.is_file())


class Preview(Base):
    def test_thumbnail_and_info(self):
        p = self.img("a.jpg", (1600, 800))
        png = make_thumbnail(p, 160)
        with Image.open(io.BytesIO(png)) as t:
            self.assertLessEqual(max(t.size), 160)
            self.assertAlmostEqual(2.0, t.width / t.height, places=1)
        self.assertEqual({"width": 1600, "height": 800, "format": "JPEG", "frames": 1}, image_info(p))
        with self.assertRaises(InvalidOptionsError):
            make_thumbnail(p, 4)
        bad = self.d / "bad.png"
        bad.write_text("x")
        with self.assertRaises(InvalidFileError):
            make_thumbnail(bad)


if __name__ == "__main__":
    unittest.main()
