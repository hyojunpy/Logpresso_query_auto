param([Parameter(Mandatory=$true)][string]$Archive)
$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) { throw "백업 파일이 없습니다: $Archive" }
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$temp = [IO.Path]::GetFullPath((Join-Path $tempRoot ("logpresso-restore-check-" + [guid]::NewGuid().ToString("N"))))
if (-not $temp.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) { throw "안전한 임시 경로가 아닙니다." }
New-Item -ItemType Directory -Path $temp | Out-Null
try {
    Expand-Archive -LiteralPath $Archive -DestinationPath $temp
    $docker = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"
    if (-not (Test-Path $docker)) { $docker = (Get-Command docker).Source }
    $mount = "type=bind,src=$temp,dst=/verify,readonly"
    & $docker run --rm --mount $mount python:3.12-slim python -c `
        "import pathlib,sqlite3,sys; files=list(pathlib.Path('/verify').rglob('*.db')); print('databases='+str(len(files))); bad=[str(p) for p in files if sqlite3.connect(p).execute('pragma integrity_check').fetchone()[0] != 'ok']; sys.exit(1 if bad else 0)"
    if ($LASTEXITCODE -ne 0) { throw "SQLite 무결성 검증에 실패했습니다." }
    Write-Host "백업 압축 해제와 SQLite 무결성 검증을 통과했습니다."
} finally {
    if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Recurse -Force }
}
