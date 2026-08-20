param(
    [Parameter(Mandatory=$true)][string]$Username,
    [ValidateSet("viewer", "editor", "admin")][string]$Role = "viewer"
)
$ErrorActionPreference = "Stop"
$repo = Split-Path $PSScriptRoot -Parent
$envFile = Join-Path $repo ".env"
$secure = Read-Host "${Username}의 비밀번호" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
if ([string]::IsNullOrWhiteSpace($password)) { throw "빈 비밀번호는 사용할 수 없습니다." }
$salt = New-Object byte[] 16
[Security.Cryptography.RandomNumberGenerator]::Fill($salt)
$iterations = 200000
$derive = [Security.Cryptography.Rfc2898DeriveBytes]::new($password, $salt, $iterations, [Security.Cryptography.HashAlgorithmName]::SHA256)
try { $digest = $derive.GetBytes(32) } finally { $derive.Dispose() }
$encoded = 'pbkdf2_sha256$' + $iterations + '$' + [Convert]::ToBase64String($salt) + '$' + [Convert]::ToBase64String($digest)

$lines = if (Test-Path $envFile) { [Collections.Generic.List[string]](Get-Content $envFile) } else { [Collections.Generic.List[string]]::new() }
$users = @{}
$existing = $lines | Where-Object { $_ -like 'UI_USERS_JSON=*' } | Select-Object -First 1
if ($existing) {
    $raw = $existing.Substring('UI_USERS_JSON='.Length)
    if ($raw.StartsWith("'") -and $raw.EndsWith("'")) { $raw = $raw.Substring(1, $raw.Length - 2) }
    if ($raw -and $raw -ne '{}') { (ConvertFrom-Json $raw).PSObject.Properties | ForEach-Object { $users[$_.Name] = $_.Value } }
}
$users[$Username] = @{ password_hash = $encoded; role = $Role }
$json = ConvertTo-Json $users -Compress
$lines = [Collections.Generic.List[string]]($lines | Where-Object { $_ -notlike 'UI_USERS_JSON=*' -and $_ -notlike 'UI_AUTH_ENABLED=*' })
$lines.Add("UI_AUTH_ENABLED=true")
$lines.Add("UI_USERS_JSON='$json'")
Set-Content -LiteralPath $envFile -Value $lines -Encoding utf8
Write-Host "사용자 '$Username'를 '$Role' 역할로 저장했습니다. scripts/start_dev.ps1 로 재시작하세요."
