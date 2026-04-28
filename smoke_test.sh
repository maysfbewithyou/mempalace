#!/usr/bin/env bash
# MemPalace IEP fork — Phase 2 smoke tests
# version: 0.1
# usage: ./smoke_test.sh <base_url> <bearer_token>
#   example local:  ./smoke_test.sh http://localhost:8000 "$TOKEN"
#   example tunnel: ./smoke_test.sh https://mempalace.tstly.dev "$TOKEN"
#
# Implements the 5 checks from Phase 2 Architecture v0.2 §8:
#   1. /health → 200 ok
#   2. /mcp without auth → 401
#   3. /mcp with valid bearer + initialize → valid MCP response
#   4. /mcp tools/list → returns the upstream's mempalace_* tool list
#   5. (printed instructions for manual Cowork verification)

set -euo pipefail

BASE="${1:-http://localhost:8000}"
TOKEN="${2:-}"

if [ -z "$TOKEN" ]; then
    echo "ERROR: bearer token required as second argument." >&2
    echo "Usage: $0 <base_url> <bearer_token>" >&2
    exit 2
fi

PASS=0
FAIL=0

green() { printf '\033[32m%s\033[0m' "$*"; }
red()   { printf '\033[31m%s\033[0m' "$*"; }
bold()  { printf '\033[1m%s\033[0m' "$*"; }

ok()   { green "✓"; printf " %s\n" "$*"; PASS=$((PASS+1)); }
fail() { red   "✗"; printf " %s\n" "$*"; FAIL=$((FAIL+1)); }

bold "MemPalace smoke test against $BASE"; echo

# ── 1. /health (no auth) → 200 ok ────────────────────────────────────
echo "1/4  GET  $BASE/health"
status=$(curl -s -o /tmp/smoke_health.txt -w "%{http_code}" "$BASE/health")
body=$(cat /tmp/smoke_health.txt 2>/dev/null || echo "")
if [ "$status" = "200" ] && [ "$body" = "ok" ]; then
    ok "health endpoint returns 200 ok"
else
    fail "health endpoint expected 200/ok, got $status / '$body'"
fi
echo

# ── 2. /mcp without auth → 401 ────────────────────────────────────────
echo "2/4  POST $BASE/mcp  (no Authorization header)"
status=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' "$BASE/mcp")
if [ "$status" = "401" ]; then
    ok "unauthenticated request rejected with 401"
else
    fail "expected 401 without auth, got $status"
fi
echo

# ── 3. /mcp initialize round-trip ─────────────────────────────────────
echo "3/4  POST $BASE/mcp  (initialize, with bearer)"
init_resp=$(curl -s -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":"init-1","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke-test","version":"0.1"}}}' \
    "$BASE/mcp")
if echo "$init_resp" | grep -q '"id":"init-1"'; then
    ok "initialize round-trip succeeded"
else
    fail "initialize response unexpected"
    echo "    response: $init_resp"
fi
echo

# ── 4. /mcp tools/list returns mempalace_* tools ──────────────────────
echo "4/4  POST $BASE/mcp  (tools/list, with bearer)"
tools_resp=$(curl -s -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":"tools-1","method":"tools/list","params":{}}' \
    "$BASE/mcp")
tool_count=$(echo "$tools_resp" | grep -o '"mempalace_' | wc -l | tr -d ' ')
if [ "$tool_count" -ge 8 ]; then
    ok "tools/list returned $tool_count mempalace_* tools (expected ≥8)"
else
    fail "tools/list returned only $tool_count mempalace_* tools (expected ≥8)"
    echo "    response: $tools_resp"
fi
echo

# ── 5. Cowork manual verification (printed, not automated) ────────────
echo "5/4  Manual: register the bearer-MCP in Cowork pointed at $BASE/mcp"
echo "     and run a mempalace_status query. (Not automated — perform from"
echo "     the Cowork client once smoke tests 1-4 are green.)"
echo

# ── Summary ──────────────────────────────────────────────────────────
echo
bold "Summary"; echo
echo "  passed: $PASS"
echo "  failed: $FAIL"
echo
if [ "$FAIL" -eq 0 ]; then
    green "ALL AUTOMATED CHECKS PASSED"; echo
    exit 0
else
    red   "FAILURES PRESENT"; echo
    exit 1
fi
