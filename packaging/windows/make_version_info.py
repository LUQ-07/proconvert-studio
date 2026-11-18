"""Write build/version_info.txt (Windows file-properties resource) from proconvert.__version__."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from proconvert import __version__, config  # noqa: E402

core = __version__.split("-")[0].split("+")[0]
a, b, c = (int(x) for x in core.split("."))
text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({a}, {b}, {c}, 0), prodvers=({a}, {b}, {c}, 0), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '{config.ORG_NAME}'),
      StringStruct('FileDescription', '{config.APP_NAME}'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'ProConvertStudio'),
      StringStruct('OriginalFilename', 'ProConvertStudio.exe'),
      StringStruct('ProductName', '{config.APP_NAME}'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
out = ROOT / "build" / "version_info.txt"
out.parent.mkdir(exist_ok=True)
out.write_text(text, encoding="utf-8")
print("wrote", out)
