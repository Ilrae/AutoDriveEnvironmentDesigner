param(
    [string]$PythonVersion = "3.7",
    [string]$ReleaseLabel = "",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$bundleScript = Join-Path $repoRoot "packaging\windows\build_windows_bundle.ps1"
$distDir = Join-Path $repoRoot "dist\AutoDriveEnvironmentDesigner"
$installerPath = Join-Path $repoRoot "output\installer\AutoDriveEnvironmentDesigner_Setup.exe"
$releaseRoot = Join-Path $repoRoot "output\release"

if ([string]::IsNullOrWhiteSpace($ReleaseLabel)) {
    $ReleaseLabel = Get-Date -Format "yyyy-MM-dd"
}

$portableZipName = "AutoDriveEnvironmentDesigner_Windows_Portable_$ReleaseLabel.zip"
$setupName = "AutoDriveEnvironmentDesigner_Windows_Setup_$ReleaseLabel.exe"
$notesName = "AutoDriveEnvironmentDesigner_Windows_Release_$ReleaseLabel.txt"

if (-not $SkipBuild) {
    & powershell -ExecutionPolicy Bypass -File $bundleScript -PythonVersion $PythonVersion
}

if (-not (Test-Path $distDir)) {
    throw "Executable bundle directory was not found: $distDir"
}
if (-not (Test-Path $installerPath)) {
    throw "Installer was not found: $installerPath"
}

New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null

$portableZipPath = Join-Path $releaseRoot $portableZipName
$setupCopyPath = Join-Path $releaseRoot $setupName
$notesPath = Join-Path $releaseRoot $notesName

if (Test-Path $portableZipPath) {
    Remove-Item $portableZipPath -Force
}

Compress-Archive -Path (Join-Path $distDir "*") -DestinationPath $portableZipPath -CompressionLevel Optimal
Copy-Item $installerPath $setupCopyPath -Force

$notes = @"
AutoDrive Environment Designer Windows release asset bundle

Release label: $ReleaseLabel
Created at: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

Files:
- $setupName
  Installer build for end users. Recommended for normal use.

- $portableZipName
  Portable bundle. Extract the zip and run AutoDriveEnvironmentDesigner.exe.

Quick start:
1. Launch CARLA first.
2. Run the installer or extract the portable zip.
3. Set the PythonAPI path to your CARLA installation.
4. Use Track, Intermediate, or Practical stage from the GUI.

Suggested GitHub distribution:
- Create a GitHub Release from the current tagged or main commit.
- Upload both files above as release assets.
- Mention that CARLA 0.9.15 + PythonAPI path setup is required.
"@

$notes | Set-Content -Path $notesPath -Encoding UTF8

Write-Host "Release assets created:"
Write-Host "  Setup:    $setupCopyPath"
Write-Host "  Portable: $portableZipPath"
Write-Host "  Notes:    $notesPath"
