param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [string]$Python = 'python',
    [string]$PreviousInstaller = ''
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$setupPath = (Resolve-Path -LiteralPath $Installer).Path
$initialSetup = if ($PreviousInstaller) { (Resolve-Path -LiteralPath $PreviousInstaller).Path } else { $setupPath }
$registered = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{3E9CFC2A-A5A2-460C-9C63-26DF955A17E4}_is1'
if (Test-Path -LiteralPath $registered) { throw 'Run installation tests on a machine without a registered user installation.' }
$testRoot = Join-Path $repoRoot ('output/installer-test-' + [guid]::NewGuid().ToString('N'))
$installDir = Join-Path $testRoot 'Program Files Unicode/Ankicard'
$stateDir = Join-Path $testRoot 'user-state'
New-Item -ItemType Directory -Force $stateDir | Out-Null
$sentinel = Join-Path $stateDir 'preserve.txt'
[IO.File]::WriteAllText($sentinel, 'User data must survive upgrade and uninstall')
$promptDir = Join-Path $stateDir 'prompts'
New-Item -ItemType Directory -Force $promptDir | Out-Null
[IO.File]::WriteAllText((Join-Path $promptDir 'legacy-check.md'), 'Legacy custom prompt retained across releases')
[IO.File]::WriteAllText((Join-Path $promptDir 'types.json'), '{"custom/legacy-check.md":"supplement"}')
[IO.File]::WriteAllText((Join-Path $stateDir 'settings.json'), '{"locale":"zh","theme":"dark","palette":"paper"}')
$previousDataDir = $env:ANKICARD_DATA_DIR
$env:ANKICARD_DATA_DIR = $stateDir
function Run-Installer([string]$Program, [string[]]$Arguments) {
    $process = Start-Process -FilePath $Program -ArgumentList $Arguments -WindowStyle Hidden -Wait -PassThru
    if ($process.ExitCode -ne 0) { throw "Installer failed: $($process.ExitCode)" }
}
try {
    $installArgs = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOICONS', '/TASKS=', ('/DIR="' + $installDir + '"'))
    Run-Installer $initialSetup $installArgs
    $exe = Join-Path $installDir 'Ankicard.exe'
    if (-not (Test-Path -LiteralPath $exe)) { throw 'Installed executable missing' }
    & $Python (Join-Path $PSScriptRoot 'check_desktop.py') $exe --state-directory $stateDir
    if ($LASTEXITCODE -ne 0) { throw 'Installed desktop verification failed' }
    $firstJobs = @(Get-ChildItem (Join-Path $stateDir 'jobs') -Directory).Count
    if ($firstJobs -ne 3) { throw 'Expected three persisted demo jobs before upgrade' }
    $preferencesBefore = [IO.File]::ReadAllText((Join-Path $stateDir 'settings.json'))
    $promptBefore = Get-Item -LiteralPath (Join-Path $promptDir 'legacy-check.md')
    if (-not $promptBefore) { throw 'Expected saved custom prompt' }
    $promptHash = (Get-FileHash -LiteralPath $promptBefore.FullName).Hash
    & $Python (Join-Path $PSScriptRoot 'check_update_install.py') $setupPath $exe --state-directory $stateDir
    if ($LASTEXITCODE -ne 0) { throw 'One-click updater verification failed' }
    if (@(Get-ChildItem (Join-Path $stateDir 'jobs') -Directory).Count -ne 6) { throw 'Update did not preserve jobs' }
    # No /DIR on the second manual install: Setup must detect and reuse the old directory.
    Run-Installer $setupPath @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOICONS', '/TASKS=')
    if (-not (Test-Path -LiteralPath $sentinel)) { throw 'Upgrade removed user data' }
    $preferencesAfter = Get-Content -LiteralPath (Join-Path $stateDir 'settings.json') -Raw | ConvertFrom-Json
    if ($preferencesAfter.theme -ne 'dark' -or $preferencesAfter.palette -ne 'paper') { throw 'Upgrade changed appearance preferences' }
    if ((Get-FileHash -LiteralPath $promptBefore.FullName).Hash -ne $promptHash) { throw 'Upgrade changed prompt' }
    & $Python (Join-Path $PSScriptRoot 'check_desktop.py') $exe --state-directory $stateDir
    if ($LASTEXITCODE -ne 0) { throw 'Upgraded desktop verification failed' }
    if (@(Get-ChildItem (Join-Path $stateDir 'jobs') -Directory).Count -ne 9) { throw 'Upgrade did not preserve demo jobs' }
    $actualVersion = (Get-ItemProperty -LiteralPath $registered).DisplayVersion
    try {
        # This registry entry belongs solely to this disposable test installation.
        Set-ItemProperty -LiteralPath $registered -Name DisplayVersion -Value '99.0.0'
        $downgrade = Start-Process -FilePath $setupPath -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -WindowStyle Hidden -Wait -PassThru
        if ($downgrade.ExitCode -eq 0) { throw 'Installer allowed a downgrade' }
    } finally {
        Set-ItemProperty -LiteralPath $registered -Name DisplayVersion -Value $actualVersion
    }
} finally {
    $uninstaller = Join-Path $installDir 'unins000.exe'
    if (Test-Path -LiteralPath $uninstaller) {
        Run-Installer $uninstaller @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART')
    }
    $env:ANKICARD_DATA_DIR = $previousDataDir
}
if (Test-Path -LiteralPath (Join-Path $installDir 'Ankicard.exe')) { throw 'Uninstall left application executable' }
if (-not (Test-Path -LiteralPath $sentinel)) { throw 'Uninstall removed user data' }
if (@(Get-ChildItem (Join-Path $stateDir 'jobs') -Directory).Count -ne 9) { throw 'Uninstall removed generated jobs' }
if ((Get-FileHash -LiteralPath $promptBefore.FullName).Hash -ne $promptHash) { throw 'Uninstall changed prompt' }
Write-Host 'Installer OK: install, one-click update, real desktop relaunch, detected-directory upgrade, uninstall, preserved user data.'
