# LAYER OS 인프라 점수 평가
> 평가일: 2026-03-06 | 평가 기준: 프로덕션 운영 성숙도

---

## 총점: 68 / 100

| 영역 | 점수 | 등급 |
|------|------|------|
| 서비스 아키텍처 | 16/20 | B+ |
| 배포 파이프라인 | 14/20 | B |
| 보안 | 13/20 | B- |
| 모니터링/관측성 | 8/20 | D+ |
| 복원력/가용성 | 7/10 | B |
| CI/CD | 10/10 | A |

---

## 1. 서비스 아키텍처 — 16/20

**강점**
- 역할 분리 명확: Gateway(8082) / CMS Backend(5000) / Admin(5001) / E-commerce 별도 스택
- FastAPI 통합 게이트웨이가 sub-app 마운트 패턴으로 CMS/Upload/Commerce 통합
- systemd 기반 서비스 관리 (7개 active unit)
- Council Worker가 timer 기반 비동기 큐 처리 (2분 주기)

**약점**
- **세션 스토리지가 인메모리** (`_admin_sessions`, `_user_sessions` dict) → 재시작 시 전체 로그아웃, 수평 확장 불가
- SQLite 기본 사용 (`sqlite:///./woohwahae_cms.db`) → 동시 쓰기 제한, 프로세스 간 공유 불가
- Gateway에 770줄짜리 모놀리식 `main.py` — 라우팅/인증/DB/HTML 템플릿이 한 파일에 혼재
- WSGIAdapter 자체 구현 — 검증되지 않은 ASGI↔WSGI 브릿지, edge case 리스크

**권장**
- Redis 세션 스토어 도입 (E-commerce 쪽은 이미 Redis 의존성 있음)
- Gateway `main.py` → 라우터 모듈 분리 (auth, content, queue, admin 등)

---

## 2. 배포 파이프라인 — 14/20

**강점**
- `deploy.sh` 770줄 — 포괄적 배포 스크립트 (pull/all/service별/ssl/gateway/admin-cutover)
- `vm_services.json` SSOT 패턴: 서비스 레지스트리를 JSON으로 관리, 스크립트가 참조
- `ops_gate.sh` 배포 전 게이트: visual validator + Playwright smoke + payment regression
- admin-cutover에 canary 체크 + 자동 롤백 로직 내장
- `--skip-gate` 긴급 배포 옵션 존재

**약점**
- **`git reset --hard origin/main`** — 배포 전략이 force-pull, VM 로컬 변경 무조건 소실
- SSH 기반 직접 배포 — 배포 이력 추적 없음, 감사 로그 없음
- 배포 원자성 부재: 코드 pull → 서비스 재시작 사이 정합성 깨질 수 있음
- E-commerce 배포 가이드가 문서(`deployment.md`)에만 있고 자동화 미연동

**권장**
- 배포 이력 로깅 (`knowledge/reports/deploy_log.jsonl`)
- Blue-Green 또는 최소한 symlink swap 패턴 검토
- `deploy.sh all` 시 서비스 순차 재시작 + 각 서비스 health 확인 후 다음 진행

---

## 3. 보안 — 13/20

**강점**
- `core/system/security.py` 공유 보안 모듈: password hash(werkzeug), CORS 로드, HTML sanitize, rate limiter
- `SecurityHeadersMiddleware` 적용
- FastAPI 엔드포인트에 Pydantic 길이 제한 (`max_length`)
- Rate limiter: 로그인 5회/분, OAuth 20회/분
- `require_env()` 패턴으로 비밀값 하드코딩 방지
- 감사 로그(audit log) 구현

**약점**
- **admin 패널 HTML이 Python 코드에 인라인** — CSP 적용 어렵고, XSS 공격면 증가
- `admin-setpw` 명령어에서 평문 비밀번호가 SSH 명령줄에 노출 (`'$2'` 직접 전달)
- `env-set` 명령어: 임의 환경변수를 원격 주입 가능 — 입력 검증 없음
- 500 에러 핸들러가 정수 `500`으로 등록 — FastAPI는 `Exception` 클래스 필요, 실제로 동작 안 할 수 있음
- HTTPS 강제가 nginx 의존 — 앱 레벨 HTTP→HTTPS 리다이렉트 없음

**권장**
- admin 패널을 별도 HTML 파일로 분리 + CSP 헤더 적용
- `admin-setpw`는 stdin 또는 env 기반으로 비밀번호 전달
- `env-set`에 허용 키 화이트리스트 추가

---

## 4. 모니터링/관측성 — 8/20

**강점**
- `/healthz` 엔드포인트: 서비스 마운트 상태 + 큐 카운트 + orchestrator 상태 통합
- `/harness/status` 상세 상태 API
- Nightguard v2 — 할당량 추적 데몬
- `harness_doctor.py` 시스템 진단 스크립트

**약점**
- **중앙 메트릭 수집 시스템 없음** — Prometheus/Grafana/Datadog 등 부재
- 로그가 파일 기반 분산 — 구조화된 로그 수집/검색 불가
- 알림 시스템이 텔레그램 봇에만 의존 — 장애 감지 자동화 미약
- APM(Application Performance Monitoring) 없음 — 응답 시간, 에러율 트래킹 없음
- uptime 모니터링 외부 서비스 연동 없음
- `_is_process_running`이 `pgrep` 기반 — 프로세스 존재 여부만 확인, 실제 health 미검증

**권장**
- 최소: UptimeRobot/BetterStack 외부 uptime 모니터링
- 중기: 구조화된 JSON 로깅 + 로그 집계 (Loki 또는 CloudWatch)
- 장기: Prometheus + Grafana 메트릭 대시보드

---

## 5. 복원력/가용성 — 7/10

**강점**
- systemd `Restart=always` + `RestartSec=3` — 서비스 자동 재시작
- admin-cutover에 canary 실패 시 legacy 롤백
- nginx 설정 변경 전 자동 백업 (`*.bak.admin-route.TS`)

**약점**
- **단일 VM(136.109.201.201)** — SPOF(Single Point of Failure)
- DB 백업이 가이드에만 존재, 자동화 미확인
- Redis 영속성 설정 미확인

**권장**
- 자동 DB 백업 cron + 외부 스토리지 동기화
- VM 스냅샷 정기 생성

---

## 6. CI/CD — 10/10

**강점**
- GitHub Actions 3개 워크플로우 운영
  - `changelog-update`: 일일 자동 + push 트리거
  - `plan-dispatch-health`: 안정성 테스트 + 일일 헬스 리포트
  - `sitemap-auto-regen`: 사이트맵 자동 갱신
- pytest 기반 테스트 게이트 (`core/tests/`)
- `ops_gate.sh` 배포 전 통합 검증 (visual + smoke + payment)

---

## 요약 매트릭스

```
서비스 아키텍처  ████████████████░░░░  16/20
배포 파이프라인  ██████████████░░░░░░  14/20
보안            █████████████░░░░░░░  13/20
모니터링        ████████░░░░░░░░░░░░   8/20
복원력          ███████░░░             7/10
CI/CD           ██████████            10/10
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
총점                                 68/100
```

## 즉시 조치 TOP 3

1. **인메모리 세션 → Redis 전환** — 재시작 시 세션 유실 + 스케일아웃 블로커
2. **외부 uptime 모니터링 추가** — 단일 VM이므로 외부에서 장애 감지 필수
3. **구조화 로깅 도입** — 현재 파일 분산 로그로는 장애 원인 추적 어려움

## 중기 개선 (1-2개월)

4. Gateway `main.py` 모듈 분리 (인라인 HTML 제거)
5. 배포 이력 로깅 + Blue-Green 패턴
6. DB 자동 백업 + 외부 스토리지
