# LAYER OS — Claude Code Entry Point
# Updated: 2026-03-04

## 세션 시작
startup hook이 자동 로드하는 것:
1. `AGENTS.md` — 실행 가드레일 SSOT
2. `knowledge/agent_hub/state.md` — 세션 상태
3. `directives/the_origin.md` — 세계관 SSOT
4. `directives/sage_architect.md` — 브랜드 인격 SSOT (언어/어조/금지어 전체)
5. `directives/practice.md` — 서비스·브랜드 실행 기준
6. `.claude/rules/proactive-tools.md` — MCP 능동 트리거 SSOT
7. `.claude/rules/plan-council.md` — 실행 전 계획 협의 규칙
8. `.claude/rules/model-role-routing.md` — 모델 역할 라우팅 규칙
9. `.claude/rules/anti-hallucination.md` — 환각 방지 실행 규칙
10. `knowledge/system/agent_runtime_contract.json` — 모델 독립 실행 계약
11. `knowledge/docs/reference-map.md` — 작업별 위치 안내
12. `knowledge/docs/ops-handbook.md` — 실행 체크리스트

`web_work_lock` 잠금 시 STOP.
파일 생성 전: `filesystem_cache.json` 확인. 배치 규칙: `directives/system.md §10`.

작업 시작 전 필수:
```bash
bash core/scripts/session_bootstrap.sh
```
출력이 `READY`가 아니면 작업 시작 금지.

**디자인/콘텐츠 작업 시**: sage_architect.md §4(어조) + §9(금지어) 반드시 적용.

## 금지
1. ❌ 중복 생성 — filesystem_cache.json 먼저
2. ❌ work lock 무시
3. ❌ 루트(/)에 파일 생성 (CLAUDE.md, README.md 제외)
4. ❌ 금지 파일명: SESSION_SUMMARY_* / WAKEUP_REPORT* / DEPLOY_* / NEXT_STEPS* / temp_* / untitled_*

## 파일 정책
- 덮어쓰기: `state.md`, `the_origin.md`, `system.md`
- Append: `council_room.md`, `feedback_loop.md`
- 날짜별: `reports/morning_YYYYMMDD.md`
- 생성 금지: 위 외 임의 경로 .md

## 실행 원칙
- 컨텍스트 50%: `/compact` 실행
- Codex 기본 계획 진입점: `bash core/scripts/plan_dispatch.sh "<intent>" --auto`
- 채팅 alias: `/plan <intent>` 입력 시 `bash core/scripts/plan_dispatch.sh "<intent>" --manual` 실행
- 비자명 태스크: Plan Council 선행 (`python3 core/system/plan_council.py --task "<intent>" --mode preflight`)
- 비자명 태스크: Plan mode 먼저 + `sequential-thinking` 최소 1회 선행
- 도구 트리거 규칙: `.claude/rules/proactive-tools.md`
- 모델 역할 라우팅: `Claude=Plan`, `Codex=Code`, `Gemini=Verify`
- Read 순서: `Glob → Grep → Read(offset/limit)` — 전체 blindly Read 금지
- 커뮤니케이션: Direct & Factual | Zero Noise | 인사/사과 없음
- 사용자 응답 톤: 기본 `존댓말(합니다체)` 고정, 명시 요청 시에만 반말
- MCP 트리거 미충족 상태 구현 금지
- 사실 단정 전 근거 필수, 근거 없으면 `모름/검증 필요`로 응답
- 시간 민감 정보(`최신/오늘/현재`)는 검증 전 단정 금지
- `python3 core/system/evidence_guard.py --check` 결과 `READY` 유지
- Plan Council `DEGRADED`면 리스크를 먼저 알리고 실행

## 핸드오프
```bash
./core/scripts/session_handoff.sh "agent-id" "요약" "다음태스크"
```

## 스킬 매핑 (bash 직접 치기 전 확인)

| 작업 | 커맨드 |
|------|--------|
| VM 배포 / 서비스 재시작 | `/deploy [대상]` |
| 시스템 전체 진단 | `/doctor` |
| 파이프라인 현황 | `/status` |
| Codex 계획 디스패처 | `bash core/scripts/plan_dispatch.sh "<요청>" --auto` |
| 실행 전 계획 협의 | `/plan [요청]` 또는 `/plan-council [요청]` |
| state.md 갱신 | `/quanta` |
| Brand OS 규칙 참조 | `/brand` |
| 코드 품질 검증 | `/verify` |
| 폴더 구조 감사 | `/audit` |
| 세션 종료 핸드오프 | `/handoff` |

## 필수 스킬 존재 체크
```bash
test -f /Users/97layer/.codex/skills/playwright/SKILL.md
test -f /Users/97layer/.codex/skills/screenshot/SKILL.md
test -f /Users/97layer/.codex/skills/.system/skill-creator/SKILL.md
test -f /Users/97layer/.codex/skills/.system/skill-installer/SKILL.md
```
