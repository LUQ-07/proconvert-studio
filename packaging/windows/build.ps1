<#
 Windows build: PyInstaller one-folder app + Inno Setup installer (+ optional code signing).
 NOT YET RUN: authored on Linux without Windows, PySide6 or PyInstaller. Treat as unverified until
 you have run it on Windows 10/11 and ticked the Release Checklist. See docs/BUILD_GUIDE.md.
 Usage:  powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
 Optional environment: SIGN_THUMBPRINT (certificate SHA1 in the store), TIMESTAMP_URL
#>
$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\..\.."
Set-Location $root

py -3.11 -m venv .venv-build
& .\.venv-build\Scripts\python.exe -m pip install --upgrade pip
& .\.venv-build\Scripts\python.exe -m pip install -r requirements\build.txt
& .\.venv-build\Scripts\python.exe packaging\windows\make_version_info.py
& .\.venv-build\Scripts\pyinstaller.exe --noconfirm --clean packaging\pyinstaller\proconvert.spec

$exe = "dist\ProConvertStudio\ProConvertStudio.exe"
if ($env:SIGN_THUMBPRINT) {
  $ts = if ($env:TIMESTAMP_URL) { $env:TIMESTAMP_URL } else { "http://timestamp.digicert.com" }
  & signtool sign /sha1 $env:SIGN_THUMBPRINT /fd sha256 /tr $ts /td sha256 $exe
}

# Packaging verification: run the built-in end-to-end self test from the FROZEN executable.
& .\.venv-build\Scripts\python.exe packaging\verify_build.py $exe

$ver = (& .\.venv-build\Scripts\python.exe -c "import proconvert;print(proconvert.__version__)").Trim()
Copy-Item LICENSE packaging\windows\LICENSE.txt -Force
$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { throw "Inno Setup 6 not found. Install it from https://jrsoftware.org/isinfo.php" }
& $iscc "/DAppVersion=$ver" packaging\windows\installer.iss
if ($env:SIGN_THUMBPRINT) {
  & signtool sign /sha1 $env:SIGN_THUMBPRINT /fd sha256 /tr $ts /td sha256 "dist\installer\ProConvertStudio-$ver-setup.exe"
}
Write-Host "Done. Installer in dist\installer. An unsigned installer WILL trigger SmartScreen warnings."
