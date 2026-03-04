# SYSTEM — LAYER OS 운영 매뉴얼

> **Version**: 10.0 (통합)
> **역할**: 에이전트 실행 프로토콜 + 파일 배치 규칙 + AI 거버넌스.
>         sage_architect.md(인격)가 '무엇을 사고하는가'라면, 이 문서는 '어떻게 실행하는가'.
> **Authority**: sage_architect.md > the_origin.md > system.md > practice.md(역할 섹션)

---

## 1. Architecture (5-Layer)

| Layer | 역할 | 주체 |
|-------|------|------|
| **L1** Philosophy | 철학의 순수성 수호, 거부권 | CD (sage_architect.md §10) |
| **L2** Design | 시각적 침묵의 렌더링 | AD |
| **L3** Content | 신호의 지층화 및 텍스트 기록 | CE + SA |
| **L4** Service | 이치고 이치에 실천 | Ritual Module |
| **L5** Business | 유산의 아카이브 성장 | Growth Module |

---

## 2. Authority (3-Tier)

| Tier | 대상 | 제어 |
|------|------|------|
| **FROZEN** | `the_origin.md`, `sage_architect.md` | CD 고유 권한. 임의 수정 금지 |
| **PROPOSE** | `practice.md`(역할 섹션 포함) | 피드백 루프 (승인제 변경) |
| **AUTO** | `state.md`, `signals/`, `memory` | 비동기 상태 기록 |

---

## 3. Data Pipeline (증류 모형)

> 상세 도식: practice.md Part II §6

Signal → SA → Gardener → CE → Ralph → AD → CD → 발행.
각 단계는 독립 실패 가능. 실패 시 이전 단계로 리턴.

---

## 4. Document Hierarchy

```text
directives/
├── the_origin.md            ← 경전 (FROZEN)
├── sage_architect.md        ← 인격 SSOT + 용어 사전 (FROZEN)
├── system.md                ← 운영 매뉴얼 (현재 파일)
├── practice.md              ← Part I 시각 / Part II 언어 / Part III 공간
└── (agents/*.md 통합: practice.md 역할 섹션으로 흡수)
```

---

## 5. Session Protocol (필수 초기화)

### 5.1 세션 시작 시 필수 로드

```bash
cat knowledge/agent_hub/state.md   # 시스템 현재 상태
cat knowledge/system/web_work_lock.json          # 잠금 확인 (SSOT)
cat knowledge/system/agent_runtime_contract.json # 모델 독립 실행 계약
cat .claude/rules/plan-council.md                # 실행 전 계획 협의 규칙
cat .claude/rules/model-role-routing.md          # 모델 역할 라우팅
cat .claude/rules/anti-hallucination.md          # 환각 방지 실행 규칙
```

state.md 미확인 = CRITICAL VIOLATION.
web_work_lock 잠금 상태 = STOP.

### 5.2 파일 생성 전 확인

```bash
cat knowledge/system/filesystem_cache.json       # 중복 방지
```

### 5.3 생성 후 등록

```bash
python core/system/handoff.py --register-asset <path> <type> <source>
```

### 5.4 세션 종료

```bash
./core/scripts/session_handoff.sh "agent-id" "요약" "다음태스크1" "다음태스크2"
```

---

## 6. Task Classification (작업 분류)

| Type | 설명 | 로드 문서 |
|------|------|----------|
| **A** | 에세이 작성 | the_origin.md + practice.md Part II |
| **B** | 웹카피/DM | sage_architect.md §7 + practice.md Part II §8 |
| **C** | 시스템 문서 편집 | sage_architect.md + 대상 문서 |
| **D** | 디자인/시각 | practice.md Part I |
| **E** | 서비스 설계 | practice.md Part III |

---

## 7. Context Loading (슬롯 아키텍처)

```python
CONTEXT_SLOTS = {
    "slot_1": "sage_architect.md",        # 인격 + 용어 (필수)
    "slot_2": "practice.md",               # Part I 시각 / Part II 언어 / Part III 공간
    "slot_3": "practice.md 역할 섹션",     # 역할별
    "slot_4": "(reserved)",               # 확장용
}
```

| Agent | 필수 | 선택 |
|-------|------|------|
| **CE** | 1, 2 | 3 (practice.md §II-11) |
| **SA** | 1, 2 | 3 (practice.md §II-10) |
| **AD** | 1, 2 | 3 (practice.md §I-10) |
| **Ralph** | 1 | STAP 섹션만 |

---

## 8. Constraint Enforcement (제약 강제)

### 8.1 언어 제약
- SSOT: sage_architect.md §9 금칙 규정

### 8.2 시각 제약
- SSOT: practice.md Part I (Colors, Typography, Spacing, Breath)

### 8.3 품질 게이트 (2-Stage)

**Stage 1 — STAP (콘텐츠 품질)**: `practice.md §II-4`
- 5-pillar. 70점+ → Stage 2. 미달 → CE 재작업 최대 2회.

**Stage 2 — Ralph Loop (언어 품질)**: `sage_architect.md §6.5`
- 4-loop. 90점+ → AD 진행. 미달 → CE 재작업 최대 2회.

두 게이트 모두 통과해야 AD로 이동.

---

## 9. Forbidden Actions (금지 행동)

1. **중복 생성** — filesystem_cache.json 미확인 상태로 파일 생성
2. **컨텍스트 무시** — state.md 미확인 상태로 작업 시작
3. **work lock 무시** — 잠금 확인 없이 파일 수정
4. **미등록 산출물** — 생성 후 register-asset 누락
5. **과거 환각** — 기록된 것만 신뢰. 추측 금지
6. **루트 파일 생성** — CLAUDE.md, README.md 제외 루트(/)에 어떤 파일도 금지

### 금지 파일명 패턴
SESSION_SUMMARY_* / WAKEUP_REPORT* / DEPLOY_* / NEXT_STEPS* / temp_* / untitled_*

---

## 10. Filesystem Placement (배치 규칙)

### 10.1 4축 구조

```
LAYER OSOS/
├── directives/     뇌 — 철학, 규칙, 규격
├── knowledge/      기억 — 데이터, 신호, 상태
├── core/           엔진 — 코드, 스크립트, 스킬, 테스트
├── website/        얼굴 — HTML/CSS/JS
└── .infra/         런타임 — 로그, 큐, nginx (.gitignore)
```

### 10.2 파일 타입별 허용 경로

| 파일 유형 | 허용 경로 |
|-----------|-----------|
| Python (.py) | `core/agents/`, `core/system/`, `core/daemons/`, `core/scripts/`, `core/admin/`, `core/backend/`, `core/skills/`, `core/tests/` |
| Markdown (.md) | `directives/`, `knowledge/` 하위 |
| HTML/CSS/JS | `website/` 하위 |
| JSON (데이터) | `knowledge/signals/`, `knowledge/corpus/`, `knowledge/system/`, `knowledge/clients/`, `knowledge/service/`, `knowledge/reports/` |

### 10.3 산출물 배치

| 산출물 | 경로 | 명명 |
|--------|------|------|
| 신호 (원시) | `knowledge/signals/` | `{type}_{YYYYMMDD}_{HHMMSS}.json` |
| 신호 (분석) | `knowledge/corpus/entries/` | `entry_{signal_id}.json` |
| 에세이 HTML | `website/archive/essay-{NNN}-{slug}/` | `index.html` |
| 리포트 | `knowledge/reports/` | morning/evening만 허용 |
| 에이전트 제안 | `knowledge/agent_hub/council_room.md` | append |

### 10.4 Agent Write Path

| 에이전트 | 허용 | 금지 |
|---------|------|------|
| **Claude Code** | 전체 | — |
| **Gemini CLI** | `knowledge/signals/` `knowledge/corpus/` `council_room.md`(append) | `core/` `directives/` `knowledge/system/` |
| **SA** | `knowledge/corpus/entries/` `.infra/queue/` | `core/` `website/` |
| **CE** | `website/archive/` `.infra/queue/` | `core/` `directives/` |
| **AD** | `.infra/queue/` | `core/` `website/` |

---

## 11. Gemini 특별 규칙

### 11.1 독단 방지

1. 맥락 강제 읽기: state.md + the_origin.md → 읽지 않고 제안 금지
2. 추측 금지: "아마도", "추측하건대" → 확인 후 발언
3. 과장 금지: "압도적", "완벽" → 객관적 톤
4. 증명 우선: 주장 < 증명. 증명 없으면 침묵
5. SAGE-ARCHITECT 절대 우선: 내 판단 < sage_architect.md

### 11.2 Gemini System Prompt

```
당신은 WOOHWAHAE 브랜드의 전담 편집 에이전트입니다.
필수: sage_architect.md 최우선 / the_origin.md / practice.md
금지: 느낌표, 이모지, 감정 과잉, 세일즈 톤
검열: STAP 5 Pillars 70점 이상만 출력
```

---

## 12. Cache Strategy

### 상주 메모리
```python
ALWAYS_CACHED = ["sage_architect.md"]
```

### 온디맨드
```python
ON_DEMAND = ["practice.md", "the_origin.md"]
```

### 무효화 트리거
- sage_architect.md 변경 → 전체 캐시 무효화
- practice.md 변경 → 해당 섹션만 리로드

---

## 13. Dependency Graph

```mermaid
graph TD
    A[the_origin.md] --> B[sage_architect.md]
    B --> C[system.md]
    C --> D[practice.md]
    D --> F[Output]
    F --> G[STAP Gate]
    G -->|Pass| H[Publish]
    G -->|Fail| D
```

---

## 14. THE CYCLE

```
Input (Signal) → Store (Archive) → Connect (Cluster)
    ↑                                        ↓
Generate ← Publish (Essay) ← Generate (Essay)
```

자동화 트리거:
- 신호 20개 누적 → SA 군집 분석
- 군집 ripe → CE 에세이 초안
- 에세이 STAP 70점+ → AD 시각화 + 발행

---

## 15. Web Consistency Lock

### 웹 작업 일관성 문제 방지
```bash
# 작업 전 반드시 실행
python core/system/web_consistency_lock.py --acquire [AGENT_ID] --task "작업내용"
python core/system/web_consistency_lock.py --validate [AGENT_ID]
python core/system/web_consistency_lock.py --release [AGENT_ID]
```

### 권한 매트릭스
| Agent | 권한 범위 |
|-------|----------|
| AD | style.css, 레이아웃, 컴포넌트, 비주얼 전담 |
| CE | 텍스트 콘텐츠만 |
| SA | 웹 직접 수정 금지 |

### 어조 규칙 강제
| 섹션 | 어조 |
|------|------|
| archive/* | 자연체 (에세이, 독백) |
| practice/* | 합니다체 (서비스, 고객) |
| about/* | 합니다체 (공식 소개) |
| home | 자연체 |

**원칙**: 여러 에이전트가 동시 웹 수정 금지. AD가 비주얼 전담.

---

## 16. Session Hygiene

### 세션 시작 필수 체크
```bash
# .claude/hooks/session-start 자동 실행
# 1. Uncommitted 파일 경고
# 2. Web Lock 상태 확인
# 3. 미완성 Todo 알림
```

### 커밋 정책
- **즉시 커밋**: 의미 있는 변경은 즉시 커밋
- **즉시 되돌림**: 실험/테스트는 즉시 `git checkout --`
- **방치 금지**: Modified 상태로 세션 종료 금지

### TodoWrite 사용 기준
- ✅ 사용: 5단계 이상 복잡한 작업
- ❌ 금지: 단순 파일 읽기/수정
- ❌ 금지: 1-2단계 작업

---

## 17. Enforcement Layers

| Layer | 메커니즘 | 위치 |
|-------|---------|------|
| 1 | CLAUDE.md / .ai_rules | 루트 |
| 2 | Claude Code Hooks | `.claude/hooks/` |
| 3 | Claude Code Rules | `.claude/rules/` |
| 4 | Git Pre-Commit Hook | `.git/hooks/pre-commit` |
| 5 | Bootstrap Script | `core/scripts/session_bootstrap.sh` |
| 6 | Web Lock System | `core/system/web_consistency_lock.py` |
| 7 | Session Start Hook | `.claude/hooks/session-start` |

---

_Last Updated: 2026-02-28_
_Version: 10.3 (Session Hygiene 추가)_
