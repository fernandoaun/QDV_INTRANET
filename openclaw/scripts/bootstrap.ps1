#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function New-Secret {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    [Convert]::ToBase64String($bytes).TrimEnd("=") -replace "[+/]", "A"
}

if (-not (Test-Path ".env.example")) {
    Write-Error "Ejecutá este script desde openclaw/ (falta .env.example)."
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Creé .env desde .env.example"
}

$raw = Get-Content ".env" -Raw
if ($raw -match "(?m)^DATABASE_URL=") {
    Write-Host "ADVERTENCIA — aislamiento de base local"
    Write-Host "Quitá DATABASE_URL de openclaw/.env. El bot usa /api/v1."
    exit 2
}

if ($raw -match "(?m)^OPENCLAW_GATEWAY_TOKEN=cambi") {
    $tok = New-Secret
    $raw = $raw -replace "(?m)^OPENCLAW_GATEWAY_TOKEN=.*$", "OPENCLAW_GATEWAY_TOKEN=$tok"
    Set-Content -Path ".env" -Value $raw -Encoding utf8
    Write-Host "Generé OPENCLAW_GATEWAY_TOKEN"
}

docker version > $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker no está corriendo. Instalà Docker Desktop y volvé a intentar."
}

Write-Host "Levantando OpenClaw (la primera vez baja la imagen, puede tardar)..."
docker compose up --build -d
Write-Host ""
Write-Host "Dashboard: http://127.0.0.1:18789/"
Write-Host "Token: OPENCLAW_GATEWAY_TOKEN en openclaw/.env"
Write-Host "WhatsApp QR: whatsapp_login.bat"
