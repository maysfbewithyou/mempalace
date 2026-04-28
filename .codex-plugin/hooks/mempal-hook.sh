#!/usr/bin/env bash
set -euo pipefail
HOOK_NAME="${1:?Usage: mempal-hook.sh <hook-name>}"

# Whitelist allowed hook names to prevent arbitrary command injection via hook arg
case "$HOOK_NAME" in
    session-start|stop|precompact) ;;
    *) echo "ERROR: Unknown hook name: $HOOK_NAME" >&2; exit 1 ;;
esac

INPUT_FILE=$(mktemp) || { echo "Failed to create temp file" >&2; exit 1; }
cat > "$INPUT_FILE"
cat "$INPUT_FILE" | python3 -m mempalace hook run --hook "$HOOK_NAME" --harness codex
EXIT_CODE=$?
rm -f "$INPUT_FILE" 2>/dev/null
exit $EXIT_CODE
