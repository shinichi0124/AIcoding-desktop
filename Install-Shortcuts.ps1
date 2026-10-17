# Stable "AI Coding Desktop" shortcuts. In-place TargetPath update (AGENTS.md B.19).
# Never delete-and-recreate: pinned Start/Taskbar copies keep working.
#
# Target is wscript.exe + Launch-Desktop-Silent.vbs so Win11 still offers
# "Pin to taskbar" (it hides that option when the target is a .bat).
#
# Icon lives at %LOCALAPPDATA%\AI-Coding-Desktop\app.ico (short path, no spaces)
# copied from sources\windows\app\web\assets\ai-coding-desktop.ico.
$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$launcher = Join-Path $root 'Launch-Desktop-Silent.vbs'
if (-not (Test-Path -LiteralPath $launcher)) { throw "Missing $launcher" }
$srcIco = Join-Path $root 'sources\windows\app\web\assets\ai-coding-desktop.ico'
if (-not (Test-Path -LiteralPath $srcIco)) { throw "Missing $srcIco (run scripts\make_icon.py first)" }

$stableDir = Join-Path $env:LOCALAPPDATA 'AI-Coding-Desktop'
New-Item -ItemType Directory -Force -Path $stableDir | Out-Null
$stableIco = Join-Path $stableDir 'app.ico'
Copy-Item -LiteralPath $srcIco -Destination $stableIco -Force

$shell = New-Object -ComObject WScript.Shell
$wscript = Join-Path $env:SystemRoot 'System32\wscript.exe'

function Set-AcdShortcut([string]$lnkPath) {
    $sc = $shell.CreateShortcut($lnkPath)
    $sc.TargetPath = $wscript
    $sc.Arguments = '"' + $launcher + '"'
    $sc.WorkingDirectory = $root
    $sc.WindowStyle = 7
    $sc.Description = 'AI Coding Desktop (Coding platform)'
    $sc.IconLocation = $stableIco
    $sc.Save()
    Write-Host ('OK: ' + $lnkPath)
}

# Start Menu: always maintained.
Set-AcdShortcut (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\AI Coding Desktop.lnk')

# Desktop: create/update (user asked for a shortcut this turn).
Set-AcdShortcut (Join-Path ([Environment]::GetFolderPath('Desktop')) 'AI Coding Desktop.lnk')

# Taskbar pin: update only when already pinned.
$taskbar = Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\AI Coding Desktop.lnk'
if (Test-Path -LiteralPath $taskbar) { Set-AcdShortcut $taskbar } else { Write-Host ('SKIP (not pinned): ' + $taskbar) }
