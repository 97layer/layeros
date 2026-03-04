#!/usr/bin/env bash
# Team entrypoint for web rebuild preflight

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

if [[ "${SKIP_BOOTSTRAP:-0}" != "1" ]]; then
  bash core/scripts/session_bootstrap.sh
fi

PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python3"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

"$PYTHON_BIN" core/scripts/web_rebuild_prep.py "$@"
