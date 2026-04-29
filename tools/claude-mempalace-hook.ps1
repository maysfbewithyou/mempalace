<#
  claude-mempalace-hook.ps1 — project-scoped Claude Code hook (D7)

  Reads the hook event JSON from stdin and writes a diary entry to the hosted
  MemPalace via mempalace_diary_write. Diaries are per-agent in MemPalace, so
  the hook uses a stable agent_name "claude-code" (separate from claude.ai
  "claude-web" diaries). The body string encodes wing/event/cwd as AAAK-style
  pipe-separated context.

  Failure mode: never block the session. Any error logged to
    %TEMP%\mempalace-hook.log; script exits 0.

  Version: v1.3 (2026-04-28) — corrected diary_write schema (agent_name + topic)
#>

$ErrorActionPreference = 'Continue'
$logFile = Join-Path $env:TEMP 'mempalace-hook.log'
$ts = (Get-Date).ToString('o')

function _Log($msg) {
  try { "$ts $msg" | Out-File -FilePath $logFile -Append -Encoding utf8 } catch {}
}

# Read stdin OUTSIDE try/catch so $input isn't pre-consumed
$raw = $null
try { $raw = [Console]::In.ReadToEnd() } catch {}
if (-not $raw) {
  try { $raw = ($input | Out-String) } catch {}
}

try {
  if (-not $raw) { _Log "no stdin"; exit 0 }
  $bom = [char]0xFEFF
  $raw = $raw.TrimStart($bom).Trim()
  if (-not $raw) { _Log "stdin empty after trim"; exit 0 }

  $evt = $raw | ConvertFrom-Json -ErrorAction Stop

  $event = "$($evt.hook_event_name)"
  $sid   = "$($evt.session_id)"
  $cwd   = "$($evt.cwd)"
  if (-not $cwd) { $cwd = (Get-Location).Path }
  $base  = Split-Path -Leaf $cwd

  # Wing routing — encoded into the diary entry body
  $wing = 'wing_atlas'
  if     ($cwd -match 'atlas|mempalace')         { $wing = 'wing_atlas' }
  elseif ($cwd -match 'IEP|Mays|interactep')     { $wing = 'wing_iep' }
  elseif ($cwd -match 'personal|aiTeach|Yugioh') { $wing = 'wing_personal' }

  $sidShort = if ($sid.Length -ge 8) { $sid.Substring(0,8) } else { $sid }
  # AAAK-flavored compact entry. Pipe-separated fields, ts ISO.
  $entry = "EVT:$event | WING:$wing | CWD:$base | SID:$sidShort | TS:$ts"
  $topic = "claude-code-$($event.ToLower())"

  $tokenFile = Join-Path $env:USERPROFILE '.mempalace_client\token'
  if (-not (Test-Path $tokenFile)) { _Log "token file missing"; exit 0 }
  $token = (Get-Content $tokenFile -Raw).Trim()

  $body = @{
    jsonrpc = '2.0'
    id      = 1
    method  = 'tools/call'
    params  = @{
      name      = 'mempalace_diary_write'
      arguments = @{
        agent_name = 'claude-code'
        entry      = $entry
        topic      = $topic
      }
    }
  } | ConvertTo-Json -Depth 6 -Compress

  $headers = @{
    'Authorization' = "Bearer $token"
    'Content-Type'  = 'application/json'
    'Accept'        = 'application/json, text/event-stream'
    'User-Agent'    = 'mempalace-hook/1.3'
  }

  $resp = Invoke-WebRequest -Uri 'https://claude-brain.tstly.dev/mcp' `
    -Method POST -Headers $headers -Body $body -UseBasicParsing -TimeoutSec 10
  _Log "ok event=$event wing=$wing topic=$topic http=$($resp.StatusCode)"
} catch {
  $first16 = ''
  if ($raw) { $first16 = $raw.Substring(0,[Math]::Min(16,$raw.Length)) }
  _Log "ERROR: $_ | first16=[$first16]"
}
exit 0
