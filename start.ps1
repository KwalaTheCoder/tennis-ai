$py='C:\Users\kwala\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if(-not(Test-Path $py)){$py='python'}
$key=[Environment]::GetEnvironmentVariable('LIVE_TENNIS_API_KEY','User')
if($key){
    $env:LIVE_TENNIS_API_KEY=$key
    Write-Host 'API key loaded. Starting with real-data connection.' -ForegroundColor Green
}else{
    Write-Host 'API key is not configured. Starting in manual mode.' -ForegroundColor Yellow
}
Write-Host 'Open http://127.0.0.1:8775'
& $py "$PSScriptRoot\server.py"
