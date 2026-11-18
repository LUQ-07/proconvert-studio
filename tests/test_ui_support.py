"""Qt-free tests of the UI support layer: translations, palette contrast, string coverage."""
import json
import re
import sys
import unittest
from pathlib import Path

from proconvert.localization import Translator, available_languages, is_rtl
from proconvert.localization.translator import load_catalog, locales_dir
from proconvert.ui.palette import DARK, LIGHT, contrast_ratio

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from check_strings import candidate_keys, used_keys  # noqa: E402

PLACEHOLDER = re.compile(r"\{(\w+)\}")


class Translations(unittest.TestCase):
    def setUp(self):
        self.en = load_catalog("en")

    def test_english_covers_every_key_the_ui_uses(self):
        missing = sorted(k for k in used_keys() if k not in self.en)
        self.assertEqual([], missing)

    def test_english_has_no_unused_keys(self):
        unused = sorted(k for k in self.en if not k.startswith("_") and k not in candidate_keys())
        self.assertEqual([], unused, "dead strings should be removed")

    def test_every_language_has_identical_keys_and_placeholders(self):
        keys = {k for k in self.en if not k.startswith("_")}
        for p in sorted(locales_dir().glob("*.json")):
            if p.stem == "en":
                continue
            cat = json.loads(p.read_text(encoding="utf-8"))
            with self.subTest(lang=p.stem):
                self.assertEqual(set(), keys - set(cat), "missing translations")
                self.assertEqual(set(), {k for k in cat if not k.startswith("_")} - keys, "unknown keys")
                for k in keys:
                    self.assertEqual(set(PLACEHOLDER.findall(self.en[k])), set(PLACEHOLDER.findall(cat[k])), f"{p.stem}:{k}")
                    self.assertTrue(cat[k].strip(), f"{p.stem}:{k} empty")

    def test_unreviewed_languages_are_labelled_honestly(self):
        langs = {l["code"]: l for l in available_languages()}
        self.assertTrue(langs["en"]["reviewed"] and langs["en"]["complete"])
        for code in ("fr", "es", "ar"):
            self.assertFalse(langs[code]["reviewed"], f"{code} must not be presented as reviewed")
            self.assertEqual(1.0, langs[code]["coverage"])

    def test_formatting_fallback_and_rtl(self):
        t = Translator("fr")
        self.assertIn("5", t("convert.notes", n=5))
        self.assertEqual("no.such.key", t("no.such.key"))
        self.assertEqual(Translator("en")("nav.convert"), Translator("xx")("nav.convert"), "unknown language falls back to English")
        self.assertTrue(is_rtl("ar") and not is_rtl("fr"))

    def test_settings_languages_match_available_catalogs(self):
        from proconvert.settings.store import CHOICES
        self.assertEqual(set(CHOICES["language"]), {l["code"] for l in available_languages()})


class Contrast(unittest.TestCase):
    PAIRS = [("text", "bg", 7), ("text", "surface", 7), ("text", "surface2", 7), ("muted", "bg", 4.5), ("muted", "surface", 4.5),
             ("muted", "surface2", 4.5), ("accent_text", "accent", 4.5), ("accent_text", "accent_hover", 4.5), ("accent", "surface", 4.5),
             ("accent", "bg", 4.5), ("success", "surface", 4.5), ("warning", "surface", 4.5), ("warning", "surface2", 4.5),
             ("danger", "surface", 4.5), ("focus", "surface", 3), ("badge_text", "badge_pdf", 4.5), ("badge_text", "badge_docx", 4.5),
             ("badge_text", "badge_pptx", 4.5), ("badge_text", "badge_xlsx", 4.5), ("badge_text", "badge_image", 4.5)]

    def test_wcag_aa_for_both_themes(self):
        for name, pal in (("dark", DARK), ("light", LIGHT)):
            for fg, bg, need in self.PAIRS:
                with self.subTest(theme=name, fg=fg, bg=bg):
                    self.assertGreaterEqual(contrast_ratio(pal[fg], pal[bg]), need)

    def test_known_reference_values(self):
        self.assertAlmostEqual(21.0, contrast_ratio("#000000", "#FFFFFF"), places=1)
        self.assertAlmostEqual(1.0, contrast_ratio("#777777", "#777777"), places=3)

    def test_themes_define_same_tokens(self):
        self.assertEqual(set(DARK), set(LIGHT))

    def test_qss_builds_for_both_themes_without_unresolved_tokens(self):
        from proconvert.ui.theme import build_qss
        for pal in (DARK, LIGHT):
            qss = build_qss(pal)
            self.assertNotIn("{p[", qss)
            self.assertGreater(qss.count("{"), 50)
            self.assertEqual(qss.count("{"), qss.count("}"))


if __name__ == "__main__":
    unittest.main()
