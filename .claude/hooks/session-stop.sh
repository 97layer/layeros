#!/bin/bash
# session-stop.sh — Stop hook
# 세션 종료 시 state.md 갱신 상태 체크 + 핸드오프 리마인더
#
# exit 0 = 항상 통과

PROJECT_ROOT="/Users/97layer/97layerOS"
STATE="$PROJECT_ROOT/knowledge/agent_hub/state.md"

INPUT_JSON=$(cat)

echo "━━━ LAYER OS Session Stop ━━━"

# ─── state.md 갱신 시각 체크 ──────────────────────────────

if [ -f "$STATE" ]; then
  LAST_MOD=$(stat -f "%m" "$STATE" 2>/dev/null || stat -c "%Y" "$STATE" 2>/dev/null)
  NOW=$(date +%s)

  if [ -n "$LAST_MOD" ]; then
    DIFF=$(( (NOW - LAST_MOD) / 60 ))

    if [ "$DIFF" -gt 120 ]; then
      echo "⚠️  state.md 미갱신: ${DIFF}분 전 마지막 수정"
      echo "→ /handoff 실행을 권장합니다."
    elif [ "$DIFF" -gt 60 ]; then
      echo "state.md: ${DIFF}분 전 갱신 (갱신 권장)"
    else
      echo "state.md: ${DIFF}분 전 갱신 (정상)"
    fi
  fi
else
  echo "WARNING: state.md 파일 없음"
fi

# ─── 미커밋/미push 확인 ───────────────────────────────────

cd "$PROJECT_ROOT" 2>/dev/null || exit 0

UNCOMMITTED=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
UNPUSHED=$(git log @{u}.. --oneline 2>/dev/null | wc -l | tr -d ' ')

if [ "$UNCOMMITTED" -gt 0 ]; then
  echo "⚠️  미커밋 변경 ${UNCOMMITTED}개 있음"
fi

if [ "$UNPUSHED" -gt 0 ]; then
  echo "⚠️  미push 커밋 ${UNPUSHED}개 있음 → git push origin main"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ─── 토큰 사용량 추적 ─────────────────────────────────────

if [ -f "$PROJECT_ROOT/core/system/token_tracker.py" ]; then
  echo "$INPUT_JSON" | python3 "$PROJECT_ROOT/core/system/token_tracker.py" 2>&1
fi

# ─── state.md 자동 갱신 ───────────────────────────────────

if [ -f "$PROJECT_ROOT/core/system/auto_quanta_update.py" ]; then
  AGENT_ID=$(echo "$INPUT_JSON" | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get('agent_id', 'auto-session'))
except:
    print('auto-session')
" 2>/dev/null || echo "auto-session")

  python3 "$PROJECT_ROOT/core/system/auto_quanta_update.py" --agent-id "$AGENT_ID" 2>&1
fi

# ─── decision_log 세션 요약 ───────────────────────
DECISION_LOG="$PROJECT_ROOT/knowledge/system/decision_log.jsonl"
SESSION_TS=$(date -u +"%Y-%m-%dT%H:%M:%S")
TODAY=$(date +%Y-%m-%d)
SESSION_DECISIONS=0
if [ -f "$DECISION_LOG" ]; then
    SESSION_DECISIONS=$(grep -c "\"$TODAY" "$DECISION_LOG" 2>/dev/null || echo 0)
fi
python3 - <<PYEOF
import json
from pathlib import Path
log_path = Path("$DECISION_LOG")
record = {
    "ts": "$SESSION_TS", "type": "session_summary",
    "actor": "session-stop", "id": "auto-session",
    "title": "세션 종료",
    "meta": {"session_decisions_today": $SESSION_DECISIONS, "uncommitted": $UNCOMMITTED}
}
log_path.parent.mkdir(parents=True, exist_ok=True)
with open(log_path, 'a', encoding='utf-8') as f:
    f.write(json.dumps(record, ensure_ascii=False) + '\n')
PYEOF

exit 0
