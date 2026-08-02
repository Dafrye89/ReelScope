param(
    [switch]$InstallShortcut
)

$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectDir ".venv\Scripts\python.exe"
$requirements = Join-Path $projectDir "requirements-desktop.txt"
$entrypoint = Join-Path $projectDir "reelscope_desktop.pyw"
$icon = Join-Path $projectDir "assets\reelscope-icon.ico"
$templates = Join-Path $projectDir "templates"
$assets = Join-Path $projectDir "assets"

if (-not (Test-Path -LiteralPath $python)) {
    py -3 -m venv (Join-Path $projectDir ".venv")
}

& $python -m pip install -r $requirements
if ($LASTEXITCODE -ne 0) {
    throw "Desktop build dependencies could not be installed."
}

Push-Location $projectDir
try {
    & $python -m PyInstaller `
        --noconfirm `
        --clean `
        --windowed `
        --name ReelScope `
        --icon $icon `
        --add-data "${templates}:templates" `
        --add-data "${assets}:assets" `
        --collect-all webview `
        --collect-all faster_whisper `
        --collect-all ctranslate2 `
        --collect-all av `
        --hidden-import webview.platforms.edgechromium `
        $entrypoint
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed."
    }
} finally {
    Pop-Location
}

$exe = Join-Path $projectDir "dist\ReelScope\ReelScope.exe"
if (-not (Test-Path -LiteralPath $exe)) {
    throw "Expected desktop executable was not produced: $exe"
}

Write-Output "Built ReelScope desktop app: $exe"

if ($InstallShortcut) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $shortcutPath = Join-Path $desktop "ReelScope.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $exe
    $shortcut.WorkingDirectory = Split-Path -Parent $exe
    $shortcut.IconLocation = $exe + ",0"
    $shortcut.Description = "Extract, inspect, and export exact video frames with ReelScope."
    $shortcut.Save()
    Write-Output "Installed ReelScope shortcut: $shortcutPath"
}
