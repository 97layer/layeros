# Ops Handbook — 실행 체크리스트

> 포털 문서입니다. 원본 SSOT는 링크를 따라가십시오. 철학/설명 금지.

## 1. 파일 배치
- 규칙: AGENTS.md §Filesystem Hard Rules
- 금지 경로: src/, output/, package.json(루트), db 파일, root 임시 파일

## 2. 웹 작업 Lock
- 스크립트: core/system/web_consistency_lock.py
- 절차: acquire → validate → release (AD 전담)

## 3. 품질 게이트
- STAP: directives/practice.md §II-4 (70점 이상)
- Ralph Loop: directives/sage_architect.md §6.5 (90점 이상)

## 4. 세션 절차
- 시작: bash core/scripts/session_bootstrap.sh → READY 확인
- 증거 체크: python3 core/system/evidence_guard.py --check
- 종료: core/scripts/session_handoff.sh "agent-id" "요약" "다음태스크"

## 5. 빌드/배포
- 빌드: python3 core/scripts/build.py [--components|--bust]
- 배포: core/scripts/deploy/deploy.sh <target> (기본 precheck: ops_gate)
- 긴급 배포 우회: core/scripts/deploy/deploy.sh --skip-gate <target>
- 캐시 버스트: build.py --bust

## 6. 긴급 복구
- git status 확인 후 필요한 경우 stash/branch로 보존
- 웹 락 해제: core/system/web_consistency_lock.py --release <AGENT>
- 서비스 재시작: (VM) systemctl restart <services>  # 필요 시

## 7. 운영전환 최소 세팅 (게이트/롤백/알람)
- 게이트: `bash core/scripts/ops_gate.sh`  (visual + 스모크 + 결제 회귀)
- 롤백: `bash core/scripts/ops_rollback.sh`  (`--to legacy|gateway`)
- 알람체크: `python3 core/scripts/ops_alert_check.py --log-file .infra/logs/woohwahae-gateway.log`
- 알람 러너: `bash core/scripts/ops_alert_runner.sh`
- 알람 크론 설치: `bash core/scripts/ops_alert_install_cron.sh --schedule "*/5 * * * *"`
- 복원력 스모크: `python3 core/scripts/pipeline_resilience_smoke.py`
- 복원력 러너: `bash core/scripts/pipeline_resilience_runner.sh`
- 복원력 크론 설치: `bash core/scripts/pipeline_resilience_install_cron.sh --schedule "*/20 * * * *"`
- Plan Dispatch pending 재시도: `python3 core/scripts/plan_dispatch_pending_replay.py --json`
- Plan Dispatch stale 정리/순환: `python3 core/scripts/plan_dispatch_pending_replay.py --drop-stale --max-age-hours 24 --json` (처리 완료/무시 건 pending 자동 compact)
- Council worker 강제가드: `python3 core/scripts/harness_doctor.py`의 `council-worker` 체크는 기본 fail-closed (`COUNCIL_WORKER_REQUIRED=1` 기본)
- Council Room 안건 루프(세션 공유): `python3 core/scripts/council_issue_loop.py watch --json`
- Council Room 안건 담당 할당: `python3 core/scripts/council_issue_loop.py claim --issue-id <id> --agent <AGENT>`
- Council Room 안건 처리/삭제 순환: `python3 core/scripts/council_issue_loop.py resolve --issue-id <id> --agent <AGENT> --result done`

## 8. 신규 에이전트 추가 규칙
- 새 지침 파일 생성 금지: 역할 규칙은 `directives/practice.md` 내 섹션만 추가/수정.
- 라우터/로더 동기화: 새 역할을 만들면 `core/system/directive_loader.py` AGENT_SECTIONS와 `core/agents/agent_router.py` 매핑을 동시 수정.
- 감사 확인: `python3 core/scripts/structure_audit.py`는 미등록 directives/*.md를 경고하므로 실행 후 0건인지 확인.
- 캐시/슬라이스: 필요 시 `core/scripts/render_directives.py --agent <KEY>`로 섹션 슬라이스 생성해 텔레그램/에이전트에 캐시 주입.

## 9. 커밋/배포 자동 트리거
- 훅 설치: `bash core/scripts/hooks/install_git_hooks.sh`
- 상태 확인:
  - `git config --get core.hooksPath` (기대값: `core/scripts/hooks`)
  - `git config --get woohwahae.autodeploy` (기대값: `true`)
- 기본 동작:
  - `pre-commit`: code_audit 강제
  - `pre-push`: evidence_guard + code_audit + resilience smoke + ops_gate(lite/full)
  - `post-commit`: `main` 브랜치 자동 push 후 `deploy.sh <target>` 실행
- 설정 키:
  - `git config woohwahae.autodeploy true|false`
  - `git config woohwahae.autodeployBranch main`
  - `git config woohwahae.autodeployTarget all|none|<deploy.sh target>`
  - `git config woohwahae.prepushMode off|lite|full`

---

> 원본 규정 변경 시 여기 링크만 업데이트하세요. 내용 자체는 규정이 아닙니다.
