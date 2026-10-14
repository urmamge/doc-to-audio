# Removes the right-click menu, the queue folder and the Python environment.
# Leaves this folder's source files in place; delete the folder afterwards if you want them gone too.

foreach ($ext in '.pdf', '.docx', '.txt', '.md') {
    $menu = "HKCU:\Software\Classes\SystemFileAssociations\$ext\shell\DocToAudio"
    if (Test-Path $menu) { Remove-Item -Path $menu -Recurse -Force }
}
foreach ($dir in (Join-Path $env:LOCALAPPDATA 'doc-to-audio'), (Join-Path $PSScriptRoot '.venv')) {
    if (Test-Path $dir) { Remove-Item -Path $dir -Recurse -Force }
}
Write-Host 'Uninstalled.'
