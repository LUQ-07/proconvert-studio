# Build guide

> **Scope change:** the product now targets **Windows only** (Microsoft Store). Any macOS/Linux section below is legacy and no longer built, tested or shipped.


**Honest status:** the build scripts were written on Linux without PySide6 or PyInstaller. Mechanics that *could* be checked (syntax, plist/TOML/desktop-file validity, the `.deb` assembly with a dummy payload) are covered by `tests/test_packaging.py`. **No real binary has been built.** Run each script on its target OS and tick `RELEASE_CHECKLIST.md`.

## Common
Python 3.11, a fresh venv, `pip install -r requirements/build.txt`. Build on each OS natively (PyInstaller does not cross-compile). Then `python packaging/verify_build.py <frozen exe>`: it runs the built-in self-test of all 12 routes *inside the frozen app*, proving every library, font and data file was bundled. It does not prove the GUI starts - also launch the app by hand.
Pin and audit: `pip freeze > requirements-lock.txt`, `pip-audit -r requirements-lock.txt`, `pip-licenses`, `python tools/gen_notices.py`.

## Windows
`powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1` -> `dist\ProConvertStudio\` + `dist\installer\ProConvertStudio-<ver>-setup.exe` (needs Inno Setup 6). Includes version resource, Start Menu entry, optional desktop shortcut, uninstaller.
**Signing:** buy a code-signing certificate (EV or OV; HSM/cloud-token rules apply), set `SIGN_THUMBPRINT`; the script signs the exe and installer with SHA-256 and a timestamp. SmartScreen reputation builds over time even when signed - there is no guarantee of immediate silence.

## macOS
`./packaging/macos/build.sh` (`ARCH=arm64|x86_64`; universal2 only if all wheels are universal2). Produces `dist/ProConvert Studio.app` and `dist/ProConvertStudio-<ver>-macos-<arch>.dmg`.
**Sign + notarize:** Apple Developer Program membership, a *Developer ID Application* certificate; `export CODESIGN_IDENTITY="Developer ID Application: Name (TEAMID)"`; once: `xcrun notarytool store-credentials pc-notary --apple-id <id> --team-id <team> --password <app-specific-password>`; `export NOTARY_PROFILE=pc-notary`. The script signs inside-out with the hardened runtime and `entitlements.plist` (remove entitlements that testing shows are unnecessary), submits to `notarytool`, and staples. Verify with `spctl --assess` on a clean Mac.

## Linux
`./packaging/linux/build.sh` -> `dist/proconvert-studio_<ver>_amd64.deb` and, if `appimagetool` exists, `dist/ProConvertStudio-<ver>-<arch>.AppImage`. Build on the oldest distro you support (glibc). Test on clean Ubuntu LTS, Debian stable and Kali; the `.deb` declares the Qt/XCB libraries it needs. Linux has no code-signing gate; publish SHA-256 sums (and optionally a GPG signature) next to downloads.

## Size and startup
One-folder builds start faster than one-file and keep Qt libraries replaceable (LGPL). Unused Qt modules are excluded in the spec.
