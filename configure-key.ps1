$ErrorActionPreference = 'Stop'
Write-Host 'Didban Tennis - API setup' -ForegroundColor Cyan
$key = Read-Host 'Paste your Live Tennis API key'
if ([string]::IsNullOrWhiteSpace($key)) {
    Write-Host 'ERROR: Key was empty.' -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}
try {
    [Environment]::SetEnvironmentVariable('LIVE_TENNIS_API_KEY', $key.Trim(), 'User')
    $saved = [Environment]::GetEnvironmentVariable('LIVE_TENNIS_API_KEY', 'User')
    if ([string]::IsNullOrWhiteSpace($saved)) { throw 'Windows did not save the key.' }
    Write-Host ('SUCCESS: Key saved (' + $saved.Length + ' characters).') -ForegroundColor Green
    Write-Host 'Now run start.ps1.' -ForegroundColor Green
} catch {
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
}
Read-Host 'Press Enter to close'
