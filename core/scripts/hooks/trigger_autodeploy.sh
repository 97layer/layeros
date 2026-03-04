#!/usr/bin/env bash
# Push + deploy trigger called by post-commit hook.

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
LOG_FILE="/tmp/woohwahae-autodeploy.log"
LOCK_FILE="$REPO_ROOT/.git/woohwahae-autodeploy.lock"

cd "$REPO_ROOT"

timestamp() {
  date -u +"%Y-%m-%dT%H:%M:%SZ"
}

if [[ "${SKIP_LOCAL_HOOKS:-0}" == "1" ]]; then
  exit 0
fi

ENABLED="$(git config --bool --get woohwahae.autodeploy || echo false)"
if [[ "$ENABLED" != "true" ]]; then
  exit 0
fi

branch="$(git rev-parse --abbrev-ref HEAD)"
target_branch="$(git config --get woohwahae.autodeployBranch || echo main)"
if [[ "$branch" != "$target_branch" ]]; then
  echo "[$(timestamp)] skip: branch=$branch target=$target_branch" >>"$LOG_FILE"
  exit 0
fi

if [[ -e "$LOCK_FILE" ]]; then
  echo "[$(timestamp)] skip: lock_exists" >>"$LOG_FILE"
  exit 0
fi

echo "$$" >"$LOCK_FILE"
cleanup() {
  rm -f "$LOCK_FILE"
}
trap cleanup EXIT

sha="$(git rev-parse --short HEAD)"
echo "[$(timestamp)] start: branch=$branch sha=$sha" >>"$LOG_FILE"

if ! git push origin "$branch" >>"$LOG_FILE" 2>&1; then
  echo "[$(timestamp)] fail: git_push" >>"$LOG_FILE"
  exit 1
fi

deploy_target="$(git config --get woohwahae.autodeployTarget || echo all)"
if [[ "$deploy_target" == "none" ]]; then
  echo "[$(timestamp)] done: push_only" >>"$LOG_FILE"
  exit 0
fi

if ! bash core/scripts/deploy/deploy.sh "$deploy_target" >>"$LOG_FILE" 2>&1; then
  echo "[$(timestamp)] fail: deploy target=$deploy_target" >>"$LOG_FILE"
  exit 1
fi

echo "[$(timestamp)] done: deploy target=$deploy_target" >>"$LOG_FILE"

