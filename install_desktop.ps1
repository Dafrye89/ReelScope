param(
    [switch]$Launch
)

$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectDir ".venv\Scripts\python.exe"
$pythonw = Join-Path $projectDir ".venv\Scripts\pythonw.exe"
$requirements = Join-Path $projectDir "requirements-desktop.txt"
$entrypoint = Join-Path $projectDir "reelscope_desktop.pyw"
$icon = Join-Path $projectDir "assets\reelscope-icon.ico"

if (-not (Test-Path -LiteralPath $python)) {
    py -3 -m venv (Join-Path $projectDir ".venv")
}

& $python -m pip install -r $requirements
if ($LASTEXITCODE -ne 0) {
    throw "Desktop dependencies could not be installed."
}

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "ReelScope.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = '"' + $entrypoint + '"'
$shortcut.WorkingDirectory = $projectDir
$shortcut.IconLocation = $icon + ",0"
$shortcut.Description = "Extract, inspect, and export exact video frames with ReelScope."
$shortcut.Save()

Write-Output "Installed ReelScope shortcut: $shortcutPath"

if ($Launch) {
    Start-Process -FilePath $pythonw -ArgumentList ('"' + $entrypoint + '"') -WorkingDirectory $projectDir
}
