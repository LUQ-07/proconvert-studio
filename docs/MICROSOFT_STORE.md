# Microsoft Store: packaging and submission guide (ProConvert Studio 1.0.0)

**Honest status:** the MSIX manifest, build script, tile images and a CI smoke job are written and statically tested.
**No MSIX has been built, installed, certified or submitted yet** (the authoring environment had no Windows). Expect to
fix things the first time you run the steps below. Nothing here claims Store approval or code signing.

## What the Store handles for you
* **Updates:** the app has no update button or update checker; the Store delivers new versions.
* **Signing:** you do NOT need your own code-signing certificate for a Store submission - the Store signs the package
  after certification. (You only need a test certificate to install the package on your own PC before submitting.)

## One-time setup (browser)
1. Create a developer account at https://storedeveloper.microsoft.com (individual accounts were announced as free;
   an account for a registered business may carry a fee). Check the current terms and your country on that site.
   For a free open-source app an individual account is normally enough; check Microsoft's current rules for your case.
2. In Partner Center: **Apps and games -> New product -> MSIX or PWA app**, reserve the name.
3. Open **Product management -> Product identity** and copy three values: *Package/Identity/Name*,
   *Package/Identity/Publisher* (looks like `CN=...`) and *Publisher display name*.

## Build the package (PowerShell, on Windows 10/11 with the Windows SDK installed)
```powershell
python -m pip install -r requirements/build.txt
python tools/make_store_assets.py                       # regenerates packaging/windows/msix/Assets from the app icon
pyinstaller --noconfirm --clean packaging/pyinstaller/proconvert.spec
python packaging/verify_build.py dist/ProConvertStudio/ProConvertStudio.exe      # must print 12/12 routes passed
.\packaging\windows\msix\build_msix.ps1 -IdentityName "<Identity/Name>" -Publisher "<Identity/Publisher>" `
    -PublisherDisplayName "<Publisher display name>"
```
Output: `dist\ProConvertStudio.msix` (unsigned). The version comes from `proconvert.__version__` (1.0.0 -> 1.0.0.0; the
Store requires the 4th number to be 0).

## Test it on your own PC before submitting
1. Create a test certificate whose **Subject equals the Publisher value** and sign a COPY of the package:
   `New-SelfSignedCertificate -Type Custom -Subject "<Publisher>" -KeyUsage DigitalSignature -CertStoreLocation Cert:\CurrentUser\My -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3","2.5.29.19={text}")`
   then export it, trust it under *Trusted People*, and run `signtool sign /fd SHA256 /a /f test.pfx /p <password> ProConvertStudio.msix`.
2. Install by double-clicking the signed copy (or `Add-AppxPackage`). Check: launches, converts all 12 routes and images,
   dark/light themes, languages, history survives a restart, uninstall removes the app.
3. Run the **Windows App Certification Kit** (`appcert.exe`, part of the SDK) on the package and fix every failure.
4. Settings/history live in the per-user data folders. For a packaged app Windows redirects writes under `%APPDATA%` to a
   private per-package location that is **removed when the app is uninstalled** (it is kept across Store updates).
   Document this for users (tell them to export history first) and verify it on your machine.

## Submit (browser)
* Upload `ProConvertStudio.msix` under *Packages*. Supported: Windows 10 1809+ and Windows 11 (x64 only; no ARM64 build exists).
* *Properties*: category Productivity. *Age rating*: complete the questionnaire (no ads, no user-generated content, no network).
* *Store listing* per language (en, fr, es, ar): description, at least 1 screenshot (take real ones from the running app; none are bundled),
  keywords. Do not claim features that are experimental (see the compatibility table in Help).
* **Privacy policy URL is required.** `docs/PRIVACY.md` is the privacy statement: publish it on a web page (for example the
  rendered file in this repository) and give that URL to the Store.
* *Notes for certification*: explain the restricted capability `runFullTrust` ("packaged desktop application converting
  documents locally; no network access"). No other capabilities are requested.
* Pricing: **free**. The program has no licensing, trial or purchase features.

## Known gaps (also in docs/KNOWN_ISSUES.md)
The UI, the frozen build and the MSIX have not been run on real Windows by the author; there is no x86/ARM64 build;
the Help table's "Experimental" routes need human review and are labelled that way in the Store text you write.
