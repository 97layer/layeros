#!/usr/bin/env bash
# Wrapper to enforce web_consistency_lock around a command.
# Usage: web_lock_guardian.sh "task description" -- <command> [args]

set -euo pipefail

if [[ $# -lt 3 || $2 != "--" ]]; then
  echo "Usage: $0 \"task description\" -- <command> [args]" >&2
  exit 2
fi

TASK="$1"
shift 2

python3 "$(dirname "$0")/../system/web_consistency_lock.py" --acquire AGENT --task "$TASK"
python3 "$(dirname "$0")/../system/web_consistency_lock.py" --validate AGENT

set +e
"$@"
CMD_STATUS=$?
set -e

python3 "$(dirname "$0")/../system/web_consistency_lock.py" --release AGENT

exit $CMD_STATUS
