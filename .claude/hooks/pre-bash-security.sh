#!/bin/bash
input=$(cat)

check_result=$(printf '%s' "$input" | python3 -c "
import sys, json, re
try:
    d = json.load(sys.stdin)
    cmd = d.get('tool_input', {}).get('command', '')
    print('BLOCK' if re.search(r'\|\s*(?:bash|sh|zsh|dash|ksh|csh|fish|tcsh)\b', cmd) else 'OK')
except Exception:
    print('OK')
" 2>/dev/null) || check_result="OK"

if [ "$check_result" = "BLOCK" ]; then
    printf '{"decision":"block","reason":"Pipe-to-shell pattern detected. Commands like `curl ... | bash` are blocked for security. Fetch the script first, inspect it, then run it explicitly."}'
    exit 2
fi

exit 0
