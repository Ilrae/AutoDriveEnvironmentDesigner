param(
    [string]$PythonVersion = "3.7",
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$specPath = Join-Path $repoRoot "packaging\windows\AutoDriveEnvironmentDesigner.spec"
$issPath = Join-Path $repoRoot "packaging\windows\AutoDriveEnvironmentDesigner.iss"

function Resolve-InnoSetupCompiler {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }

    $commonPaths = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )

    foreach ($candidate in $commonPaths) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

Push-Location $repoRoot
try {
    & py "-$PythonVersion" -m pip install pyinstaller
    & py "-$PythonVersion" -m PyInstaller $specPath --noconfirm --clean

    if (-not $SkipInstaller) {
        $isccPath = Resolve-InnoSetupCompiler
        if ($null -ne $isccPath) {
            & $isccPath "/DRepoRoot=$repoRoot" $issPath
        }
        else {
            Write-Warning "ISCC.exe was not found. The executable bundle was built, but the installer was skipped."
        }
    }
}
finally {
    Pop-Location
}
