#!/bin/bash
# LAYER OS 배포 스크립트
# SSOT: knowledge/system/vm_services.json
#
# Usage:
#   ./deploy.sh              코드 pull만 (재시작 없음)
#   ./deploy.sh all          코드 pull + active 서비스 전체 재시작
#   ./deploy.sh web          Cloudflare Pages 안내
#   ./deploy.sh <서비스명>   특정 서비스 재시작 (active만 허용)
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
SERVICES_ACTIVE=$(python3 -c "import json; d=json.load(open('$VM_SERVICES_JSON')); print(' '.join(d['active'].keys()))")

# 서비스가 active 목록에 있는지 확인
is_active_service() {
  python3 -c "
import json, sys
d = json.load(open('$VM_SERVICES_JSON'))
sys.exit(0 if '$1' in d['active'] else 1)
" 2>/dev/null
}

case "${1:-pull}" in
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
    ssh ${VM_HOST} "sudo systemctl restart ${SERVICES_ACTIVE}"
    sleep 3
    ssh ${VM_HOST} "for s in ${SERVICES_ACTIVE}; do printf '%-25s %s\n' \$s \$(systemctl is-active \$s); done"
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
    if ! is_active_service "$1"; then
      echo "ERROR: '$1'은(는) active 서비스가 아닙니다." >&2
      echo "배포 가능 목록: ${SERVICES_ACTIVE}" >&2
      echo "전체 목록: ./deploy.sh --list" >&2
      exit 1
    fi

    echo "[1/2] git pull..."
    ssh ${VM_HOST} "cd ${VM_PATH} && git fetch origin main && git reset --hard origin/main"
    echo "[2/2] ${1} 재시작..."
    ssh ${VM_HOST} "sudo systemctl restart ${1}"
    sleep 2
    ssh ${VM_HOST} "systemctl is-active ${1}"
    ;;
esac
