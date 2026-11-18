"""Build-time constants. Nothing here is read from the network or from user-writable files."""

APP_NAME = "ProConvert Studio"
COPYRIGHT_HOLDER = "LUQ-07"
COPYRIGHT_YEAR = 2026
APP_ID = "proconvert-studio"
ORG_NAME = "ProConvert"
REPOSITORY_URL = "https://github.com/LUQ-07/prodoc-suite"      # where bugs are reported and the source lives

# Conversions that are NOT offered in this build, as (source, target) pairs of "pdf" | "docx" | "pptx" | "xlsx".
# A disabled route disappears everywhere at once: the Convert page, Batch, the Dashboard, the Help table (shown as a dash),
# the command line and the self-test. Example (remove PDF -> PowerPoint):  frozenset({("pdf", "pptx")})
DISABLED_ROUTES: frozenset[tuple[str, str]] = frozenset()
