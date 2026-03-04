# Reference Map — Routing Table

> 이 문서는 위치 안내 전용입니다. 철학/설명 금지. SSOT는 링크된 파일을 따릅니다.

## 콘텐츠 (CE/SA)

| 컴포넌트/역할 | 절대 경로 | 권한 | 비고 |
| --- | --- | --- | --- |
| 어조·금칙 | directives/sage_architect.md §4·§9 | FROZEN | CE/SA 공통 |
| 철학 백업 | directives/the_origin.md | FROZEN | SA fallback |
| 실행 규격 | directives/practice.md Part II | PROPOSE | STAP, 카테고리/타입 |
| SA 관측 규칙 | directives/practice.md §II-10 | PROPOSE | signal 등급·톤 |
| CE 편집 규칙 | directives/practice.md §II-11 | PROPOSE | 어미·5포맷 |
| 출력 경로 | knowledge/corpus/entries/ | AUTO | signal_id 기반 JSON |

## 이미지/비주얼 (AD)

| 컴포넌트/역할 | 절대 경로 | 권한 | 비고 |
| --- | --- | --- | --- |
| 시각 규격 | directives/practice.md Part I | PROPOSE | 색/폰트/레이아웃 |
| AD 전담 규칙 | directives/practice.md §I-10 | PROPOSE | 락/권한/원칙 |
| 룩북 가이드 | directives/practice.md §I-11 | PROPOSE | pipeline 비연결 |
| 웹 락 스크립트 | core/system/web_consistency_lock.py | AUTO | AD만 acquire |
| 스타일 시트 | website/assets/css/style.css | PROPOSE | AD 전담 수정 |
| 컴포넌트 | website/_components/ | PROPOSE | AD 전담 수정 |

## 개발/배포 (Codex)

| 컴포넌트/역할 | 절대 경로 | 권한 | 비고 |
| --- | --- | --- | --- |
| 파일 배치 규칙 | AGENTS.md §Filesystem Hard Rules | FROZEN | 생성 경로 제한 |
| Claude rules | .claude/rules/filesystem.md | FROZEN | 생성/편집 가드 |
| 실행 프로토콜 | directives/system.md §5, §15 | PROPOSE | 세션/웹락 |
| Plan Dispatch 재시도 | core/scripts/plan_dispatch_pending_replay.py | AUTO | pending 큐 재실행 |
| 빌드 | core/scripts/build.py | AUTO | 전체/--components/--bust |
| 배포 | core/scripts/deploy/deploy.sh (별도) | AUTO | 환경별 실행 |
| 테스트/감사 | core/scripts/structure_audit.py | AUTO | md 참조 검사 |

---

> 수정 시: 링크만 추가/삭제. 설명 문장 추가 금지.
