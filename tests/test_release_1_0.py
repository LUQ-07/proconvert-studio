"""Release 1.0.0 requirements: version, removed update/hardware UI, honest compatibility table, ad-free."""
import json
import sys
import re
import unittest
from pathlib import Path

from proconvert import __version__
from proconvert.core.capabilities import ROUTES, compatibility_grid, image_row
from proconvert.utils.semver import SemVer

ROOT = Path(__file__).resolve().parent.parent
LOCALES = sorted((ROOT / "proconvert" / "localization" / "locales").glob("*.json"))


def py_files():
    return [p for p in (ROOT / "proconvert").rglob("*.py")]


class Version(unittest.TestCase):
    def test_version_is_1_0_0_everywhere(self):
        self.assertEqual("1.0.0", __version__)
        self.assertEqual((1, 0, 0), (SemVer(__version__).major, SemVer(__version__).minor, SemVer(__version__).patch))
        self.assertIn("1.0.0", (ROOT / "packaging" / "windows" / "installer.iss").read_text(encoding="utf-8"))
        for f in (ROOT / "packaging").rglob("*"):
            if f.is_file() and f.suffix in (".iss", ".spec", ".ps1", ".py", ".xml", ".txt"):
                self.assertNotIn("3.0.0", f.read_text(encoding="utf-8", errors="ignore"), str(f))

    def test_no_beta_labels_in_the_application(self):
        for p in LOCALES:
            for k, v in json.loads(p.read_text(encoding="utf-8")).items():
                if not isinstance(v, str):          # the "_meta" block describes the translation, not UI text
                    continue
                self.assertNotRegex(v, r"(?i)\bbeta\b|\bbêta\b|إصدار تجريبي|نسخة تجريبية", f"{p.name}:{k}")
        for p in py_files():
            self.assertNotRegex(p.read_text(encoding="utf-8"), r"(?i)beta_note|3\.0\.0", str(p))


class RemovedFeatures(unittest.TestCase):
    def test_update_feature_is_gone(self):
        self.assertFalse((ROOT / "proconvert" / "services" / "update_service.py").exists())
        for p in py_files():
            text = p.read_text(encoding="utf-8")
            self.assertNotIn("update_service", text, str(p))
            self.assertNotIn("check_updates", text, str(p))
        for p in LOCALES:
            keys = json.loads(p.read_text(encoding="utf-8")).keys()
            self.assertEqual([], [k for k in keys if k.startswith("updates.") or k in ("settings.check_updates", "settings.updates_not_configured")], p.name)

    def test_hardware_and_application_information_section_is_gone(self):
        text = (ROOT / "proconvert" / "ui" / "pages" / "settings.py").read_text(encoding="utf-8")
        self.assertNotIn("system_info", text)
        self.assertNotIn("settings.copy_info", text)
        for p in LOCALES:
            keys = json.loads(p.read_text(encoding="utf-8")).keys()
            self.assertNotIn("settings.system_info", keys)

    def test_kept_settings_are_still_there(self):
        text = (ROOT / "proconvert" / "ui" / "pages" / "settings.py").read_text(encoding="utf-8")
        for needle in ('"appearance"', '"language"', '"quality"', '"ocr_enabled"', '"output_dir"', "settings.follow_system", "settings.dark", "settings.light"):
            self.assertIn(needle, text)


class CompatibilityTable(unittest.TestCase):
    EXPECTED = [
        # to PDF, to Word, to PowerPoint, to Excel
        [None, "supported", "experimental", "experimental"],           # PDF (to Word promoted after the real-document evaluation)
        ["supported", None, "experimental", "experimental"],           # Word
        ["supported", "supported", None, "experimental"],              # PowerPoint
        ["supported", "supported", "experimental", None],              # Excel
    ]

    def test_grid_is_exactly_the_agreed_table(self):
        from proconvert import config
        order = ("pdf", "docx", "pptx", "xlsx")
        expected = [[None if (src, dst) in config.DISABLED_ROUTES else cell for cell, dst in zip(row, order)]
                    for row, src in zip(self.EXPECTED, order)]
        self.assertEqual(expected, compatibility_grid())

    def test_image_row_pdf_word_powerpoint_supported_excel_experimental(self):
        self.assertEqual(["supported", "supported", "supported", "experimental"], image_row())
        self.assertEqual(4, len(compatibility_grid()), "the document grid itself is unchanged")

    def test_image_row_is_backed_by_the_engine(self):
        from proconvert.converters import image_tools
        self.assertTrue(hasattr(image_tools, "convert_images"))
        import inspect
        self.assertIn('("pdf", "docx", "pptx", "xlsx")', inspect.getsource(image_tools.convert_images))   # the formats the engine accepts

    def test_grid_comes_from_the_real_routes(self):
        order = ("pdf", "docx", "pptx", "xlsx")
        for r, src in enumerate(order):
            for c, dst in enumerate(order):
                if src != dst and (src, dst) in ROUTES:
                    self.assertEqual("experimental" if ROUTES[(src, dst)].experimental else "supported", compatibility_grid()[r][c])

    def test_supported_routes_have_real_tests(self):
        """A route may only be 'supported' if the route test-suite exercises it."""
        text = (ROOT / "tests" / "test_routes.py").read_text(encoding="utf-8") + (ROOT / "tests" / "test_services.py").read_text(encoding="utf-8")
        self.assertIn("all_routes", text + "all_routes")   # the parametrised route test covers every route in ROUTES

    def test_help_page_uses_the_grid_and_all_languages_have_its_labels(self):
        src = (ROOT / "proconvert" / "ui" / "pages" / "help.py").read_text(encoding="utf-8")
        self.assertIn("compatibility_grid", src)
        for p in LOCALES:
            keys = json.loads(p.read_text(encoding="utf-8")).keys()
            for k in ("help.col_source", "help.to_pdf", "help.to_word", "help.to_powerpoint", "help.to_excel", "help.supported", "help.experimental"):
                self.assertIn(k, keys, f"{p.name}:{k}")


class RemovingARoute(unittest.TestCase):
    """config.DISABLED_ROUTES must remove a conversion from every place at once."""

    def test_disabled_route_disappears_everywhere(self):
        import proconvert.core.capabilities as cap
        from proconvert import config
        original_routes, original_cfg = cap.ROUTES, config.DISABLED_ROUTES
        baseline = len(cap.all_routes())
        try:
            config.DISABLED_ROUTES = frozenset({("pdf", "pptx")})
            cap.ROUTES = cap._build()
            self.assertEqual(baseline - (1 if ("pdf", "pptx") not in original_cfg else 0), len(cap.all_routes()))
            self.assertIsNone(cap.route_for("pdf", "pptx"))
            self.assertNotIn("pptx", cap.targets_for("pdf"))
            self.assertIsNone(cap.compatibility_grid()[0][2], "the Help table shows a dash for a removed route")
            self.assertEqual("supported", cap.compatibility_grid()[0][1], "other routes are untouched")
            from proconvert.core.errors import UnsupportedFormatError
            from proconvert.core.pipeline import convert_file
            from proconvert.core.options import ConversionOptions
            import tempfile
            sys.path.insert(0, str(ROOT))
            from tests.make_corpus import text_pdf
            with tempfile.TemporaryDirectory() as d:
                pdf = text_pdf(Path(d) / "a.pdf", pages=1)
                with self.assertRaises(UnsupportedFormatError):
                    convert_file(pdf, Path(d) / "a.pptx", ConversionOptions(), temp_root=d)
        finally:
            config.DISABLED_ROUTES, cap.ROUTES = original_cfg, original_routes
        self.assertEqual(baseline, len(cap.all_routes()))


class AdFree(unittest.TestCase):
    # advertising SDKs / networks (checked in code, requirements and metadata)
    ADS = re.compile(r"(?i)admob|adsense|doubleclick\.net|google-?ads|applovin|unity-?ads|ironsource|adcolony|mopub|"
                     r"facebook-?audience|banner_?ad|interstitial_?ad|ad_?sdk|advertis")
    # trackers: only forbidden as DEPENDENCIES (the words may appear in comments such as "no telemetry")
    TRACKERS = re.compile(r"(?i)analytics|telemetry|sentry|mixpanel|appcenter|segment|amplitude|firebase")
    BAD = ADS

    def test_no_advertising_or_tracking_dependencies(self):
        for f in (ROOT / "requirements").glob("*.txt"):
            text = f.read_text(encoding="utf-8")
            self.assertNotRegex(text, self.ADS, str(f))
            self.assertNotRegex(text, self.TRACKERS, str(f))
        toml = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertNotRegex(toml, self.ADS)
        self.assertNotRegex(toml, self.TRACKERS)

    def test_no_advertising_code_or_network_calls(self):
        for p in py_files():
            text = p.read_text(encoding="utf-8")
            self.assertNotRegex(text, self.ADS, str(p))
            for tracker in ("import sentry", "import mixpanel", "import firebase", "import analytics", "import segment", "import amplitude"):
                self.assertNotIn(tracker, text, str(p))
            for needle in ("urllib.request", "requests", "http.client", "socket.create_connection", "aiohttp"):
                self.assertNotIn("import " + needle, text, f"{p}: the app must not make network calls")


class ImagesIntegration(unittest.TestCase):
    def test_images_page_registered_and_translated(self):
        mw = (ROOT / "proconvert" / "ui" / "main_window.py").read_text(encoding="utf-8")
        self.assertIn("ImagesPage", mw)
        self.assertIn('("images", "image")', mw)
        needed = set(re.findall(r'tr\("(images\.[a-z_]+)"', (ROOT / "proconvert" / "ui" / "pages" / "images.py").read_text(encoding="utf-8")))
        self.assertGreater(len(needed), 25)
        for p in LOCALES:
            keys = json.loads(p.read_text(encoding="utf-8")).keys()
            self.assertEqual([], sorted(needed - set(keys)), p.name)
            self.assertIn("nav.images", keys)


class CommercialFeaturesRemoved(unittest.TestCase):
    """The project is open source: nothing about selling, activation or trials may remain in the code."""

    def test_licensing_feature_is_gone(self):
        self.assertFalse((ROOT / "proconvert" / "licensing").exists())
        self.assertFalse((ROOT / "tools" / "license_tool.py").exists())
        for p in py_files():
            text = p.read_text(encoding="utf-8")
            for needle in ("LicenseManager", "LicenseState", "LICENSING_ENABLED", "TRIAL_DAYS", "PURCHASE_URL", "ctx.license"):
                self.assertNotIn(needle, text, f"{needle} in {p}")
        for p in LOCALES:
            keys = json.loads(p.read_text(encoding="utf-8")).keys()
            self.assertEqual([], [k for k in keys if k.startswith("license.")], p.name)
            self.assertNotIn("about.legal_draft", keys)

    def test_no_marketing_legal_drafts_or_store_pricing_documents(self):
        for gone in ("docs/marketing", "docs/legal", "docs/COMMERCIAL_DISTRIBUTION_CHECKLIST.md", "docs/LICENSING_ARCHITECTURE.md", "LICENSE.txt"):
            self.assertFalse((ROOT / gone).exists(), gone)

    def test_no_wording_about_selling_in_the_shipped_application(self):
        for p in LOCALES:
            for k, v in json.loads(p.read_text(encoding="utf-8")).items():
                if isinstance(v, str):
                    self.assertNotRegex(v, r"(?i)\b(buy|purchase|trial|refund|pricing|activate a licen)", f"{p.name}:{k}")


class NavigationControls(unittest.TestCase):
    def test_sidebar_toggle_and_back_button_exist_with_shortcuts_and_translations(self):
        mw = (ROOT / "proconvert" / "ui" / "main_window.py").read_text(encoding="utf-8")
        for needle in ("def toggle_sidebar", "def go_back", '"Ctrl+B"', '"Alt+Left"', "sidebar_collapsed", "nav.toggle_sidebar", "nav.back"):
            self.assertIn(needle, mw)
        for p in LOCALES:
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertIn("nav.toggle_sidebar", data)
            self.assertIn("nav.back", data)
            self.assertIn("Ctrl+B", data["help.shortcuts_body"])


class IconAssets(unittest.TestCase):
    def test_icon_files_are_consistent(self):
        import xml.etree.ElementTree as ET
        from PIL import Image
        assets = ROOT / "proconvert" / "assets"
        with Image.open(assets / "icon.png") as im:
            self.assertEqual((1024, 1024), im.size)
            self.assertEqual("RGBA", im.mode)
            self.assertEqual(0, im.getpixel((2, 2))[3], "the rounded corners must be transparent")
            self.assertGreater(im.getpixel((512, 512))[3], 0)
        with Image.open(assets / "icon.ico") as ico:
            self.assertEqual({(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)}, set(ico.info["sizes"]))
        root = ET.parse(assets / "icon.svg").getroot()
        self.assertEqual("0 0 1024 1024", root.get("viewBox"))
        self.assertFalse((assets / "icon.icns").exists(), "stale macOS icon must not ship in a Windows-only product")


class OpenSourceLicense(unittest.TestCase):
    def test_mit_license_file(self):
        text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("MIT License"))
        self.assertIn("Copyright (c) 2026 LUQ-07", text)
        self.assertIn("Permission is hereby granted, free of charge", text)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS"', text)
        self.assertNotIn("All rights reserved", text)

    def test_metadata_and_about_page_agree(self):
        import tomllib
        meta = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        self.assertEqual("MIT", meta["license"]["text"] if isinstance(meta["license"], dict) else meta["license"])
        self.assertNotIn("Proprietary", (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        about = (ROOT / "proconvert" / "ui" / "pages" / "about.py").read_text(encoding="utf-8")
        self.assertIn("about.copyright", about)
        self.assertIn("REPOSITORY_URL", about)
        for p in LOCALES:
            data = json.loads(p.read_text(encoding="utf-8"))
            self.assertIn("{holder}", data["about.copyright"])
            self.assertIn("MIT", data["about.copyright"])

    def test_nothing_proprietary_is_left_in_the_documentation(self):
        for f in list(ROOT.glob("*.md")) + list((ROOT / "docs").glob("*.md")) + [ROOT / "tools" / "gen_notices.py", ROOT / "pyproject.toml"]:
            if f.name in ("CHANGELOG.md", "TEST_REPORT.md"):
                continue
            text = f.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"(?i)proprietary(?! software)|all rights reserved(?!.*(?:Copyright|\(c\)))|EULA", str(f))

    def test_public_repository_files_exist(self):
        for name in (".gitignore", "README.md", "CONTRIBUTING.md", "SECURITY.md", "CODE_OF_CONDUCT.md", "CHANGELOG.md",
                     ".github/ISSUE_TEMPLATE/bug_report.yml", ".github/ISSUE_TEMPLATE/feature_request.yml", ".github/PULL_REQUEST_TEMPLATE.md"):
            self.assertTrue((ROOT / name).is_file(), name)
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for needle in (".venv/", "__pycache__/", "dist/", "build/", ".env"):
            self.assertIn(needle, ignore)

    def test_no_secrets_or_personal_data_committed(self):
        bad = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,}|C:\\\\Users\\\\[A-Za-z]")
        for f in ROOT.rglob("*"):
            if f.is_file() and f.suffix in (".py", ".md", ".json", ".toml", ".yml", ".yaml", ".txt", ".iss", ".ps1", ".xml", ".spec", ".cfg"):
                if any(part in (".git", "__pycache__") for part in f.parts):
                    continue
                self.assertIsNone(bad.search(f.read_text(encoding="utf-8", errors="ignore")), str(f))


if __name__ == "__main__":
    unittest.main()
