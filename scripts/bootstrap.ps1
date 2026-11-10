#!/usr/bin/env pwsh
# Bootstrap the Phase 0 scaffold on Windows.
# Safe to re-run.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host "==> Checking prerequisites"
foreach ($cmd in @("uv", "docker")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        throw "Missing prerequisite: $cmd"
    }
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "==> Created .env from .env.example (fill in provider keys when ready)"
}
if (-not (Test-Path "config/providers.yaml")) {
    Copy-Item "config/providers.example.yaml" "config/providers.yaml"
    Write-Host "==> Created config/providers.yaml; verify limits in each provider console"
}

Write-Host "==> Installing Python dependencies"
uv sync --group dev

Write-Host "==> Starting Postgres + SearXNG"
docker compose up -d postgres searxng

Write-Host "==> Waiting for Postgres"
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    docker compose exec -T postgres pg_isready -U research -d research *> $null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 1
}
if (-not $ready) { throw "Postgres did not become ready" }

Write-Host "==> Waiting for SearXNG"
$searxngReady = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8080/" -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) { $searxngReady = $true; break }
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $searxngReady) { throw "SearXNG did not become ready" }

Write-Host "==> Applying database migrations"
uv run alembic upgrade head

Write-Host ""
Write-Host "Ready. Next:"
Write-Host "  uv run pytest"
Write-Host "  uv run python -m research_agent"
Write-Host "  docker compose logs -f"
