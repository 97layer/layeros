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
- 배포: core/scripts/deploy/deploy.sh <target> (또는 /deploy 스킬)
- 캐시 버스트: build.py --bust

## 6. 긴급 복구
- git status 확인 후 필요한 경우 stash/branch로 보존
- 웹 락 해제: core/system/web_consistency_lock.py --release <AGENT>
- 서비스 재시작: (VM) systemctl restart <services>  # 필요 시

## 7. 신규 에이전트 추가 규칙
- 새 지침 파일 생성 금지: 역할 규칙은 `directives/practice.md` 내 섹션만 추가/수정.
- 라우터/로더 동기화: 새 역할을 만들면 `core/system/directive_loader.py` AGENT_SECTIONS와 `core/agents/agent_router.py` 매핑을 함께 수정.
- 감사 확인: `python3 core/scripts/structure_audit.py`는 미등록 directives/*.md를 경고하므로 실행 후 0건인지 확인.
- 캐시/슬라이스: 필요 시 `core/scripts/render_directives.py --agent <KEY>`로 섹션 슬라이스 생성해 텔레그램/에이전트에 캐시 주입.

---

> 원본 규정 변경 시 여기 링크만 업데이트하세요. 내용 자체는 규정이 아닙니다.
