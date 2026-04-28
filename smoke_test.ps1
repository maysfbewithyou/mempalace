# MemPalace IEP fork — Phase 2 smoke tests (PowerShell version)
# version: 0.1
# usage:
#   .\smoke_test.ps1 -BaseUrl http://localhost:8000 -Token <token>
#   .\smoke_test.ps1 -BaseUrl https://mempalace.tstly.dev -Token <token>
#
# Equivalent to smoke_test.sh but native to Matt's Windows environment.
# Implements the 4 automated checks from Phase 2 Architecture v0.2 §8.

param(
    [Parameter(Mandatory = $true)] [string] $BaseUrl,
    [Parameter(Mandatory = $true)] [string] $Token
)

$ErrorActionPreference = 'Continue'
$pass = 0
$fail = 0

function Write-Pass($msg) { Write-Host "  PASS  $msg" -ForegroundColor Green; $script:pass++ }
function Write-Fail($msg) { Write-Host "  FAIL  $msg" -ForegroundColor Red;   $script:fail++ }

Write-Host "MemPalace smoke test against $BaseUrl" -ForegroundColor Cyan
Write-Host ""

# 1. /health
Write-Host "1/4  GET  $BaseUrl/health"
try {
    $r = Invoke-WebRequest -Uri "$BaseUrl/health" -Method GET -UseBasicParsing -TimeoutSec 10
    if ($r.StatusCode -eq 200 -and $r.Content.Trim() -eq 'ok') {
        Write-Pass "health endpoint returns 200 ok"
    } else {
        Write-Fail "expected 200/ok, got $($r.StatusCode) / '$($r.Content)'"
    }
} catch {
    Write-Fail "health request failed: $($_.Exception.Message)"
}
Write-Host ""

# 2. /mcp without auth -> 401
Write-Host "2/4  POST $BaseUrl/mcp  (no Authorization header)"
try {
    $body = @{ jsonrpc = "2.0"; id = 1; method = "tools/list" } | ConvertTo-Json -Compress
    $r = Invoke-WebRequest -Uri "$BaseUrl/mcp" -Method POST -Body $body `
        -ContentType "application/json" -UseBasicParsing -TimeoutSec 10 -SkipHttpErrorCheck
    if ($r.StatusCode -eq 401) {
        Write-Pass "unauthenticated request rejected with 401"
    } else {
        Write-Fail "expected 401 without auth, got $($r.StatusCode)"
    }
} catch {
    Write-Fail "no-auth request failed unexpectedly: $($_.Exception.Message)"
}
Write-Host ""

# 3. /mcp initialize with bearer
Write-Host "3/4  POST $BaseUrl/mcp  (initialize, with bearer)"
try {
    $body = @{
        jsonrpc = "2.0"
        id      = "init-1"
        method  = "initialize"
        params  = @{
            protocolVersion = "2024-11-05"
            capabilities    = @{}
            clientInfo      = @{ name = "smoke-test"; version = "0.1" }
        }
    } | ConvertTo-Json -Compress -Depth 5
    $r = Invoke-WebRequest -Uri "$BaseUrl/mcp" -Method POST -Body $body `
        -Headers @{ Authorization = "Bearer $Token" } `
        -ContentType "application/json" -UseBasicParsing -TimeoutSec 30
    if ($r.StatusCode -eq 200 -and $r.Content -match '"id"\s*:\s*"init-1"') {
        Write-Pass "initialize round-trip succeeded"
    } else {
        Write-Fail "initialize response unexpected"
        Write-Host "    response: $($r.Content)" -ForegroundColor DarkGray
    }
} catch {
    Write-Fail "initialize request failed: $($_.Exception.Message)"
}
Write-Host ""

# 4. /mcp tools/list returns mempalace_* tools
Write-Host "4/4  POST $BaseUrl/mcp  (tools/list, with bearer)"
try {
    $body = @{ jsonrpc = "2.0"; id = "tools-1"; method = "tools/list"; params = @{} } | ConvertTo-Json -Compress -Depth 3
    $r = Invoke-WebRequest -Uri "$BaseUrl/mcp" -Method POST -Body $body `
        -Headers @{ Authorization = "Bearer $Token" } `
        -ContentType "application/json" -UseBasicParsing -TimeoutSec 30
    $count = ([regex]::Matches($r.Content, '"mempalace_')).Count
    if ($count -ge 8) {
        Write-Pass "tools/list returned $count mempalace_* tools (expected >=8)"
    } else {
        Write-Fail "tools/list returned only $count mempalace_* tools (expected >=8)"
        Write-Host "    response: $($r.Content)" -ForegroundColor DarkGray
    }
} catch {
    Write-Fail "tools/list request failed: $($_.Exception.Message)"
}
Write-Host ""

# 5. Cowork manual verification — printed instructions only
Write-Host "5/4  Manual: register the bearer-MCP in Cowork pointed at $BaseUrl/mcp"
Write-Host "     and run a mempalace_status query."
Write-Host ""

Write-Host "Summary" -ForegroundColor Cyan
Write-Host "  passed: $pass"
Write-Host "  failed: $fail"
Write-Host ""
if ($fail -eq 0) {
    Write-Host "ALL AUTOMATED CHECKS PASSED" -ForegroundColor Green
    exit 0
} else {
    Write-Host "FAILURES PRESENT" -ForegroundColor Red
    exit 1
}
