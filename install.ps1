# Sets up the Python environment and adds the "Convert to audio (Ava)" right-click menu.
# Per-user only (HKCU); no admin rights needed. Safe to re-run.

$ErrorActionPreference = 'Stop'
$root   = $PSScriptRoot
$venv   = Join-Path $root '.venv'
$python = Join-Path $venv 'Scripts\python.exe'
$script = Join-Path $root 'doc_to_audio.py'

if (-not (Test-Path $python)) {
    Write-Host 'Creating Python environment...'
    python -m venv $venv
}
& $python -m pip install --no-cache-dir -q --upgrade -r (Join-Path $root 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }

$extensions = '.pdf', '.docx', '.txt', '.md'
$speeds = [ordered]@{
    '1normal' = @('Normal speed', '1')
    '2s125'   = @('1.25x speed',  '1.25')
    '3s15'    = @('1.5x speed',   '1.5')
    '4s2'     = @('2x speed',     '2')
}

foreach ($ext in $extensions) {
    $menu = "HKCU:\Software\Classes\SystemFileAssociations\$ext\shell\DocToAudio"
    New-Item -Path $menu -Force | Out-Null
    Set-ItemProperty -Path $menu -Name 'MUIVerb'          -Value 'Convert to audio (Ava)'
    Set-ItemProperty -Path $menu -Name 'SubCommands'      -Value ''
    Set-ItemProperty -Path $menu -Name 'Icon'             -Value 'imageres.dll,-1026'
    Set-ItemProperty -Path $menu -Name 'MultiSelectModel' -Value 'Player'

    foreach ($key in $speeds.Keys) {
        $label, $speed = $speeds[$key]
        $item = "$menu\shell\$key"
        New-Item -Path "$item\command" -Force | Out-Null
        Set-ItemProperty -Path $item -Name 'MUIVerb'          -Value $label
        Set-ItemProperty -Path $item -Name 'MultiSelectModel' -Value 'Player'
        Set-ItemProperty -Path "$item\command" -Name '(default)' `
            -Value "`"$python`" `"$script`" --speed $speed `"%1`""
    }
}

Write-Host "Installed. Right-click a $($extensions -join ', ') file > Show more options > Convert to audio (Ava)."
