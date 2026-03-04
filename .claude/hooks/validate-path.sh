#!/bin/bash
# validate-path.sh — Write 후크: 금지 경로 검증
# PostToolUse(Write) 시 실행됨
#
# exit 2 = 위반 시 차단
# exit 0 = 통과

# stdin에서 JSON 읽기 (Claude Code가 stdin으로 전달)
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('tool_input',{}).get('file_path',''))" 2>/dev/null)

if [ -z "$FILE_PATH" ]; then
  exit 0
fi

PROJECT_ROOT="/Users/97layer/97layerOS"
REL_PATH="${FILE_PATH#$PROJECT_ROOT/}"

# 프로젝트 외부 파일은 무시
if [ "$REL_PATH" = "$FILE_PATH" ]; then
  exit 0
fi

BASENAME=$(basename "$REL_PATH")
DIRNAME=$(dirname "$REL_PATH")

# 1. 루트에 .md/.json/.txt 파일 (허용 리스트 외) — 차단
ALLOWED_ROOT_FILES="CLAUDE.md README.md AGENTS.md .ai_rules"
GUARD_RULES_PATH="$PROJECT_ROOT/knowledge/system/guard_rules.json"
if [ -f "$GUARD_RULES_PATH" ]; then
  LOADED_ROOT_FILES=$(python3 - "$GUARD_RULES_PATH" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
    allowed = data.get("allowed_root_files")
    if isinstance(allowed, list):
        names = [str(x).strip() for x in allowed if str(x).strip()]
        if names:
            print(" ".join(names))
except Exception:
    pass
PY
)
  if [ -n "$LOADED_ROOT_FILES" ]; then
    ALLOWED_ROOT_FILES="$LOADED_ROOT_FILES"
  fi
fi
if [ "$DIRNAME" = "." ]; then
  case "$BASENAME" in
    *.md|*.json|*.txt)
      # 허용 리스트 체크
      if ! printf "%s\n" $ALLOWED_ROOT_FILES | grep -Fxq "$BASENAME"; then
        echo "[ValidatePath] 🚫 BLOCKED: 루트에 파일 생성 금지 — $BASENAME (허용: $ALLOWED_ROOT_FILES)"
        exit 2
      fi
      ;;
  esac
fi

# 2. 금지 파일명 패턴 — 차단
case "$BASENAME" in
  SESSION_SUMMARY_*|WAKEUP_REPORT*|DEEP_WORK_PROGRESS*|DEPLOY_*|NEXT_STEPS*|audit_report_*|*_report_*.json)
    echo "[ValidatePath] 🚫 BLOCKED: 금지 파일명 패턴: $BASENAME"
    exit 2
    ;;
esac

# 3. 임시 파일명 — 차단
case "$BASENAME" in
  temp_*|untitled_*|무제*)
    echo "[ValidatePath] 🚫 BLOCKED: 임시 파일명 감지: $BASENAME"
    exit 2
    ;;
esac

exit 0
