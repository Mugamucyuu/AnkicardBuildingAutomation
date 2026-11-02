param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$setupPath = (Resolve-Path -LiteralPath $Installer).Path
$testRoot = Join-Path $repoRoot ('output/installer-test-' + [guid]::NewGuid().ToString('N'))
$installDir = Join-Path $testRoot 'Program Files Unicode/Ankicard'
$stateDir = Join-Path $testRoot 'user-state'
New-Item -ItemType Directory -Force $stateDir | Out-Null
$sentinel = Join-Path $stateDir 'preserve.txt'
[IO.File]::WriteAllText($sentinel, 'User data must survive upgrade and uninstall')
$previousDataDir = $env:ANKICARD_DATA_DIR
$env:ANKICARD_DATA_DIR = $stateDir
function Run-Installer([string]$Program, [string[]]$Arguments) {
    $process = Start-Process -FilePath $Program -ArgumentList $Arguments -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Installer failed: $($process.ExitCode)" }
}
try {
    $installArgs = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOICONS', '/TASKS=', ('/DIR="' + $installDir + '"'))
    Run-Installer $setupPath $installArgs
    $exe = Join-Path $installDir 'Ankicard.exe'
    if (-not (Test-Path -LiteralPath $exe)) { throw 'Installed executable missing' }
    & $Python (Join-Path $PSScriptRoot 'check_desktop.py') $exe --state-directory $stateDir
    if ($LASTEXITCODE -ne 0) { throw 'Installed desktop verification failed' }
    $firstJobs = @(Get-ChildItem (Join-Path $stateDir 'jobs') -Directory).Count
    if ($firstJobs -ne 3) { throw 'Expected three persisted demo jobs before upgrade' }
    Run-Installer $setupPath $installArgs
    if (-not (Test-Path -LiteralPath $sentinel)) { throw 'Upgrade removed user data' }
    & $Python (Join-Path $PSScriptRoot 'check_desktop.py') $exe --state-directory $stateDir
    if ($LASTEXITCODE -ne 0) { throw 'Upgraded desktop verification failed' }
    if (@(Get-ChildItem (Join-Path $stateDir 'jobs') -Directory).Count -ne 6) { throw 'Upgrade did not preserve demo jobs' }
} finally {
    $uninstaller = Join-Path $installDir 'unins000.exe'
    if (Test-Path -LiteralPath $uninstaller) {
        Run-Installer $uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
    }
    $env:ANKICARD_DATA_DIR = $previousDataDir
}
if (Test-Path -LiteralPath (Join-Path $installDir 'Ankicard.exe')) { throw 'Uninstall left application executable' }
if (-not (Test-Path -LiteralPath $sentinel)) { throw 'Uninstall removed user data' }
if (@(Get-ChildItem (Join-Path $stateDir 'jobs') -Directory).Count -ne 6) { throw 'Uninstall removed generated jobs' }
Write-Host 'Installer OK: install, real desktop, reinstall/upgrade, uninstall, preserved user data.'
