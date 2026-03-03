#!/bin/bash
# session-start.sh — SessionStart hook
# state.md 전체 출력 + work_lock 체크

PROJECT_ROOT="/Users/97layer/97layerOS"
STATE="$PROJECT_ROOT/knowledge/agent_hub/state.md"
WORK_LOCK="$PROJECT_ROOT/knowledge/system/work_lock.json"

# 세션 시작 시각 기록 (auto_quanta_update.py가 커밋 경계로 사용)
date -u +"%Y-%m-%dT%H:%M:%SZ" > "$PROJECT_ROOT/knowledge/system/session_start.txt"

echo "━━━ LAYER OS Session Start ━━━"

# ─── STATE 전체 출력 ──────────────────────────────────────

if [ -f "$STATE" ]; then
  cat "$STATE"
else
  echo "WARNING: state.md 파일 없음 — $STATE"
fi

echo ""

# ─── work_lock 상태 ───────────────────────────────────────

if [ -f "$WORK_LOCK" ]; then
  python3 - "$WORK_LOCK" <<'PYEOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    if d.get('locked'):
        print(f"⚠️  WORK LOCK ACTIVE — Agent: {d.get('agent_id','unknown')}, Task: {d.get('task','unknown')}")
        print("다른 에이전트가 작업 중입니다. 충돌 주의.")
    else:
        print("work_lock: unlocked")
except Exception as e:
    print(f"work_lock: 파싱 오류 ({e})")
PYEOF
else
  echo "work_lock: 파일 없음 (정상)"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ─── 브랜드 SSOT 자동 로드 ─────────────────────────────────

SAGE="$PROJECT_ROOT/directives/sage_architect.md"
ORIGIN="$PROJECT_ROOT/directives/the_origin.md"
PRACTICE="$PROJECT_ROOT/directives/practice.md"

for FILE in "$ORIGIN" "$SAGE" "$PRACTICE"; do
  if [ -f "$FILE" ]; then
    echo ""
    echo "━━━ DIRECTIVES: $(basename $FILE) ━━━"
    cat "$FILE"
  fi
done

# ─── 구조 감사 (선제 스캔) ──────────────────────────────────

AUDIT_SCRIPT="$PROJECT_ROOT/core/scripts/structure_audit.py"
if [ -f "$AUDIT_SCRIPT" ]; then
  python3 "$AUDIT_SCRIPT" 2>/dev/null
fi

exit 0
