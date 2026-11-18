<#
 Build an MSIX package from the frozen PyInstaller output.  AUTHORED BUT NOT YET RUN on a real Windows machine.

 Prerequisites: Windows SDK (makeappx.exe, and signtool.exe for local test signing), the frozen app in dist\ProConvertStudio.
 For a Store upload the package does NOT need your own signature: the Store signs it after certification.

 Example (values come from Partner Center > Product identity):
   .\packaging\windows\msix\build_msix.ps1 -IdentityName "12345Publisher.ProConvertStudio" `
        -Publisher "CN=00000000-0000-0000-0000-000000000000" -PublisherDisplayName "Your Name"
#>
param(
  [Parameter(Mandatory = $true)] [string] $IdentityName,
  [Parameter(Mandatory = $true)] [string] $Publisher,
  [Parameter(Mandatory = $true)] [string] $PublisherDisplayName,
  [string] $Version = "",
  [string] $Dist = "dist\ProConvertStudio",
  [string] $Out = "dist\ProConvertStudio.msix"
)
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
Set-Location $root

if (-not $Version) {
  $py = (python -c "import proconvert; print(proconvert.__version__)").Trim()
  if ($py -notmatch '^(\d+)\.(\d+)\.(\d+)$') { throw "Store packages need a plain MAJOR.MINOR.PATCH version, got '$py'" }
  $Version = "$py.0"                                   # MSIX versions have four parts; the last must be 0 for Store submissions
}
if (-not (Test-Path (Join-Path $Dist "ProConvertStudio.exe"))) { throw "Frozen app not found in $Dist. Run pyinstaller first." }

$makeappx = (Get-Command makeappx.exe -ErrorAction SilentlyContinue).Source
if (-not $makeappx) {
  $makeappx = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter makeappx.exe -ErrorAction SilentlyContinue |
              Where-Object { $_.FullName -like "*\x64\*" } | Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $makeappx) { throw "makeappx.exe not found. Install the Windows 10/11 SDK." }

$stage = Join-Path $root "build\msix-stage"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item $stage -ItemType Directory | Out-Null
Copy-Item (Join-Path $Dist "*") $stage -Recurse
Copy-Item (Join-Path $PSScriptRoot "Assets") (Join-Path $stage "Assets") -Recurse

$xml = Get-Content (Join-Path $PSScriptRoot "AppxManifest.xml") -Raw -Encoding UTF8
$xml = $xml.Replace("@IDENTITY_NAME@", $IdentityName).Replace("@PUBLISHER@", $Publisher).Replace("@PUBLISHER_DISPLAY_NAME@", $PublisherDisplayName).Replace("@VERSION@", $Version)
if ($xml -match "@[A-Z_]+@") { throw "Unreplaced placeholder left in the manifest." }
[IO.File]::WriteAllText((Join-Path $stage "AppxManifest.xml"), $xml, (New-Object Text.UTF8Encoding($false)))

if (Test-Path $Out) { Remove-Item $Out -Force }
& $makeappx pack /d $stage /p $Out /o
if ($LASTEXITCODE -ne 0) { throw "makeappx failed with exit code $LASTEXITCODE" }
Write-Host "Created $Out (unsigned). Upload it in Partner Center; the Store signs it after certification."
Write-Host "To test locally you must sign it with a test certificate whose subject equals the Publisher value (see docs/MICROSOFT_STORE.md)."
