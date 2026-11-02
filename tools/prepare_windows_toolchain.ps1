param([string]$Directory = 'output/toolchain')
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force $Directory | Out-Null
$target = (Resolve-Path -LiteralPath $Directory).Path
$inno = Join-Path $target 'innosetup-7.1.1-x64.exe'
$runtime = Join-Path $target 'MicrosoftEdgeWebView2RuntimeInstallerX64.exe'
& curl.exe --fail --location --retry 3 --max-time 600 --output $inno 'https://github.com/jrsoftware/issrc/releases/download/is-7_1_1/innosetup-7.1.1-x64.exe'
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup download failed' }
if ((Get-FileHash -LiteralPath $inno -Algorithm SHA256).Hash -ne '8A5A6711C3766A6E5FB74F280BA0E3551E719CE94538D901FDBD1F8F9920B3F0') {
    throw 'Inno Setup checksum mismatch'
}
if ((Get-AuthenticodeSignature -LiteralPath $inno).Status -ne 'Valid') { throw 'Invalid Inno Setup signature' }
& curl.exe --fail --location --retry 3 --max-time 600 --output $runtime 'https://go.microsoft.com/fwlink/?linkid=2124701'
if ($LASTEXITCODE -ne 0) { throw 'WebView2 download failed' }
$signature = Get-AuthenticodeSignature -LiteralPath $runtime
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
    throw 'Invalid Microsoft WebView2 signature'
}
$compilerDir = Join-Path $target 'inno'
$process = Start-Process -FilePath $inno -ArgumentList @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CURRENTUSER','/NOICONS',('/DIR="'+$compilerDir+'"')) -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -ne 0) { throw 'Inno Setup tool installation failed' }
Write-Host "Toolchain ready in $target"
