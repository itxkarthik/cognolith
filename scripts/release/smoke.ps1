$ErrorActionPreference = "Stop"
$frontendUrl = if ($env:FRONTEND_URL) { $env:FRONTEND_URL } else { "http://127.0.0.1:8080" }
$backendUrl = if ($env:BACKEND_URL) { $env:BACKEND_URL } else { "http://127.0.0.1:3000" }

Invoke-WebRequest -UseBasicParsing "$backendUrl/health/live" | Out-Null
Invoke-WebRequest -UseBasicParsing "$backendUrl/health/ready" | Out-Null
Invoke-WebRequest -UseBasicParsing "$frontendUrl/auth/login" | Out-Null

# Optional: stream one chat reply and fail if anything on the way buffers it.
# See smoke.sh for SMOKE_EMAIL, SSE_CHECK_PASSWORD and SMOKE_STREAM_URL.
if ($env:SMOKE_EMAIL) {
    if (-not $env:SSE_CHECK_PASSWORD) { throw "SSE_CHECK_PASSWORD is required with SMOKE_EMAIL" }
    $composeFile = if ($env:COMPOSE_FILE) { $env:COMPOSE_FILE } else { "docker-compose.production.yml" }
    # Without SMOKE_STREAM_URL: plain HTTP on the compose network, where the Secure
    # session cookies go over it
    $target = if ($env:SMOKE_STREAM_URL) { @("--base-url", $env:SMOKE_STREAM_URL) } else { @("--internal", "--base-url", "http://frontend:3000") }
    docker compose -f $composeFile exec -T -e SSE_CHECK_PASSWORD backend `
        python -m scripts.check_sse_streaming @target --email $env:SMOKE_EMAIL
    if ($LASTEXITCODE -ne 0) { throw "The streaming check failed (exit $LASTEXITCODE)" }
} else {
    Write-Output "Skipping the streaming check (set SMOKE_EMAIL and SSE_CHECK_PASSWORD)."
}

Write-Output "Cognolith smoke checks passed."
