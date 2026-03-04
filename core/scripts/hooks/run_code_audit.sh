#!/usr/bin/env bash
# Lightweight pre-commit/pre-push helper for code_audit.
# Usage: core/scripts/hooks/run_code_audit.sh [--scan-all] [--warn-only]

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"

# Guardrail linkage must pass before running content/path audit.
python3 "$REPO_ROOT/core/system/agents_guardrail_trace.py" --check

python3 "$REPO_ROOT/core/scripts/code_audit.py" "$@"
