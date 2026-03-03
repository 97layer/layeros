#!/bin/bash
# PostToolUse Bash: git commit 시에만 staged .py 파일 Gemini 리뷰
INPUT=$(cat)
CMD=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('tool_input', {}).get('command', ''))
except:
    print('')
" 2>/dev/null)

# git commit 명령이 아니면 스킵
[[ "$CMD" != *"git commit"* ]] && exit 0

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec python3 "$PROJECT_ROOT/.claude/hooks/gemini_critic.py" "$PROJECT_ROOT" --staged
