"""Static checks of the MSIX packaging files. The package itself has NOT been built or installed yet."""
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
MSIX = ROOT / "packaging" / "windows" / "msix"
NS = {"m": "http://schemas.microsoft.com/appx/manifest/foundation/windows10",
      "uap": "http://schemas.microsoft.com/appx/manifest/uap/windows10",
      "rescap": "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"}


def manifest_text(**over):
    values = {"IDENTITY_NAME": "Test.ProConvertStudio", "PUBLISHER": "CN=Test", "PUBLISHER_DISPLAY_NAME": "Test", "VERSION": "1.0.0.0"}
    values.update(over)
    text = (MSIX / "AppxManifest.xml").read_text(encoding="utf-8")
    for k, v in values.items():
        text = text.replace(f"@{k}@", v)
    return text


class Manifest(unittest.TestCase):
    def test_well_formed_and_all_placeholders_known(self):
        raw = (MSIX / "AppxManifest.xml").read_text(encoding="utf-8")
        self.assertEqual({"IDENTITY_NAME", "PUBLISHER", "PUBLISHER_DISPLAY_NAME", "VERSION"}, set(re.findall(r"@([A-Z_]+)@", raw)))
        self.assertNotRegex(manifest_text(), r"@[A-Z_]+@")
        ET.fromstring(manifest_text())

    def test_identity_application_and_capabilities(self):
        root = ET.fromstring(manifest_text())
        ident = root.find("m:Identity", NS)
        self.assertEqual("x64", ident.get("ProcessorArchitecture"))
        app = root.find("m:Applications/m:Application", NS)
        self.assertEqual("ProConvertStudio.exe", app.get("Executable"))
        self.assertEqual("Windows.FullTrustApplication", app.get("EntryPoint"))
        caps = [c.get("Name") for c in root.findall("m:Capabilities/rescap:Capability", NS)]
        self.assertEqual(["runFullTrust"], caps, "no network/file-system capabilities are requested: the app is offline")
        self.assertEqual([], root.findall("m:Capabilities/m:Capability", NS))
        dev = root.find("m:Dependencies/m:TargetDeviceFamily", NS)
        self.assertEqual("Windows.Desktop", dev.get("Name"))
        self.assertEqual("10.0.17763.0", dev.get("MinVersion"))            # Windows 10 1809 and later, including Windows 11

    def test_every_referenced_asset_exists_with_the_right_size(self):
        text = manifest_text()
        refs = set(re.findall(r'Assets\\([A-Za-z0-9_.\-]+\.png)', text))
        self.assertGreaterEqual(len(refs), 5)
        want = {"StoreLogo.png": (50, 50), "Square44x44Logo.png": (44, 44), "Square150x150Logo.png": (150, 150),
                "Wide310x150Logo.png": (310, 150), "Square310x310Logo.png": (310, 310), "SmallTile.png": (71, 71)}
        for name in refs:
            path = MSIX / "Assets" / name
            self.assertTrue(path.is_file(), name)
            with Image.open(path) as im:
                self.assertEqual(want[name], im.size, name)

    def test_languages_match_the_application(self):
        langs = {r.get("Language") for r in ET.fromstring(manifest_text()).findall("m:Resources/m:Resource", NS)}
        self.assertEqual({"en-us", "fr-fr", "es-es", "ar-sa"}, langs)

    def test_build_script_refuses_unreplaced_placeholders_and_bad_versions(self):
        s = (MSIX / "build_msix.ps1").read_text(encoding="utf-8")
        for needle in ("Unreplaced placeholder", "MAJOR.MINOR.PATCH", "makeappx", "ErrorActionPreference"):
            self.assertIn(needle, s)
        self.assertNotIn("signtool sign", s.lower().replace("signtool.exe for local", ""))   # the script never signs: the Store does

    def test_no_network_capabilities_requested(self):
        text = (MSIX / "AppxManifest.xml").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"(?i)internetClient|privateNetworkClient|internetClientServer")


if __name__ == "__main__":
    unittest.main()
