#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PLAN_COUNCIL_SCRIPT="${PLAN_DISPATCH_COUNCIL_SCRIPT:-$PROJECT_ROOT/core/system/plan_council.py}"
PLAN_CLASSIFIER_SCRIPT="${PLAN_DISPATCH_CLASSIFIER_SCRIPT:-$PROJECT_ROOT/core/system/plan_dispatch_classifier.py}"
PLAN_METRICS_SCRIPT="$PROJECT_ROOT/core/system/plan_dispatch_metrics.py"
PLAN_COUNCIL_LITE_SCRIPT="${PLAN_DISPATCH_COUNCIL_LITE_SCRIPT:-$PROJECT_ROOT/core/scripts/plan_council_lite.py}"
PLAN_METRICS_LOG="${PLAN_DISPATCH_METRICS_LOG:-$PROJECT_ROOT/knowledge/system/plan_dispatch_metrics.jsonl}"
PLAN_PENDING_LOG="${PLAN_DISPATCH_PENDING_LOG:-$PROJECT_ROOT/knowledge/system/plan_dispatch_pending.jsonl}"
PLAN_PENDING_LOCK="${PLAN_DISPATCH_PENDING_LOCK:-$PROJECT_ROOT/knowledge/system/plan_dispatch_pending.lock}"
LOG_PENDING="${PLAN_DISPATCH_LOG_PENDING:-1}"
ENV_FILE="$PROJECT_ROOT/.env"
SAFE_ENV_EXPORT_SCRIPT="$PROJECT_ROOT/core/scripts/safe_env_export.py"

# Load .env safely (KEY=VALUE lines only) to avoid command execution side effects.
if [[ -f "$ENV_FILE" ]]; then
  if [[ -f "$SAFE_ENV_EXPORT_SCRIPT" ]]; then
    # shellcheck disable=SC2046
    eval "$(python3 "$SAFE_ENV_EXPORT_SCRIPT" --file "$ENV_FILE")"
  else
    while IFS= read -r raw || [[ -n "$raw" ]]; do
      line="${raw#"${raw%%[![:space:]]*}"}"
      [[ -z "$line" ]] && continue
      [[ "$line" == \#* ]] && continue
      if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
        key="${BASH_REMATCH[1]}"
        value="${BASH_REMATCH[2]}"
        if [[ "$value" =~ ^\"(.*)\"$ ]]; then
          value="${BASH_REMATCH[1]}"
        elif [[ "$value" =~ ^\'(.*)\'$ ]]; then
          value="${BASH_REMATCH[1]}"
        fi
        export "${key}=${value}"
      fi
    done < "$ENV_FILE"
  fi
fi

if [[ $# -lt 1 ]]; then
  echo "Usage: bash core/scripts/plan_dispatch.sh \"<task>\" [--auto|--manual] [--smoke]" >&2
  exit 2
fi

TASK="$1"
shift || true

MODE="auto"
SMOKE="0"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --auto)
      MODE="auto"
      ;;
    --manual)
      MODE="manual"
      ;;
    --smoke)
      SMOKE="1"
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
ALLOW_DEGRADED="${PLAN_DISPATCH_ALLOW_DEGRADED:-0}"
STRICT_RUNTIME="${PLAN_DISPATCH_STRICT_RUNTIME:-1}"
MIN_RELIABILITY="${PLAN_DISPATCH_MIN_RELIABILITY:-0.65}"
LOG_METRICS="${PLAN_DISPATCH_LOG_METRICS:-1}"
COUNCIL_RETRIES="${PLAN_DISPATCH_COUNCIL_RETRIES:-2}"
COUNCIL_RETRY_DELAY="${PLAN_DISPATCH_COUNCIL_RETRY_DELAY:-2}"
AUTO_LITE_FALLBACK="${PLAN_DISPATCH_AUTO_LITE_FALLBACK:-0}"
CLASSIFY_COMPLEXITY="unknown"
CLASSIFY_SCORE="0"
CLASSIFIER_FALLBACK="0"

log_dispatch_metric() {
  local phase="$1"
  local reason="$2"
  local executed="$3"
  local fallback_value="${4:-$CLASSIFIER_FALLBACK}"
  if [[ "$LOG_METRICS" != "1" ]]; then
    return 0
  fi
  if [[ ! -f "$PLAN_METRICS_SCRIPT" ]]; then
    return 0
  fi
  python3 "$PLAN_METRICS_SCRIPT" --append \
    --log "$PLAN_METRICS_LOG" \
    --task "$TASK" \
    --mode "$MODE" \
    --phase "$phase" \
    --reason "$reason" \
    --executed "$executed" \
    --complexity "$CLASSIFY_COMPLEXITY" \
    --score "$CLASSIFY_SCORE" \
    --fallback "$fallback_value" >/dev/null 2>&1 || true
}

append_pending_task() {
  local reason="$1"
  local retryable="${2:-true}"
  local raw_council="${3:-}"
  if [[ "$LOG_PENDING" != "1" ]]; then
    return 0
  fi

  python3 - "$PLAN_PENDING_LOG" "$TASK" "$MODE" "$reason" "$CLASSIFY_COMPLEXITY" "$CLASSIFY_SCORE" "$CLASSIFIER_FALLBACK" "$retryable" "$raw_council" "$PLAN_PENDING_LOCK" <<'PY'
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

try:
    import fcntl
except Exception:
    fcntl = None

pending_log = Path(sys.argv[1])
task = (sys.argv[2] or "").strip()
mode = (sys.argv[3] or "auto").strip().lower() or "auto"
reason = (sys.argv[4] or "unknown").strip().lower() or "unknown"
complexity = (sys.argv[5] or "unknown").strip().lower() or "unknown"
score_raw = (sys.argv[6] or "0").strip()
classifier_fallback = (sys.argv[7] or "").strip().lower() in {"1", "true", "yes", "y", "on"}
retryable = (sys.argv[8] or "").strip().lower() in {"1", "true", "yes", "y", "on"}
raw_council = (sys.argv[9] or "").strip()
lock_path = Path(sys.argv[10]) if len(sys.argv) > 10 else pending_log.with_suffix(".lock")

try:
    score = int(score_raw)
except Exception:
    score = 0

task_hash = hashlib.sha1(task.encode("utf-8")).hexdigest()[:12] if task else ""
council: Dict[str, Any] = {}
if raw_council:
    try:
        parsed = json.loads(raw_council)
        if isinstance(parsed, dict):
            council = parsed
    except Exception:
        council = {}

consensus = council.get("consensus") if isinstance(council.get("consensus"), dict) else {}
runtime = consensus.get("runtime") if isinstance(consensus.get("runtime"), dict) else {}
entry = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "task_hash": task_hash,
    "task_preview": task[:140],
    "task": task[:800],
    "mode": mode,
    "reason": reason,
    "complexity": complexity,
    "score": score,
    "classifier_fallback": classifier_fallback,
    "retryable": retryable,
    "consensus_status": str(consensus.get("status", "")).strip().lower(),
    "gate_recommendation": str(runtime.get("gate_recommendation", "")).strip().lower(),
    "models_used": consensus.get("models_used", []) if isinstance(consensus.get("models_used"), list) else [],
}

pending_log.parent.mkdir(parents=True, exist_ok=True)
lock_path.parent.mkdir(parents=True, exist_ok=True)

def _append_line() -> None:
    with pending_log.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(entry, ensure_ascii=False) + "\n")

if fcntl is None:
    _append_line()
else:
    with lock_path.open("a+", encoding="utf-8") as lock_fp:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
        try:
            _append_line()
        finally:
            fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)
PY
}

if [[ ! -f "$PLAN_COUNCIL_SCRIPT" ]]; then
  log_dispatch_metric "error" "plan_council_missing" "false"
  append_pending_task "plan_council_missing" "false" ""
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

if [[ -f "$PLAN_CLASSIFIER_SCRIPT" ]]; then
  CLASSIFY_JSON="$(python3 "$PLAN_CLASSIFIER_SCRIPT" \
    --task "$TASK" \
    --min-complexity "$MIN_COMPLEXITY" \
    --json 2>/dev/null || true)"
fi

if [[ -n "${CLASSIFY_JSON:-}" ]]; then
  if ! python3 - "$CLASSIFY_JSON" >/dev/null 2>&1 <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
if not isinstance(payload, dict):
    raise ValueError("classifier output must be object")
required = {"complexity", "score", "level", "threshold", "allowed"}
missing = [key for key in required if key not in payload]
if missing:
    raise ValueError(f"classifier output missing keys: {missing}")
PY
  then
    CLASSIFY_JSON=""
  fi
fi

if [[ -z "${CLASSIFY_JSON:-}" ]]; then
  CLASSIFIER_FALLBACK="1"
  CLASSIFY_JSON="$(python3 - "$MIN_COMPLEXITY" <<'PY'
import json
import sys

min_complexity = (sys.argv[1] or "medium").strip().lower()
threshold_map = {"simple": 0, "medium": 1, "high": 2}
threshold = threshold_map.get(min_complexity, 1)
print(json.dumps({
    "complexity": "simple",
    "score": 0,
    "level": 0,
    "threshold": threshold,
    "allowed": False,
    "signals": ["classifier_fallback_or_invalid"],
}, ensure_ascii=False))
PY
)"
fi

CLASSIFY_META="$(python3 - "$CLASSIFY_JSON" <<'PY'
import json
import sys
payload = json.loads(sys.argv[1])
complexity = str(payload.get("complexity", "unknown")).strip().lower() or "unknown"
score = payload.get("score", 0)
try:
    score = int(score)
except Exception:
    score = 0
print(f"{complexity}\t{score}")
PY
)"
CLASSIFY_COMPLEXITY="${CLASSIFY_META%%$'\t'*}"
CLASSIFY_SCORE="${CLASSIFY_META#*$'\t'}"

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
  log_dispatch_metric "skip" "${skip_reason:-simple_task}" "false"
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

if [[ "$SMOKE" == "1" ]]; then
  if [[ "$should_execute" == "1" ]]; then
    log_dispatch_metric "smoke" "smoke_mode" "true"
  else
    log_dispatch_metric "smoke" "${skip_reason:-smoke_mode_skipped}" "false"
  fi
  python3 - "$TASK" "$MODE" "$CLASSIFY_JSON" "$should_execute" "$skip_reason" <<'PY'
import json
import sys
from datetime import datetime, timedelta, timezone

task = sys.argv[1]
mode = sys.argv[2]
classifier = json.loads(sys.argv[3])
should_execute = (sys.argv[4] == "1")
skip_reason = (sys.argv[5] or "").strip()
now = datetime.now(timezone.utc)
expires = now + timedelta(minutes=10)

payload = {
    "timestamp": now.isoformat(),
    "mode": "preflight",
    "task": task,
    "claude": {"ok": mode == "manual", "error": "smoke_mode", "plan": None},
    "gemini": {"ok": mode == "manual", "error": "smoke_mode", "plan": None},
    "consensus": {
        "status": "smoke",
        "models_used": ["smoke"],
        "planner_primary": "claude",
        "verifier_secondary": "gemini",
        "intent": task[:120],
        "approach": "Smoke mode: dispatcher/contract integrity check only (no live model call).",
        "steps": ["Validate dispatcher payload schema", "Validate manual execution branch"],
        "risks": ["No live model connectivity verification in smoke mode"],
        "checks": ["Run without --smoke for live council check before real implementation"],
        "tools": ["plan_dispatch"],
        "decision": "go",
        "decision_conflict": False,
        "runtime": {
            "gate_recommendation": "go",
            "reliability_score": 1.0,
            "reliability_tier": "high",
            "generated_at_utc": now.isoformat(),
            "expires_at_utc": expires.isoformat(),
            "ttl_seconds": 600,
            "stability_window": 0,
            "unstable": False,
        },
    },
}
payload["dispatcher"] = {
    "mode": mode,
    "executed": should_execute,
    "reason": "smoke_mode" if should_execute else (skip_reason or "smoke_mode_skipped"),
    "complexity": classifier.get("complexity", "unknown"),
    "score": classifier.get("score", 0),
}
print(json.dumps(payload, ensure_ascii=False))
PY
  exit 0
fi

# exit code 계약: 0=go, 1=hard_stop, 2=needs_clarification, 3=degraded_or_caution
COUNCIL_JSON=""
COUNCIL_EXIT=0
if [[ ! "$COUNCIL_RETRIES" =~ ^[0-9]+$ ]] || [[ "$COUNCIL_RETRIES" -lt 1 ]]; then
  COUNCIL_RETRIES=2
fi

for ((attempt=1; attempt<=COUNCIL_RETRIES; attempt++)); do
  COUNCIL_EXIT=0
  COUNCIL_JSON="$(python3 "$PLAN_COUNCIL_SCRIPT" --task "$TASK" --mode preflight --json 2>/dev/null)" || COUNCIL_EXIT=$?

  # 1=hard_stop(둘 다 실패) 케이스만 재시도 대상
  if [[ "$COUNCIL_EXIT" -ne 1 ]]; then
    break
  fi
  if [[ "$attempt" -lt "$COUNCIL_RETRIES" ]]; then
    sleep "$COUNCIL_RETRY_DELAY"
  fi
done

if [[ "$COUNCIL_EXIT" -eq 1 ]]; then
  if [[ "$AUTO_LITE_FALLBACK" == "1" && -f "$PLAN_COUNCIL_LITE_SCRIPT" ]]; then
    LITE_JSON="$(python3 "$PLAN_COUNCIL_LITE_SCRIPT" --task "$TASK" --json 2>/dev/null || true)"
    if [[ -n "${LITE_JSON:-}" ]]; then
      log_dispatch_metric "blocked" "hard_stop_fallback_lite" "false" "1"
      append_pending_task "hard_stop_fallback_lite" "true" "$LITE_JSON"
      echo "━━━ PLAN COUNCIL: DEGRADED-LITE FALLBACK ━━━" >&2
      echo "두 모델 모두 실패하여 offline fallback 기록을 사용합니다. (승인 후 진행 권장)" >&2
      python3 - "$TASK" "$MODE" "$CLASSIFY_JSON" "$LITE_JSON" <<'PY'
import json
import sys

task = sys.argv[1]
mode = sys.argv[2]
classifier = json.loads(sys.argv[3])
raw_lite = (sys.argv[4] or "").strip()

try:
    payload = json.loads(raw_lite)
except Exception:
    payload = {
        "timestamp": "",
        "mode": "preflight-lite",
        "task": task,
        "consensus": {
            "status": "degraded-lite",
            "models_used": [],
            "planner_primary": "offline",
            "verifier_secondary": "offline",
            "intent": task[:120],
            "approach": "offline fallback parse failed",
            "steps": [],
            "risks": ["plan_council_lite parse failed"],
            "checks": [],
            "decision": "go",
        },
    }

payload["dispatcher"] = {
    "mode": mode,
    "executed": True,
    "reason": "hard_stop_fallback_lite",
    "complexity": classifier.get("complexity", "unknown"),
    "score": classifier.get("score", 0),
}

print(json.dumps(payload, ensure_ascii=False))
PY
      exit 3
    fi
  fi

  log_dispatch_metric "blocked" "hard_stop_model_unavailable" "false"
  append_pending_task "hard_stop_model_unavailable" "true" "$COUNCIL_JSON"
  echo "━━━ PLAN COUNCIL: HARD STOP ━━━" >&2
  echo "두 모델 모두 호출 실패 (네트워크/키 오류)." >&2
  echo "구현 금지. 원인 확인 후 재시도하세요. (retries=${COUNCIL_RETRIES})" >&2
  echo "self-check: python3 core/system/plan_council.py --self-check --require-both" >&2
  exit 1
fi

if [[ "$COUNCIL_EXIT" -eq 2 ]]; then
  log_dispatch_metric "blocked" "needs_clarification_model" "false"
  append_pending_task "needs_clarification_model" "false" "$COUNCIL_JSON"
  echo "━━━ PLAN COUNCIL: NEEDS CLARIFICATION ━━━" >&2
  echo "Claude/Gemini 모두 범위 불명확으로 판정." >&2
  echo "사용자에게 요청 범위 확인 후 재실행하세요." >&2
  exit 2
fi

if [[ "$COUNCIL_EXIT" -eq 3 ]]; then
  echo "━━━ PLAN COUNCIL: DEGRADED (한 모델만 응답) ━━━" >&2
  echo "단일 모델 기준으로 진행합니다. 리스크 주의." >&2
  if [[ "$ALLOW_DEGRADED" != "1" ]]; then
    log_dispatch_metric "blocked" "degraded_not_allowed" "false"
    append_pending_task "degraded_not_allowed" "true" "$COUNCIL_JSON"
    echo "명시적 승인/허용 없이 진행 금지. PLAN_DISPATCH_ALLOW_DEGRADED=1 설정 후 재실행하세요." >&2
    exit 3
  fi
fi

RUNTIME_GATE="$(python3 - "$COUNCIL_JSON" "$MIN_RELIABILITY" <<'PY'
import json
import sys

raw = (sys.argv[1] or "").strip()
min_reliability = float(sys.argv[2])

try:
    payload = json.loads(raw)
except Exception:
    print("hard_stop\tplan_council_response_parse_failed")
    raise SystemExit(0)

consensus = payload.get("consensus") or {}
runtime = consensus.get("runtime") or payload.get("runtime") or {}
action = str(runtime.get("gate_recommendation", "go")).strip().lower()
score = runtime.get("reliability_score")
unstable = bool(runtime.get("unstable", False))

try:
    score_val = float(score)
except Exception:
    score_val = 0.0

if score_val < min_reliability and action == "go":
    action = "caution"

reason = f"score={score_val:.3f}, unstable={str(unstable).lower()}"
print(f"{action}\t{reason}")
PY
)"

RUNTIME_ACTION="${RUNTIME_GATE%%$'\t'*}"
RUNTIME_REASON="${RUNTIME_GATE#*$'\t'}"

if [[ "$RUNTIME_ACTION" == "hard_stop" ]]; then
  log_dispatch_metric "blocked" "runtime_hard_stop" "false"
  append_pending_task "runtime_hard_stop" "true" "$COUNCIL_JSON"
  echo "━━━ PLAN COUNCIL: HARD STOP (runtime gate) ━━━" >&2
  echo "$RUNTIME_REASON" >&2
  exit 1
fi

if [[ "$RUNTIME_ACTION" == "needs_clarification" ]]; then
  log_dispatch_metric "blocked" "runtime_needs_clarification" "false"
  append_pending_task "runtime_needs_clarification" "false" "$COUNCIL_JSON"
  echo "━━━ PLAN COUNCIL: NEEDS CLARIFICATION (runtime gate) ━━━" >&2
  echo "$RUNTIME_REASON" >&2
  exit 2
fi

if [[ "$RUNTIME_ACTION" == "caution" && "$STRICT_RUNTIME" == "1" && "$ALLOW_DEGRADED" != "1" ]]; then
  log_dispatch_metric "blocked" "runtime_caution_not_allowed" "false"
  append_pending_task "runtime_caution_not_allowed" "true" "$COUNCIL_JSON"
  echo "━━━ PLAN COUNCIL: CAUTION (runtime gate) ━━━" >&2
  echo "$RUNTIME_REASON" >&2
  echo "신뢰도 부족 상태입니다. 승인/완화 설정 없이 진행 금지." >&2
  exit 3
fi

log_dispatch_metric "execute" "executed" "true"
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
