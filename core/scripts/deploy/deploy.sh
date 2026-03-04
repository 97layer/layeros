#!/bin/bash
# LAYER OS 배포 스크립트
# SSOT: knowledge/system/vm_services.json
#
# Usage:
#   ./deploy.sh              코드 pull만 (재시작 없음)
#   ./deploy.sh all          코드 pull + active 서비스 전체 재시작
#   ./deploy.sh web          Cloudflare Pages 안내
#   ./deploy.sh <서비스명>   특정 서비스 재시작 (active만 허용)
#   ./deploy.sh --skip-gate <명령>  운영 게이트 사전검증 생략(긴급용)
#   ./deploy.sh council-worker-install  council-worker systemd 타이머 설치
#   ./deploy.sh gateway-install  unified gateway(systemd) 설치/재시작
#   ./deploy.sh gateway-status   unified gateway 상태 확인
#   ./deploy.sh admin-cutover    gateway 준비 + /admin 안전 컷오버
#   ./deploy.sh --status     서비스 상태 확인
#   ./deploy.sh --list       배포 가능 서비스 목록

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
VM_SERVICES_JSON="$PROJECT_ROOT/knowledge/system/vm_services.json"

# vm_services.json에서 설정 읽기
if [ ! -f "$VM_SERVICES_JSON" ]; then
  echo "ERROR: $VM_SERVICES_JSON 없음. 배포 중단." >&2
  exit 1
fi

VM_HOST=$(python3 -c "import json; d=json.load(open('$VM_SERVICES_JSON')); print(d['vm']['host_alias'])")
VM_PATH=$(python3 -c "import json; d=json.load(open('$VM_SERVICES_JSON')); print(d['vm']['app_path'])")
VM_USER=$(python3 -c "import json; d=json.load(open('$VM_SERVICES_JSON')); print(d['vm'].get('user', ''))")
SERVICES_ACTIVE=$(python3 -c "import json; d=json.load(open('$VM_SERVICES_JSON')); print(' '.join(d['active'].keys()))")

SKIP_GATE=0
if [ "${DEPLOY_SKIP_GATE:-0}" = "1" ]; then
  SKIP_GATE=1
fi
while [ "${1:-}" = "--skip-gate" ]; do
  SKIP_GATE=1
  shift
done
DEPLOY_ACTION="${1:-pull}"

# 서비스가 active 목록에 있는지 확인
is_active_service() {
  python3 -c "
import json, sys
d = json.load(open('$VM_SERVICES_JSON'))
sys.exit(0 if '$1' in d['active'] else 1)
" 2>/dev/null
}

should_run_precheck() {
  case "$DEPLOY_ACTION" in
    pull|all)
      return 0
      ;;
  esac
  if is_active_service "$DEPLOY_ACTION"; then
    return 0
  fi
  return 1
}

run_ops_gate_precheck() {
  if [ "$SKIP_GATE" = "1" ]; then
    echo "[deploy] --skip-gate enabled: precheck 생략"
    return 0
  fi
  local gate_script="$PROJECT_ROOT/core/scripts/ops_gate.sh"
  if [ ! -x "$gate_script" ]; then
    echo "[deploy] ERROR: ops gate script missing or not executable: $gate_script" >&2
    exit 1
  fi
  echo "[deploy] precheck: ops_gate.sh"
  bash "$gate_script"
}

gateway_install_remote() {
  ssh ${VM_HOST} "bash -s" <<EOF
set -euo pipefail

APP_PATH="${VM_PATH}"
RUN_USER="${VM_USER}"
if [ -z "\$RUN_USER" ]; then
  RUN_USER="\$(id -un)"
fi

if [ ! -d "\$APP_PATH" ]; then
  echo "ERROR: app path not found (\$APP_PATH)" >&2
  exit 1
fi

PY_BIN=""
for CANDIDATE in "\$APP_PATH/.venv/bin/python3" "python3"; do
  if [ "\$CANDIDATE" = "python3" ]; then
    command -v python3 >/dev/null 2>&1 || continue
  elif [ ! -x "\$CANDIDATE" ]; then
    continue
  fi

  if "\$CANDIDATE" -c "import uvicorn" >/dev/null 2>&1; then
    PY_BIN="\$CANDIDATE"
    break
  fi
done

if [ -z "\$PY_BIN" ]; then
  echo "ERROR: uvicorn import 가능한 python 인터프리터를 찾지 못했습니다." >&2
  exit 1
fi

mkdir -p "\$APP_PATH/.infra/logs"

cat > /tmp/woohwahae-gateway.service <<UNIT
[Unit]
Description=WOOHWAHAE Unified Gateway (FastAPI)
After=network.target

[Service]
Type=simple
User=\$RUN_USER
WorkingDirectory=\$APP_PATH
EnvironmentFile=-\$APP_PATH/.env
ExecStart=\$PY_BIN -m uvicorn core.backend.main:app --host 127.0.0.1 --port 8082
Restart=always
RestartSec=3
StandardOutput=append:\$APP_PATH/.infra/logs/woohwahae-gateway.log
StandardError=append:\$APP_PATH/.infra/logs/woohwahae-gateway.log

[Install]
WantedBy=multi-user.target
UNIT

sudo install -m 644 /tmp/woohwahae-gateway.service /etc/systemd/system/woohwahae-gateway.service
sudo systemctl daemon-reload
sudo systemctl enable woohwahae-gateway
sudo systemctl restart woohwahae-gateway
sleep 2

echo "gateway_service=\$(systemctl is-active woohwahae-gateway 2>/dev/null || echo not-found)"
ss -tlnp | grep 8082 >/dev/null || { echo "8082 NOT LISTENING"; exit 1; }

curl -fsS --max-time 4 http://127.0.0.1:8082/healthz >/tmp/woohwahae-gateway-healthz.json
python3 - <<'PY'
import json
from pathlib import Path

payload = json.loads(Path('/tmp/woohwahae-gateway-healthz.json').read_text(encoding='utf-8'))
print("gateway_health_status=" + str(payload.get("status")))
print("gateway_orchestrator_running=" + str(((payload.get("orchestrator") or {}).get("running"))))
PY
EOF
}

gateway_status_remote() {
  ssh ${VM_HOST} "bash -s" <<'EOF'
set -euo pipefail

echo "gateway_service=$(systemctl is-active woohwahae-gateway 2>/dev/null || echo not-found)"
if ss -tlnp | grep -q 8082; then
  echo "gateway_port=8082_listening"
else
  echo "gateway_port=8082_not_listening"
fi

if curl -fsS --max-time 4 http://127.0.0.1:8082/healthz >/tmp/woohwahae-gateway-healthz.json; then
  python3 - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path('/tmp/woohwahae-gateway-healthz.json').read_text(encoding='utf-8'))
print("gateway_health_status=" + str(payload.get("status")))
print("gateway_plan_council_status=" + str(((payload.get("plan_council") or {}).get("status"))))
PY
else
  echo "gateway_health_status=unreachable"
fi
EOF
}

if should_run_precheck; then
  run_ops_gate_precheck
fi

case "$DEPLOY_ACTION" in
  web)
    echo "웹은 git push만 하면 Cloudflare Pages가 자동 배포합니다."
    echo "  git push origin main → 30초 내 woohwahae.kr 반영"
    ;;

  --status)
    echo "=== VM 서비스 상태 (active 목록) ==="
    ssh ${VM_HOST} "for s in ${SERVICES_ACTIVE}; do printf '%-25s %s\n' \$s \$(systemctl is-active \$s 2>/dev/null || echo 'not-found'); done"
    ;;

  --list)
    echo "=== 배포 가능 서비스 (active) ==="
    python3 -c "
import json
d = json.load(open('$VM_SERVICES_JSON'))
for name, info in d['active'].items():
    port = info.get('port') or '-'
    print(f'  {name:<25} port={port:<6} {info[\"role\"]}')
print()
print('=== 배포 불가 (inactive) ===')
for name, info in d['inactive'].items():
    print(f'  {name:<25} {info[\"reason\"]}')
"
    ;;

  all)
    echo "[1/3] git pull..."
    ssh ${VM_HOST} "cd ${VM_PATH} && git fetch origin main && git reset --hard origin/main"
    echo "[2/3] corpus 군집 마이그레이션..."
    ssh ${VM_HOST} "cd ${VM_PATH} && python3 core/scripts/migrate_corpus_clusters.py"
    echo "[3/3] active 서비스 전체 재시작 (${SERVICES_ACTIVE})..."
    ssh ${VM_HOST} "
      set -e
      for s in ${SERVICES_ACTIVE}; do
        if systemctl list-unit-files | grep -q \"^\${s}\\.service\"; then
          sudo systemctl restart \${s}
          printf '%-25s restarted\n' \${s}
        else
          printf '%-25s skipped(not-found)\n' \${s}
        fi
      done
    "
    sleep 3
    ssh ${VM_HOST} "for s in ${SERVICES_ACTIVE}; do printf '%-25s %s\n' \$s \$(systemctl is-active \$s 2>/dev/null || echo 'not-found'); done"
    ;;

  pull)
    echo "git pull..."
    ssh ${VM_HOST} "cd ${VM_PATH} && git fetch origin main && git reset --hard origin/main"
    ;;

  gardener-run)
    echo "Gardener 즉시 실행 (--run-now)..."
    ssh ${VM_HOST} "cd ${VM_PATH} && python3 core/agents/gardener.py --run-now 2>&1"
    ;;

  ssl)
    echo "SSL 인증서 갱신 (api.woohwahae.kr SAN 추가)..."
    ssh ${VM_HOST} "sudo certbot --nginx -d woohwahae.kr -d www.woohwahae.kr -d api.woohwahae.kr --non-interactive --agree-tos --expand 2>&1"
    echo "nginx 재시작..."
    ssh ${VM_HOST} "sudo systemctl reload nginx"
    echo "인증서 확인..."
    ssh ${VM_HOST} "sudo certbot certificates"
    ;;

  test-git-push)
    # VM에서 git push 권한 + user config 검증
    echo "=== VM git config ==="
    ssh ${VM_HOST} "git -C ${VM_PATH} config user.name 2>&1 || echo 'NO user.name'"
    ssh ${VM_HOST} "git -C ${VM_PATH} config user.email 2>&1 || echo 'NO user.email'"
    echo "=== git push dry-run (HEAD:main) ==="
    ssh ${VM_HOST} "cd ${VM_PATH} && git push --dry-run origin HEAD:main 2>&1"
    echo "=== end-to-end note test ==="
    ssh ${VM_HOST} "
      cd ${VM_PATH}
      TS=\$(date +%Y%m%d_%H%M%S)
      F=knowledge/docs/deploy_test_\${TS}.md
      echo '_test: '\${TS}$'\n\ndeploy test note' > \$F
      git add \$F
      git commit -m \"note: deploy_test_\${TS}\" 2>&1
      git push origin HEAD:main 2>&1
      echo 'returncode='$?
    "
    ;;

  git-push-auth)
    # VM git remote URL에 GITHUB_TOKEN 주입 → /note git push 가능하게
    echo "VM .env에서 GITHUB_TOKEN 로드 후 remote URL 업데이트..."
    ssh ${VM_HOST} "
      set -a; source ${VM_PATH}/.env; set +a
      if [ -z \"\$GITHUB_TOKEN\" ]; then
        echo 'ERROR: GITHUB_TOKEN not set in .env' >&2; exit 1
      fi
      REPO=\$(git -C ${VM_PATH} remote get-url origin | sed 's|https://.*@||' | sed 's|https://||')
      git -C ${VM_PATH} remote set-url origin \"https://\${GITHUB_TOKEN}@\${REPO}\"
      echo 'Remote URL updated (token hidden)'
      git -C ${VM_PATH} remote get-url origin | sed 's|https://[^@]*@|https://***@|'
    "
    ;;

  telegram-trace)
    APP_PATH="/home/skyto5339_gmail_com/97layerOS"
    ssh ${VM_HOST} "cd '${APP_PATH}' && timeout 20 python3 -c \"
import sys, os
sys.path.insert(0, '.')
try:
    from dotenv import load_dotenv; load_dotenv('.env')
except: pass
print('1 dotenv ok', flush=True)
try:
    from core.system.notebooklm_bridge import get_bridge
    b = get_bridge(); print('2 notebooklm ok', flush=True)
except Exception as e: print('2 notebooklm FAIL', e, flush=True)
try:
    from core.system.conversation_engine import get_conversation_engine
    c = get_conversation_engine(); print('3 conv_engine ok', flush=True)
except Exception as e: print('3 conv_engine FAIL', e, flush=True)
try:
    from core.system.intent_classifier import get_intent_classifier
    i = get_intent_classifier(); print('4 classifier ok', flush=True)
except Exception as e: print('4 classifier FAIL', e, flush=True)
try:
    from core.system.youtube_analyzer import YouTubeAnalyzer
    y = YouTubeAnalyzer(); print('5 youtube ok', flush=True)
except Exception as e: print('5 youtube FAIL', e, flush=True)
try:
    from core.agents.gardener import Gardener
    g = Gardener(); print('6 gardener ok', flush=True)
except Exception as e: print('6 gardener FAIL', e, flush=True)
try:
    from core.agents.code_agent import CodeAgent
    ca = CodeAgent(); print('7 code_agent ok', flush=True)
except Exception as e: print('7 code_agent FAIL', e, flush=True)
print('done', flush=True)
\" 2>&1" || true
    ;;

  telegram-tail)
    APP_PATH="/home/skyto5339_gmail_com/97layerOS"
    LOG="${2:-error}"
    if [ "$LOG" = "error" ]; then
      ssh ${VM_HOST} "tail -60 '${APP_PATH}/.infra/logs/telegram.error.log' 2>&1"
    else
      ssh ${VM_HOST} "tail -60 '${APP_PATH}/.infra/logs/telegram.log' 2>&1"
    fi
    ;;

  telegram-logfile)
    APP_PATH="/home/skyto5339_gmail_com/97layerOS"
    ssh ${VM_HOST} "cat /etc/systemd/system/97layer-telegram.service 2>/dev/null; echo '---'; ls -la '${APP_PATH}/.infra/logs/' 2>/dev/null || echo 'no logs dir'; ls -la /var/log/97layer* 2>/dev/null || echo 'no /var/log/97layer*'" 2>&1
    ;;

  telegram-error)
    APP_PATH="/home/skyto5339_gmail_com/97layerOS"
    ssh ${VM_HOST} "cd '${APP_PATH}' && export \$(grep -v '^#' .env | xargs) 2>/dev/null; timeout 15 python3 -c \"
import sys
sys.path.insert(0, '.')
try:
    from dotenv import load_dotenv; load_dotenv('.env')
except: pass
try:
    from core.system.env_validator import validate_env
    validate_env('telegram_secretary')
    print('ENV OK')
except SystemExit as e:
    print('ENV FAIL exit:', e)
    sys.exit(1)
try:
    from core.daemons.telegram_secretary import TelegramSecretaryV6
    import os
    tok = os.getenv('TELEGRAM_BOT_TOKEN')
    bot = TelegramSecretaryV6(tok)
    print('INIT OK')
except Exception as e:
    print('INIT FAIL:', type(e).__name__, str(e)[:300])
    sys.exit(1)
\" 2>&1" || true
    ;;

  debug-run)
    APP_PATH="/home/skyto5339_gmail_com/97layerOS"
    ssh ${VM_HOST} "find '${APP_PATH}' -name '*.log' -newer '${APP_PATH}/.env' 2>/dev/null | head -10; ls '${APP_PATH}/.infra/logs/' 2>/dev/null || echo 'no .infra/logs'; sudo journalctl -u 97layer-telegram --output=verbose -n 5 --no-pager 2>&1 | grep -i 'message\|error\|traceback\|python' | head -20" 2>&1
    ;;

  env-check)
    APP_PATH="/home/skyto5339_gmail_com/97layerOS"
    ssh ${VM_HOST} "grep -E '^(TELEGRAM_BOT_TOKEN|ADMIN_TELEGRAM_ID|GOOGLE_API_KEY)=' '${APP_PATH}/.env' 2>/dev/null | sed 's/=.*/=***MASKED***/' || echo '.env not found'"
    ;;

  env-set)
    ENV_KEY="${2:-}"
    ENV_VAL="${3:-}"
    if [ -z "$ENV_KEY" ] || [ -z "$ENV_VAL" ]; then
      echo "Usage: deploy.sh env-set <KEY> <VALUE>" >&2
      exit 1
    fi
    APP_PATH="/home/skyto5339_gmail_com/97layerOS"
    ssh ${VM_HOST} "
      set -e
      ENV_FILE='${APP_PATH}/.env'
      KEY='${ENV_KEY}'
      VAL='${ENV_VAL}'
      if grep -q \"^\${KEY}=\" \"\$ENV_FILE\" 2>/dev/null; then
        sed -i \"s|^\${KEY}=.*|\${KEY}=\${VAL}|\" \"\$ENV_FILE\"
        echo \"updated: \${KEY}\"
      else
        echo \"\${KEY}=\${VAL}\" >> \"\$ENV_FILE\"
        echo \"appended: \${KEY}\"
      fi
    "
    ;;

  logs)
    TARGET="${2:-}"
    if [ -n "$TARGET" ]; then
      ssh ${VM_HOST} "sudo journalctl -u ${TARGET} -n 60 --no-pager -o cat 2>&1"
    else
      for svc in 97layer-telegram 97layer-ecosystem woohwahae-backend 97layer-gardener; do
        echo "━━━ $svc ━━━"
        ssh ${VM_HOST} "sudo journalctl -u ${svc} -n 15 --no-pager 2>&1 | tail -15"
        echo ""
      done
    fi
    ;;

  backend-init)
    echo "woohwahae-backend 필수 환경변수 확인 및 주입..."
    ssh ${VM_HOST} "
      ENV_FILE=${VM_PATH}/.env
      # FLASK_SECRET_KEY 없으면 생성
      if ! grep -q '^FLASK_SECRET_KEY=' \$ENV_FILE 2>/dev/null; then
        KEY=\$(python3 -c 'import secrets; print(secrets.token_hex(32))')
        echo \"FLASK_SECRET_KEY=\$KEY\" >> \$ENV_FILE
        echo 'FLASK_SECRET_KEY 생성 완료'
      else
        echo 'FLASK_SECRET_KEY 이미 존재'
      fi
      # FLASK_ADMIN_PASSWORD_HASH 없으면 기존 ADMIN_PASSWORD_HASH 재사용 또는 신규 생성
      if ! grep -q '^FLASK_ADMIN_PASSWORD_HASH=' \$ENV_FILE 2>/dev/null; then
        if grep -q '^ADMIN_PASSWORD_HASH=' \$ENV_FILE 2>/dev/null; then
          H=\$(grep '^ADMIN_PASSWORD_HASH=' \$ENV_FILE | tail -n1 | cut -d= -f2-)
          echo \"FLASK_ADMIN_PASSWORD_HASH=\$H\" >> \$ENV_FILE
          echo 'FLASK_ADMIN_PASSWORD_HASH 추가 (ADMIN_PASSWORD_HASH 재사용)'
        else
          H=\$(python3 - <<'PY'
import secrets
from werkzeug.security import generate_password_hash
print(generate_password_hash(secrets.token_urlsafe(18), method='pbkdf2:sha256'))
PY
)
          echo \"FLASK_ADMIN_PASSWORD_HASH=\$H\" >> \$ENV_FILE
          echo 'FLASK_ADMIN_PASSWORD_HASH 신규 생성'
        fi
      else
        echo 'FLASK_ADMIN_PASSWORD_HASH 이미 존재'
      fi
      # FASTAPI_ADMIN_PASSWORD_HASH 없으면 Flask 해시와 동기화
      if ! grep -q '^FASTAPI_ADMIN_PASSWORD_HASH=' \$ENV_FILE 2>/dev/null; then
        H=\$(grep '^FLASK_ADMIN_PASSWORD_HASH=' \$ENV_FILE | tail -n1 | cut -d= -f2-)
        echo \"FASTAPI_ADMIN_PASSWORD_HASH=\$H\" >> \$ENV_FILE
        echo 'FASTAPI_ADMIN_PASSWORD_HASH 추가 (FLASK_ADMIN_PASSWORD_HASH 동기화)'
      else
        echo 'FASTAPI_ADMIN_PASSWORD_HASH 이미 존재'
      fi
      # .env 현재 키 목록 확인 (값 제외)
      grep -o '^[^=]*' \$ENV_FILE | sort
    "
    echo "woohwahae-backend 재시작..."
    ssh ${VM_HOST} "sudo systemctl restart woohwahae-backend"
    sleep 4
    ssh ${VM_HOST} "systemctl is-active woohwahae-backend && sudo journalctl -u woohwahae-backend -n 8 --no-pager 2>&1"
    ;;

  admin-setpw)
    # $2 = 평문 비밀번호
    if [ -z "$2" ]; then echo "Usage: deploy.sh admin-setpw <password>"; exit 1; fi
    echo "비밀번호 해시 생성 후 VM .env 주입..."
    ssh ${VM_HOST} "
      HASH=\$(python3 -c \"from werkzeug.security import generate_password_hash; print(generate_password_hash('$2', method='pbkdf2:sha256'))\")
      ENV_FILE=${VM_PATH}/.env
      # 기존 항목 제거 후 추가
      sed -i '/^ADMIN_PASSWORD_HASH=/d' \$ENV_FILE
      echo \"ADMIN_PASSWORD_HASH=\$HASH\" >> \$ENV_FILE
      echo 'ADMIN_PASSWORD_HASH 설정 완료'
    "
    echo "cortex-admin 재시작..."
    ssh ${VM_HOST} "sudo systemctl restart cortex-admin"
    sleep 3
    ssh ${VM_HOST} "systemctl is-active cortex-admin && sudo ss -tlnp | grep 5001"
    ;;

  admin-log)
    echo "=== cortex-admin 로그 (최근 30줄) ==="
    ssh ${VM_HOST} "sudo journalctl -u cortex-admin -n 30 --no-pager 2>&1"
    echo ""
    echo "=== 포트 5001 리스닝 확인 ==="
    ssh ${VM_HOST} "sudo ss -tlnp | grep 5001 || echo '5001 NOT LISTENING'"
    ;;

  admin-route-status)
    echo "=== api.woohwahae.kr /admin 라우팅 상태 ==="
    ssh ${VM_HOST} "python3 - <<'PY'
import pathlib
import re
import sys

conf = pathlib.Path('/etc/nginx/nginx.conf')
if not conf.exists():
    print('nginx.conf not found')
    sys.exit(1)

text = conf.read_text(encoding='utf-8', errors='ignore')
match = re.search(r'location /admin/ \{.*?proxy_pass\\s+http://127\\.0\\.0\\.1:(\\d+)(?:/)?;.*?\}', text, re.S)
if not match:
    print('/admin location block not found')
    sys.exit(1)

port = match.group(1)
if port == '5001':
    target = 'legacy-cortex-admin'
elif port == '8082':
    target = 'unified-gateway'
else:
    target = 'custom'

print(f'admin_route_target={target}')
print(f'admin_route_port={port}')
PY"
    ;;

  admin-route-switch)
    TARGET_MODE="${2:-}"
    if [ "$TARGET_MODE" != "legacy" ] && [ "$TARGET_MODE" != "gateway" ]; then
      echo "Usage: deploy.sh admin-route-switch [legacy|gateway]" >&2
      exit 1
    fi

    if [ "$TARGET_MODE" = "legacy" ]; then
      TARGET_PORT="5001"
      TARGET_LABEL="legacy-cortex-admin"
      TARGET_PROXY="http://127.0.0.1:5001/"
    else
      TARGET_PORT="8082"
      TARGET_LABEL="unified-gateway"
      TARGET_PROXY="http://127.0.0.1:8082"
    fi

    echo "api.woohwahae.kr /admin 라우팅 전환 → ${TARGET_LABEL} (${TARGET_PORT})"
    ssh ${VM_HOST} "
      set -e
      CONF=/etc/nginx/nginx.conf
      TS=\$(date +%Y%m%d_%H%M%S)
      sudo cp \$CONF \${CONF}.bak.admin-route.\${TS}
      sudo TARGET_PROXY='${TARGET_PROXY}' python3 - <<'PY'
import os
import pathlib
import re
import sys

conf_path = pathlib.Path('/etc/nginx/nginx.conf')
target_proxy = os.environ.get('TARGET_PROXY', '').strip()
if not target_proxy:
    print('TARGET_PROXY missing', file=sys.stderr)
    sys.exit(1)

text = conf_path.read_text(encoding='utf-8', errors='ignore')
block_match = re.search(r'location /admin/ \{.*?\}', text, re.S)
if not block_match:
    print('/admin location block not found', file=sys.stderr)
    sys.exit(1)

block = block_match.group(0)
updated_block = re.sub(
    r'proxy_pass\s+http://127\.0\.0\.1:\d+/?;',
    f'proxy_pass {target_proxy};',
    block,
    count=1,
)
if block == updated_block:
    print('proxy_pass update failed', file=sys.stderr)
    sys.exit(1)

updated_text = text[:block_match.start()] + updated_block + text[block_match.end():]
conf_path.write_text(updated_text, encoding='utf-8')
PY
      sudo nginx -t
      sudo systemctl reload nginx
      echo 'switched to ${TARGET_LABEL}'
      python3 - <<'PY'
import pathlib
import re
text = pathlib.Path('/etc/nginx/nginx.conf').read_text(encoding='utf-8', errors='ignore')
m = re.search(r'location /admin/ \\{.*?proxy_pass\\s+http://127\\.0\\.0\\.1:(\\d+)(?:/)?;.*?\\}', text, re.S)
print('active_admin_port=' + (m.group(1) if m else 'unknown'))
PY
    "
    ;;

  council-worker-install)
    echo "=== council-worker systemd 타이머 설치 ==="
    ssh ${VM_HOST} "bash -s" <<'COUNCIL_EOF'
set -euo pipefail
APP_PATH="/home/skyto5339_gmail_com/97layerOS"
cd "$APP_PATH"
git fetch origin main && git reset --hard origin/main
sudo cp -f ".infra/systemd/council-worker.service" /etc/systemd/system/council-worker.service 2>/dev/null || true
sudo cp -f ".infra/systemd/council-worker.timer"   /etc/systemd/system/council-worker.timer 2>/dev/null || true
sudo systemctl daemon-reload
sudo systemctl enable --now council-worker.timer
echo "council-worker 타이머 상태:"
sudo systemctl status council-worker.timer --no-pager
COUNCIL_EOF
    ;;

  gateway-install)
    echo "=== unified gateway(systemd) 설치/재시작 ==="
    gateway_install_remote
    ;;

  gateway-status)
    echo "=== unified gateway 상태 확인 ==="
    gateway_status_remote
    ;;

  admin-cutover)
    echo "[1/5] backend 환경 보강..."
    "$0" backend-init

    echo "[2/5] unified gateway 설치/재시작..."
    "$0" gateway-install

    echo "[3/5] /admin 라우팅 → gateway(8082) 전환..."
    "$0" admin-route-switch gateway

    echo "[4/5] canary 확인 (https://api.woohwahae.kr/admin/)..."
    ADMIN_CODE="$(curl -ksS -o /dev/null -w "%{http_code}" https://api.woohwahae.kr/admin/ || true)"
    if [ "$ADMIN_CODE" != "200" ] && [ "$ADMIN_CODE" != "302" ]; then
      echo "canary failed: /admin http_code=$ADMIN_CODE → legacy 롤백"
      "$0" admin-route-switch legacy
      exit 1
    fi
    echo "canary ok: /admin http_code=$ADMIN_CODE"

    echo "[5/5] 최종 상태 확인"
    "$0" admin-route-status
    "$0" gateway-status
    ;;

  ssl-check)
    echo "=== nginx api.woohwahae.kr 설정 확인 ==="
    ssh ${VM_HOST} "sudo ls /etc/nginx/sites-enabled/ && sudo cat /etc/nginx/sites-enabled/api.woohwahae.kr 2>/dev/null || sudo grep -rl 'api.woohwahae' /etc/nginx/ 2>/dev/null | head -5 | xargs sudo cat"
    ;;

  ssl-fix)
    echo "[1/4] ACME webroot 생성..."
    ssh ${VM_HOST} "sudo mkdir -p /var/www/letsencrypt/.well-known/acme-challenge && sudo chmod -R 755 /var/www/letsencrypt"

    echo "[2/4] nginx HTTP block에 ACME challenge location 추가..."
    ssh ${VM_HOST} "
      NGINX_CONF=/etc/nginx/nginx.conf
      # HTTP 서버 블록의 'return 301' 앞에 ACME location 삽입 (idempotent)
      if ! sudo grep -q 'well-known/acme-challenge' \$NGINX_CONF; then
        sudo sed -i 's|server_name api.woohwahae.kr;\n.*return 301|server_name api.woohwahae.kr;\n        location /.well-known/acme-challenge/ { root /var/www/letsencrypt; }\n        return 301|' \$NGINX_CONF
        # sed multiline 미지원 fallback: python3 사용
        sudo python3 -c \"
import re, sys
with open('\$NGINX_CONF', 'r') as f:
    content = f.read()
old = '''    server {
        listen 80;
        server_name api.woohwahae.kr;
        return 301 https://\\\$host\\\$request_uri;
    }'''
new = '''    server {
        listen 80;
        server_name api.woohwahae.kr;
        location /.well-known/acme-challenge/ {
            root /var/www/letsencrypt;
        }
        location / {
            return 301 https://\\\$host\\\$request_uri;
        }
    }'''
if old in content:
    content = content.replace(old, new)
    with open('\$NGINX_CONF', 'w') as f:
        f.write(content)
    print('nginx config 패치 완료')
else:
    print('패치 대상 없음 또는 이미 패치됨')
\"
      else
        echo 'ACME location 이미 존재, 스킵'
      fi
    "
    echo "nginx 설정 검증..."
    ssh ${VM_HOST} "sudo nginx -t 2>&1"
    echo "nginx 리로드..."
    ssh ${VM_HOST} "sudo systemctl reload nginx"

    echo "[3/4] certbot webroot로 api.woohwahae.kr 인증서 발급..."
    ssh ${VM_HOST} "sudo certbot certonly --webroot -w /var/www/letsencrypt -d api.woohwahae.kr --non-interactive --agree-tos 2>&1"

    echo "[4/4] nginx api.woohwahae.kr SSL cert 경로 업데이트..."
    ssh ${VM_HOST} "
      NGINX_CONF=/etc/nginx/nginx.conf
      sudo python3 -c \"
with open('\$NGINX_CONF', 'r') as f:
    content = f.read()
# api 서버 블록의 cert를 api.woohwahae.kr cert로 교체
old_cert = '    server_name api.woohwahae.kr;'
# api 블록에서만 cert 경로 교체
import re
def replace_api_cert(m):
    block = m.group(0)
    block = block.replace(
        '/etc/letsencrypt/live/woohwahae.kr/fullchain.pem',
        '/etc/letsencrypt/live/api.woohwahae.kr/fullchain.pem'
    )
    block = block.replace(
        '/etc/letsencrypt/live/woohwahae.kr/privkey.pem',
        '/etc/letsencrypt/live/api.woohwahae.kr/privkey.pem'
    )
    return block
# api.woohwahae.kr HTTPS 블록 패턴
pattern = r'(server \{[^}]*?server_name api\.woohwahae\.kr;.*?^\})'
new_content = re.sub(pattern, replace_api_cert, content, flags=re.MULTILINE | re.DOTALL)
if new_content != content:
    with open('\$NGINX_CONF', 'w') as f:
        f.write(new_content)
    print('cert 경로 업데이트 완료')
else:
    print('변경 없음')
\"
      sudo nginx -t 2>&1 && sudo systemctl reload nginx
    "
    echo "=== 최종 인증서 확인 ==="
    ssh ${VM_HOST} "sudo certbot certificates"
    ;;

  *)
    # 서비스명 검증
    if ! is_active_service "$DEPLOY_ACTION"; then
      echo "ERROR: '$DEPLOY_ACTION'은(는) active 서비스가 아닙니다." >&2
      echo "배포 가능 목록: ${SERVICES_ACTIVE}" >&2
      echo "전체 목록: ./deploy.sh --list" >&2
      exit 1
    fi

    echo "[1/2] git pull..."
    ssh ${VM_HOST} "cd ${VM_PATH} && git fetch origin main && git reset --hard origin/main"
    echo "[2/2] ${DEPLOY_ACTION} 재시작..."
    ssh ${VM_HOST} "sudo systemctl restart ${DEPLOY_ACTION}"
    sleep 2
    ssh ${VM_HOST} "systemctl is-active ${DEPLOY_ACTION}"
    ;;
esac
