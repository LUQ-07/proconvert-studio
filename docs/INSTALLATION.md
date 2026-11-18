# Installation guide

> **Scope change:** the product now targets **Windows only** (Microsoft Store). Any macOS/Linux section below is legacy and no longer built, tested or shipped.


> Installers are produced by the scripts in `packaging/` (`docs/BUILD_GUIDE.md`). They have **not yet been built or tested** - the steps below describe the intended experience.

## Windows 10/11 (64-bit)
Run `ProConvertStudio-<version>-setup.exe`. Choose per-user (no admin rights) or all-users install; the *desktop shortcut* is optional. Start from **Start Menu > ProConvert Studio**.
An unsigned installer shows a SmartScreen warning ("More info" > "Run anyway"); signed releases reduce but do not guarantee this.
**Uninstall:** Settings > Apps > ProConvert Studio. Your settings/history stay in `%APPDATA%\ProConvertStudio` and `%LOCALAPPDATA%\ProConvertStudio`; delete them for a full wipe.

## macOS 11+ (Apple Silicon or Intel)
Open the `.dmg`, drag **ProConvert Studio** to *Applications*. Unsigned/un-notarized builds are blocked by Gatekeeper (right-click > Open, or System Settings > Privacy & Security > Open Anyway). Choose the DMG that matches your Mac (arm64/x86_64) unless a universal build is offered.
**Uninstall:** drag the app to the Trash; remove `~/Library/Application Support/ProConvertStudio` and `~/Library/Caches/ProConvertStudio`.

## Linux (Ubuntu, Debian, Kali and derivatives)
`.deb`: `sudo apt install ./proconvert-studio_<version>_amd64.deb` (pulls the Qt/XCB libraries it needs, e.g. `libxcb-cursor0`). Launch from the applications menu or `proconvert-studio`.
AppImage: `chmod +x ProConvertStudio-*.AppImage && ./ProConvertStudio-*.AppImage` (needs `libfuse2`, or run with `--appimage-extract-and-run`).
**Uninstall:** `sudo apt remove proconvert-studio` / delete the AppImage; data in `~/.config/ProConvertStudio`, `~/.local/share/ProConvertStudio`, `~/.cache/ProConvertStudio`.
Optional OCR: `sudo apt install tesseract-ocr`.

## From source (developers)
See the README. Requires Python 3.11+.
