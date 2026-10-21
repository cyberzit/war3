param(
    [string]$Thumbprint = "",
    [string]$SubjectName = "Open Source Developer"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

# Locate signtool.exe from Windows SDK
$signtool = Get-ChildItem -Path "${env:ProgramFiles(x86)}\Windows Kits\10\bin", "${env:ProgramFiles}\Windows Kits\10\bin", "${env:ProgramFiles(x86)}\Microsoft SDKs\Windows" -Filter "signtool.exe" -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match "x64|x86" } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1 -ExpandProperty FullName

if (-not $signtool) {
    Write-Error "signtool.exe олдсонгүй. Windows SDK суулгасан эсэхийг шалгана уу."
    exit 1
}

Write-Host "Using SignTool: $signtool" -ForegroundColor Cyan

$targets = @(
    (Join-Path $root "MongolRanger.exe"),
    (Join-Path $root "dist_packages\MongolRanger-Setup.exe"),
    (Join-Path $root "dist_packages\MongolRanger_4.8_x64-setup.exe")
)

foreach ($file in $targets) {
    if (-not (Test-Path $file)) { continue }
    Write-Host "Signing: $file" -ForegroundColor Yellow

    if ($Thumbprint) {
        # 1. SHA-1 primary signature for legacy Windows 7 SP1 compatibility
        & $signtool sign /sha1 $Thumbprint /fd sha1 /t http://time.certum.pl /v $file
        # 2. Dual-sign append SHA-256 RFC3161 signature for Windows 8/10/11 & Browsers
        & $signtool sign /sha1 $Thumbprint /as /fd sha256 /tr http://time.certum.pl /td sha256 /v $file
    } else {
        # Auto-select by Subject Name (e.g., Certum "Open Source Developer")
        & $signtool sign /n $SubjectName /fd sha1 /t http://time.certum.pl /v $file
        & $signtool sign /n $SubjectName /as /fd sha256 /tr http://time.certum.pl /td sha256 /v $file
    }

    & $signtool verify /pa /v $file
}

Write-Host "All packages dual-signed (SHA-1 + SHA-256) successfully!" -ForegroundColor Green
