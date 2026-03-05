#!/usr/bin/env bash
# LAYER OS Session Handoff - MANDATORY execution at session end
# Usage: ./scripts/session_handoff.sh "agent-name" "Work summary" "next-task-1" "next-task-2"

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

# Parse arguments
AGENT_ID="${1:-unknown-agent}"
SUMMARY="${2:-No summary provided}"
shift 2 || true
NEXT_STEPS=("$@")

if [ -z "$SUMMARY" ] || [ "$SUMMARY" = "No summary provided" ]; then
    echo "❌ ERROR: Summary is required"
    echo ""
    echo "Usage: $0 AGENT_ID \"Summary\" \"next-task-1\" \"next-task-2\""
    echo ""
    echo "Example:"
    echo "  $0 \"claude-website-dev\" \\"
    echo "    \"Completed website redesign and backend CMS\" \\"
    echo "    \"Deploy to GCP VM\" \\"
    echo "    \"Test production environment\""
    exit 1
fi

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  LAYER OS Session Handoff - Recording Session                 ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Agent ID: $AGENT_ID"
echo "Summary: $SUMMARY"
echo "Next Steps: ${#NEXT_STEPS[@]} tasks"
echo ""

# Build next-steps arguments
NEXT_ARGS=()
for step in "${NEXT_STEPS[@]}"; do
    NEXT_ARGS+=("--next-steps" "$step")
done

REPORT_ARGS=()
for step in "${NEXT_STEPS[@]}"; do
    REPORT_ARGS+=("--next-step" "$step")
done

# Run handoff.py
if python3 core/system/handoff.py --handoff \
    --agent-id "$AGENT_ID" \
    --summary "$SUMMARY" \
    "${NEXT_ARGS[@]}"; then
    echo ""
    echo "✅ Session handoff recorded successfully"
else
    echo ""
    echo "❌ FATAL: Handoff failed"
    exit 1
fi

# Generate compact report (summary + 개선/다음 단계)
if python3 core/system/compact_report.py \
    --agent-id "$AGENT_ID" \
    --summary "$SUMMARY" \
    --improvement-from-next \
    "${REPORT_ARGS[@]}"; then
    echo "✅ Compact report generated"
else
    echo "⚠️  WARNING: Compact report generation failed (non-blocking)"
fi

# Verify QUANTA was updated
QUANTA_FILE="knowledge/agent_hub/state.md"
QUANTA_AGE=$(( $(date +%s) - $(stat -f %m "$QUANTA_FILE" 2>/dev/null || stat -c %Y "$QUANTA_FILE") ))

if [ $QUANTA_AGE -lt 60 ]; then
    echo "✅ state.md updated (${QUANTA_AGE}s ago)"
else
    echo "⚠️  WARNING: QUANTA was not updated recently"
fi

# Update session task telemetry (non-blocking)
python3 core/system/session_state.py \
    --event finish \
    --agent-id "$AGENT_ID" \
    --task-label "${SUMMARY:0:120}" \
    --session-id "${SESSION_ID:-}" \
    --summary "$SUMMARY" >/dev/null 2>&1 || true

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║  ✅ Session Handoff Complete                                  ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "Safe to commit and push. Next session will continue from here."
echo ""
