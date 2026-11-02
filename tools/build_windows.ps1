param(
    [string]$Python = 'python',
    [string]$Iscc = '',
    [Parameter(Mandatory=$true)][string]$WebViewInstaller
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $repoRoot
try {
    & $Python -c "import sys,struct; assert sys.platform=='win32' and struct.calcsize('P')==8; assert sys.version_info[:2]==(3,12), 'Build with CPython 3.12 x64'"
    if ($LASTEXITCODE -ne 0) { throw 'Unsupported build environment' }
    $runtimePath = (Resolve-Path -LiteralPath $WebViewInstaller).Path
    $signature = Get-AuthenticodeSignature -LiteralPath $runtimePath
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
        throw 'WebView2 standalone installer must have a valid Microsoft signature'
    }
    if (-not $Iscc) {
        $compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($compiler) { $Iscc = $compiler.Source }
        else { $Iscc = Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6/ISCC.exe' }
    }
    if (-not (Test-Path -LiteralPath $Iscc)) { throw 'Pass -Iscc with the path to Inno Setup ISCC.exe' }
    $version = (& $Python tools/windows_build_metadata.py | Select-Object -Last 1)
    if ($LASTEXITCODE -ne 0) { throw 'Build metadata/license generation failed' }
    & $Python -m PyInstaller --noconfirm --clean --distpath dist --workpath build/pyinstaller packaging/windows/ankicard.spec
    if ($LASTEXITCODE -ne 0) { throw 'Application freeze failed' }
    & $Iscc "/DAppVersion=$version" "/DWebViewInstaller=$runtimePath" packaging/windows/installer.iss
    if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed' }
    $installer = Get-Item "dist/windows/Ankicard-$version-windows-x64-Setup.exe"
    $hash = (Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText((Join-Path $installer.DirectoryName 'SHA256SUMS.txt'), "$hash  $($installer.Name)`n", (New-Object Text.UTF8Encoding $false))
    $revision = (& git rev-parse HEAD).Trim()
    $buildInfo = [ordered]@{
        application_version = $version
        source_revision = $revision
        source_dirty = [bool](& git status --porcelain)
        python_version = (& $Python -c 'import platform; print(platform.python_version())')
        inno_setup_version = '7.1.1'
        webview2_installer_version = (Get-Item -LiteralPath $runtimePath).VersionInfo.FileVersion
        webview2_installer_sha256 = (Get-FileHash -LiteralPath $runtimePath -Algorithm SHA256).Hash.ToLowerInvariant()
        installer_sha256 = $hash
    }
    [IO.File]::WriteAllText((Join-Path $installer.DirectoryName 'BUILD-INFO.json'), ($buildInfo | ConvertTo-Json), (New-Object Text.UTF8Encoding $false))
    Write-Host "Installer: $($installer.FullName)"
} finally { Pop-Location }
