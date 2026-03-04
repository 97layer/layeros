#!/usr/bin/env bash
# Install repo-managed git hooks and auto deploy trigger settings.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

AUTO_DEPLOY=1
AUTO_DEPLOY_BRANCH="main"
AUTO_DEPLOY_TARGET="all"
PREPUSH_MODE="lite"

usage() {
  cat <<'EOF'
Usage:
  bash core/scripts/hooks/install_git_hooks.sh [options]

Options:
  --disable-autodeploy         Disable post-commit auto push/deploy
  --autodeploy-branch BRANCH   Branch to auto deploy from (default: main)
  --autodeploy-target TARGET   deploy.sh target (default: all, use none for push-only)
  --prepush-mode MODE          off|lite|full (default: lite)
  -h, --help                   Show help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --disable-autodeploy)
      AUTO_DEPLOY=0
      shift
      ;;
    --autodeploy-branch)
      AUTO_DEPLOY_BRANCH="${2:-$AUTO_DEPLOY_BRANCH}"
      shift 2
      ;;
    --autodeploy-target)
      AUTO_DEPLOY_TARGET="${2:-$AUTO_DEPLOY_TARGET}"
      shift 2
      ;;
    --prepush-mode)
      PREPUSH_MODE="${2:-$PREPUSH_MODE}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

case "$PREPUSH_MODE" in
  off|lite|full) ;;
  *)
    echo "Invalid --prepush-mode: $PREPUSH_MODE" >&2
    exit 1
    ;;
esac

cd "$REPO_ROOT"

chmod +x core/scripts/hooks/pre-commit \
  core/scripts/hooks/pre-push \
  core/scripts/hooks/post-commit \
  core/scripts/hooks/trigger_autodeploy.sh \
  core/scripts/hooks/run_code_audit.sh

git config core.hooksPath core/scripts/hooks
git config --bool woohwahae.autodeploy "$([[ "$AUTO_DEPLOY" -eq 1 ]] && echo true || echo false)"
git config woohwahae.autodeployBranch "$AUTO_DEPLOY_BRANCH"
git config woohwahae.autodeployTarget "$AUTO_DEPLOY_TARGET"
git config woohwahae.prepushMode "$PREPUSH_MODE"

echo "[hooks] installed: core.hooksPath=core/scripts/hooks"
echo "[hooks] woohwahae.autodeploy=$(git config --get woohwahae.autodeploy)"
echo "[hooks] woohwahae.autodeployBranch=$(git config --get woohwahae.autodeployBranch)"
echo "[hooks] woohwahae.autodeployTarget=$(git config --get woohwahae.autodeployTarget)"
echo "[hooks] woohwahae.prepushMode=$(git config --get woohwahae.prepushMode)"

