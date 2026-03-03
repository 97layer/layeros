# LAYER OS — Claude Code Entry Point
# Updated: 2026-03-01

## 세션 시작
startup hook이 자동 로드하는 것:
1. `knowledge/agent_hub/state.md` — 세션 상태
2. `directives/the_origin.md` — 세계관 SSOT
3. `directives/sage_architect.md` — 브랜드 인격 SSOT (언어/어조/금지어 전체)
4. `directives/practice.md` — 서비스·브랜드 실행 기준

work_lock 잠금 시 STOP.
파일 생성 전: `filesystem_cache.json` 확인. 배치 규칙: `directives/system.md §10`.

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
- 비자명 태스크: Plan mode 먼저
- 도구 트리거 규칙: `.claude/rules/proactive-tools.md`
- Read 순서: `Glob → Grep → Read(offset/limit)` — 전체 blindly Read 금지
- 커뮤니케이션: Direct & Factual | Zero Noise | 인사/사과 없음

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
| state.md 갱신 | `/quanta` |
| Brand OS 규칙 참조 | `/brand` |
| 코드 품질 검증 | `/verify` |
| 폴더 구조 감사 | `/audit` |
| 세션 종료 핸드오프 | `/handoff` |
