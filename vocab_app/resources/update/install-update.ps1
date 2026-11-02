param([Parameter(Mandatory=$true)][string]$PlanPath)
$ErrorActionPreference = 'Stop'
$plan = Get-Content -LiteralPath $PlanPath -Raw -Encoding UTF8 | ConvertFrom-Json
$result = [ordered]@{ ok = $false; version = $plan.version; code = 'prepare_failed'; backup = $plan.backup }
$installStarted = $false
try {
    $dataRoot = [IO.Path]::GetFullPath($plan.data_directory).TrimEnd('\')
    $updateRoot = $dataRoot + '\updates\'
    $installerPath = [IO.Path]::GetFullPath($plan.installer)
    $installDirectory = [IO.Path]::GetFullPath($plan.install_directory).TrimEnd('\')
    $appExecutable = [IO.Path]::GetFullPath($plan.executable)
    if (-not $installerPath.StartsWith($updateRoot, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid staging path' }
    if ($appExecutable -ne (Join-Path $installDirectory 'Ankicard.exe')) { throw 'Invalid application path' }
    if ($plan.sha256 -notmatch '^[0-9a-f]{64}$' -or $plan.version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid metadata' }
    if ((Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $plan.sha256) { throw 'Checksum mismatch' }
    if (-not (Test-Path -LiteralPath $plan.backup -PathType Leaf)) { throw 'Backup missing' }
    # Obtain process objects before announcing readiness, avoiding PID-reuse races.
    $parentProcess = Get-Process -Id $plan.parent_pid -ErrorAction SilentlyContinue
    $workerProcess = Get-Process -Id $plan.worker_pid -ErrorAction SilentlyContinue
    [IO.File]::WriteAllText($plan.ready, 'ready')
    $result.code = 'shutdown_timeout'
    if ($parentProcess -and -not $parentProcess.HasExited -and -not $parentProcess.WaitForExit(120000)) { throw 'Application is still running' }
    if ($workerProcess -and -not $workerProcess.HasExited -and -not $workerProcess.WaitForExit(30000)) { throw 'Worker is still running' }
    # Never force-close another application's windows or interrupt an Anki task.
    $result.code = 'verification_failed'
    if ((Get-FileHash -LiteralPath $installerPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $plan.sha256) { throw 'Checksum changed' }
    $installStarted = $true
    $result.code = 'install_failed'
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOCLOSEAPPLICATIONS', '/NORESTARTAPPLICATIONS', '/RESTARTEXITCODE=3010', ('/DIR="' + $installDirectory + '"'), ('/LOG="' + $plan.log + '"'))
    $setup = Start-Process -FilePath $installerPath -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
    if ($setup.ExitCode -notin @(0, 3010)) { throw 'Installer failed' }
    if (-not (Test-Path -LiteralPath $appExecutable)) { throw 'Application executable missing' }
    if ([Diagnostics.FileVersionInfo]::GetVersionInfo($appExecutable).ProductVersion -ne $plan.version) { throw 'Installed version mismatch' }
    $result.ok = $true
    $result.code = if ($setup.ExitCode -eq 3010) { 'restart_required' } else { 'installed' }
} catch {
    # Only stable error codes are persisted; exception text may contain private paths.
    $result['error_type'] = $_.Exception.GetType().FullName
    $result['error_line'] = $_.InvocationInfo.ScriptLineNumber
} finally {
    $temporary = $plan.result + '.tmp'
    [IO.File]::WriteAllText($temporary, ($result | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))
    Move-Item -LiteralPath $temporary -Destination $plan.result -Force
    if ($installStarted -and (Test-Path -LiteralPath $plan.executable)) {
        $env:ANKICARD_DATA_DIR = $plan.data_directory
        $env:PYINSTALLER_RESET_ENVIRONMENT = '1'
        if ($plan.smoke_report) {
            # Release tests exercise the real relaunch with the existing hidden smoke mode.
            Start-Process -FilePath $plan.executable -ArgumentList @('--smoke-test', ('"' + $plan.smoke_report + '"')) -WorkingDirectory $plan.install_directory -WindowStyle Hidden
        } else {
            Start-Process -FilePath $plan.executable -WorkingDirectory $plan.install_directory -WindowStyle Hidden
        }
    }
}
if (-not $result.ok) { exit 1 }
