#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PLAN_COUNCIL_SCRIPT="$PROJECT_ROOT/core/system/plan_council.py"

if [[ $# -lt 1 ]]; then
  echo "Usage: bash core/scripts/plan_dispatch.sh \"<task>\" [--auto|--manual]" >&2
  exit 2
fi

TASK="$1"
shift || true

MODE="auto"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --auto)
      MODE="auto"
      ;;
    --manual)
      MODE="manual"
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
  shift
done

AUTO_ENABLED="${PLAN_COUNCIL_AUTO:-1}"
MIN_COMPLEXITY="${PLAN_COUNCIL_MIN_COMPLEXITY:-medium}"

if [[ ! -f "$PLAN_COUNCIL_SCRIPT" ]]; then
  python3 - "$TASK" "$MODE" <<'PY'
import json
import sys

task = sys.argv[1]
mode = sys.argv[2]
payload = {
    "dispatcher": {
        "mode": mode,
        "executed": False,
        "reason": "plan_council_missing",
        "complexity": "unknown",
        "score": 0,
    },
    "consensus": {
        "status": "degraded",
        "models_used": [],
        "planner_primary": "claude",
        "verifier_secondary": "gemini",
        "intent": task[:120],
        "approach": "plan_council.py missing",
        "steps": [
            "Break the request into concrete work units",
            "Inspect related files and dependencies",
            "Implement and run validation checks",
        ],
        "risks": ["plan_council.py missing"],
        "checks": [
            "Restore core/system/plan_council.py",
            "Re-run session bootstrap until READY",
        ],
        "tools": [],
        "decision": "go",
        "decision_conflict": False,
    },
}
print(json.dumps(payload, ensure_ascii=False))
PY
  exit 0
fi

CLASSIFY_JSON="$(python3 - "$TASK" "$MIN_COMPLEXITY" <<'PY'
import json
import re
import sys

task = sys.argv[1].strip()
min_complexity = (sys.argv[2] or "medium").strip().lower()

score = 0
if len(task) >= 90:
    score += 2
if len(task) >= 180:
    score += 1

keyword_pat = (
    r"(리팩토링|아키텍처|구조 변경|대규모|하네스|파이프라인|통합|연동|"
    r"마이그레이션|다중 파일|여러 파일|전면|재설계|migration|refactor|pipeline|architecture)"
)
if re.search(keyword_pat, task, flags=re.IGNORECASE):
    score += 2

if "그리고" in task or "," in task or " + " in task:
    score += 1

if score >= 4:
    complexity = "high"
    level = 2
elif score >= 2:
    complexity = "medium"
    level = 1
else:
    complexity = "simple"
    level = 0

threshold_map = {"simple": 0, "medium": 1, "high": 2}
threshold = threshold_map.get(min_complexity, 1)

print(json.dumps({
    "complexity": complexity,
    "score": score,
    "level": level,
    "threshold": threshold,
    "allowed": level >= threshold,
}, ensure_ascii=False))
PY
)"

should_execute="1"
skip_reason=""

if [[ "$MODE" == "auto" ]]; then
  if [[ "$AUTO_ENABLED" != "1" ]]; then
    should_execute="0"
    skip_reason="auto_disabled"
  else
    allowed="$(python3 - "$CLASSIFY_JSON" <<'PY'
import json
import sys
obj = json.loads(sys.argv[1])
print("1" if obj.get("allowed") else "0")
PY
)"
    if [[ "$allowed" != "1" ]]; then
      should_execute="0"
      skip_reason="simple_task"
    fi
  fi
fi

if [[ "$should_execute" != "1" ]]; then
  python3 - "$TASK" "$MODE" "$CLASSIFY_JSON" "$skip_reason" <<'PY'
import json
import sys

task = sys.argv[1]
mode = sys.argv[2]
classifier = json.loads(sys.argv[3])
reason = sys.argv[4]

payload = {
    "dispatcher": {
        "mode": mode,
        "executed": False,
        "reason": reason,
        "complexity": classifier.get("complexity", "simple"),
        "score": classifier.get("score", 0),
    },
    "consensus": {
        "status": "skipped",
        "models_used": [],
        "planner_primary": "claude",
        "verifier_secondary": "gemini",
        "intent": task[:120],
        "approach": "Plan Council skipped by dispatcher policy",
        "steps": [],
        "risks": [],
        "checks": [],
        "tools": [],
        "decision": "go",
        "decision_conflict": False,
    },
}
print(json.dumps(payload, ensure_ascii=False))
PY
  exit 0
fi

# exit code 계약: 0=go, 1=hard_stop, 2=needs_clarification, 3=degraded_single
COUNCIL_JSON=""
COUNCIL_EXIT=0
COUNCIL_JSON="$(python3 "$PLAN_COUNCIL_SCRIPT" --task "$TASK" --mode preflight --json 2>/dev/null)" || COUNCIL_EXIT=$?

if [[ "$COUNCIL_EXIT" -eq 1 ]]; then
  echo "━━━ PLAN COUNCIL: HARD STOP ━━━" >&2
  echo "두 모델 모두 호출 실패 (네트워크/키 오류)." >&2
  echo "구현 금지. 원인 확인 후 재시도하세요." >&2
  exit 1
fi

if [[ "$COUNCIL_EXIT" -eq 2 ]]; then
  echo "━━━ PLAN COUNCIL: NEEDS CLARIFICATION ━━━" >&2
  echo "Claude/Gemini 모두 범위 불명확으로 판정." >&2
  echo "사용자에게 요청 범위 확인 후 재실행하세요." >&2
  exit 2
fi

if [[ "$COUNCIL_EXIT" -eq 3 ]]; then
  echo "━━━ PLAN COUNCIL: DEGRADED (한 모델만 응답) ━━━" >&2
  echo "단일 모델 기준으로 진행합니다. 리스크 주의." >&2
fi

python3 - "$TASK" "$MODE" "$CLASSIFY_JSON" "$COUNCIL_JSON" <<'PY'
import json
import sys

task = sys.argv[1]
mode = sys.argv[2]
classifier = json.loads(sys.argv[3])
raw_council = (sys.argv[4] or "").strip()

payload = None
if raw_council:
    try:
        parsed = json.loads(raw_council)
        if isinstance(parsed, dict):
            payload = parsed
    except Exception:
        payload = None

if payload is None:
    payload = {
        "timestamp": "",
        "mode": "preflight",
        "task": task,
        "claude": {"ok": False, "error": "parse_failed", "plan": None},
        "gemini": {"ok": False, "error": "parse_failed", "plan": None},
        "consensus": {
            "status": "degraded",
            "models_used": [],
            "planner_primary": "claude",
            "verifier_secondary": "gemini",
            "intent": task[:120],
            "approach": "Plan Council call failed or returned invalid JSON",
            "steps": [
                "Break the request into concrete work units",
                "Inspect related files and dependencies",
                "Implement and run validation checks",
            ],
            "risks": ["Plan Council response parse failed"],
            "checks": [
                "core/system/plan_council.py --self-check --require-both",
                "Validate knowledge/system/plan_council_reports.jsonl integrity",
            ],
            "tools": [],
            "decision": "go",
            "decision_conflict": False,
        },
    }

payload["dispatcher"] = {
    "mode": mode,
    "executed": True,
    "reason": "executed",
    "complexity": classifier.get("complexity", "unknown"),
    "score": classifier.get("score", 0),
}

print(json.dumps(payload, ensure_ascii=False))
PY
