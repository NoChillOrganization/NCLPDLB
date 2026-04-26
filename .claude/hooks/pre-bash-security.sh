#!/bin/bash
input=$(cat)

check_result=$(printf '%s' "$input" | python3 -c "
import sys, json, re
try:
    d = json.load(sys.stdin)
    cmd = d.get('tool_input', {}).get('command', '')
    print('BLOCK' if re.search(r'\|\s*(?:bash|sh|zsh|dash|ksh|csh|fish|tcsh)\b', cmd) else 'OK')
except Exception:
    print('BLOCK')
" 2>/dev/null) || { echo "[Security] Hook error — blocking command" >&2; exit 2; }

if [ "$check_result" = "BLOCK" ]; then
    echo "[Security] Blocked pipe-to-shell command pattern" >&2
    exit 2
fi

printf '%s' "$input"
