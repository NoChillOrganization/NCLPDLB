#!/bin/bash
# PreToolUse security hook — blocks destructive Bash patterns before execution
input=$(cat)

cmd=$(echo "$input" | python3 -c "
import sys, json, re
try:
    d = json.load(sys.stdin)
    cmd = d.get('tool_input', {}).get('command', '')
    patterns = [
        r'^rm\s+-rf\s+[/~]',
        r'\|\s*\w*sh\b',
        r'>\s*/dev/',
    ]
    print('BLOCK' if any(re.search(p, cmd) for p in patterns) else 'OK')
except Exception:
    print('OK')
" 2>/dev/null || echo "OK")

if [ "$cmd" = "BLOCK" ]; then
    echo "[Security] Blocked dangerous command pattern" >&2
    exit 2
fi

echo "$input"
