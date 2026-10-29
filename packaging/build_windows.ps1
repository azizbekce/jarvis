param(
    [switch] $SkipPlaywrightBrowser
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venv = Join-Path $root ".venv-build"
$python = Join-Path $venv "Scripts\python.exe"

Push-Location $root
try {
    if (-not (Test-Path $python)) {
        $launcher = Get-Command py -ErrorAction SilentlyContinue
        if ($launcher) {
            & $launcher.Source -3.12 -m venv $venv
        } else {
            $launcher = Get-Command python -ErrorAction SilentlyContinue
            if (-not $launcher) {
                throw "Python 3.12 is required. Install it, then rerun this script."
            }
            & $launcher.Source -m venv $venv
        }
        if ($LASTEXITCODE -ne 0) { throw "Could not create the build environment." }
    }

    & $python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Could not update pip." }
    & $python -m pip install -r (Join-Path $root "requirements-build.txt")
    if ($LASTEXITCODE -ne 0) { throw "Could not install JARVIS build dependencies." }

    $env:PLAYWRIGHT_BROWSERS_PATH = "0"
    if (-not $SkipPlaywrightBrowser) {
        & $python -m playwright install chromium
        if ($LASTEXITCODE -ne 0) { throw "Could not install the bundled Chromium browser." }
    }

    & $python (Join-Path $PSScriptRoot "make_icon.py")
    if ($LASTEXITCODE -ne 0) { throw "Could not generate the application icon." }

    $icon = Join-Path $root "assets\JARVIS.ico"
    $version = Join-Path $PSScriptRoot "version_info.txt"
    $arguments = @(
        "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", "JARVIS",
        "--contents-directory", "_internal",
        "--icon", $icon,
        "--version-file", $version,
        "--add-data", "$(Join-Path $root 'core\prompt.txt');core",
        "--add-data", "$(Join-Path $root 'assets\fonts');assets\fonts",
        "--add-data", "$(Join-Path $root 'assets\JARVIS.ico');assets",
        "--collect-all", "PySide6",
        "--collect-all", "sounddevice",
        "--collect-all", "playwright",
        "--collect-all", "cv2",
        "--collect-all", "google.genai",
        "--collect-all", "google.generativeai",
        "--collect-all", "pycaw",
        "--collect-all", "pywinauto",
        (Join-Path $root "main.py")
    )
    & $python -m PyInstaller @arguments
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed to create JARVIS.exe." }

    $compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    $iscc = if ($compiler) { $compiler.Source } else $null
    if (-not $iscc) {
        $candidates = @(
            (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
            (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
            (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
        )
        $iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if (-not $iscc) {
        throw "JARVIS.exe was built, but Inno Setup 6 was not found. Install Inno Setup 6 and rerun this script to create JARVIS-Setup-2.1.1.exe."
    }

    & $iscc (Join-Path $PSScriptRoot "JARVIS.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed to create the installer." }

    Write-Host "Build complete: dist\JARVIS\JARVIS.exe"
    Write-Host "Installer: dist\JARVIS-Setup-2.1.1.exe"
} finally {
    Pop-Location
}
