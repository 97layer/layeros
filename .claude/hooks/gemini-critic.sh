#!/bin/bash
# PostToolUse: Edit/Write 후 Gemini가 변경된 .py 파일 자동 리뷰
INPUT=$(cat)
PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec python3 "$PROJECT_ROOT/.claude/hooks/gemini_critic.py" "$PROJECT_ROOT" <<< "$INPUT"
