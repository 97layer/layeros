# HARNESS — WOOHWAHAE 풀스택 아키텍처 SSOT

> **상위**: the_origin.md → sage_architect.md → system.md
> **역할**: 브랜드가 하나의 유기체로 작동하는 레이어 구조 및 데이터 흐름 정의
> **권한**: PROPOSE (구조 변경 시 순호 승인 필요)
> **최종 갱신**: 2026-03-02

---

## 원칙

시스템이 곧 브랜드다.

에이전트들이 콘텐츠를 생산하는 도구가 아니다. 에이전트 시스템 자체가 소거(消去)의 세계관을 체화한다. 각 레이어는 덧씌워진 것을 걷어내는 방향으로 동작한다. 더하지 않는다. 드러낸다.

소거 렌즈 적용 기준: 각 레이어는 입력에서 본질 외의 것을 제거하여 출력으로 전달한다. 필터가 아니라 증류다.

---

## 레이어 구조

```
Layer 0: Foundation       the_origin.md           모든 판단의 세계관 원전
Layer 1: Perception       Scout + SA              외부 신호 수집 → 소거 렌즈 독해
Layer 2: Creation         CE + AD                 에세이 생성 + 시각 구현
Layer 3: Service          Ritual + practice.md    소거가 구현된 현장 경험
Layer 4: Distribution     Publisher + Ralph       품질 게이트 통과 후 발행
Layer 5: Evolution        Gardener + Growth       개념 성숙도 + 브랜드 패턴 추적
```

---

## Layer 0 — Foundation

| 항목 | 내용 |
|------|------|
| 문서 | `directives/the_origin.md` |
| 권한 | FROZEN |
| 역할 | 소거, 영점, 느림, 공명 — 4개 좌표 제공. 모든 에이전트 판단의 기준점 |
| 소거 렌즈 | 이 레이어 자체가 렌즈다. 읽는 것으로 적용된다 |
| 구현 상태 | ✅ v8.0.0 확정, 영점 동결 2026-03-02 |

---

## Layer 1 — Perception (인식)

### Scout (`core/agents/scout_agent.py`)

| 항목 | 내용 |
|------|------|
| 역할 | 외부 RSS/큐레이션 소스에서 신호 수집 |
| 입력 | RSS 피드, 외부 URL, 직접 주입 신호 |
| 출력 | `knowledge/signals/` 내 raw signal JSON |
| 소거 렌즈 | 수집하지 않는다. 관찰한다. 양보다 주파수 판별이 기준 |
| 핵심 제약 | 트렌드 소비형 신호 배제. "공명 가능성"이 수집 필터 |
| 구현 상태 | ✅ feedparser 기반 데몬 동작 (`--once` / `--forever` 모드) |

### SA — Strategy Analyst (`core/agents/sa_agent.py`)

| 항목 | 내용 |
|------|------|
| 역할 | 수집된 신호를 소거 렌즈로 독해. 전략적 인사이트 추출 |
| 입력 | `knowledge/signals/` raw signal |
| 출력 | 분석 결과 → `knowledge/corpus/` 누적 (Gardener 트리거 조건) |
| 소거 렌즈 | "최적화" 분석이 아니다. 덧씌워진 시장 담론을 걷어낸 후 남는 패턴을 읽는다 |
| LLM | Gemini 2.5 Flash (REST API) |
| 구현 상태 | ✅ AgentWatcher 큐 기반 독립 동작 |
| 갭 | 신호 필터링에 브랜드 세계관 점수(공명 가능성) 미반영. 현재는 전량 처리 |

**L1 데이터 흐름:**
```
외부 신호
  → Scout (수집)
  → knowledge/signals/{uuid}.json
  → SA (소거 렌즈 독해)
  → knowledge/corpus/entries/{uuid}.json
```

---

## Layer 2 — Creation (창작)

### CE — Chief Editor (`core/agents/ce_agent.py`)

| 항목 | 내용 |
|------|------|
| 역할 | Corpus 군집이 성숙하면 에세이 생성. sage_architect.md §10 6단계 구조 적용 |
| 입력 | Gardener 트리거 (군집 성숙 신호) + corpus entries |
| 출력 | Archive 에세이 (`knowledge/corpus/entries/` 또는 `website/archive/`) |
| 소거 렌즈 | "무엇을 쓸 것인가"보다 "무엇을 생략할 것인가"가 기준. Ralph Loop 90점 이상 강제 |
| LLM | Gemini 2.5 Pro |
| Brand Reference | NotebookLM MCP (쿠키 인증 기반 RAG) |
| 구현 상태 | ✅ AgentWatcher 큐 기반, Ralph 인라인 QA 게이트 포함 |
| 갭 | NotebookLM 연동은 쿠키 의존적. 인증 만료 시 fallback 없이 degraded 동작 |

### AD — Art Director (`core/agents/ad_agent.py`)

| 항목 | 내용 |
|------|------|
| 역할 | CE 산출물 기반 시각 개념 설계. 이미지 프롬프트 생성 |
| 입력 | CE 완료 태스크 (에세이 텍스트) |
| 출력 | 시각 컨셉, 이미지 생성 프롬프트, 스타일 가이드 |
| 소거 렌즈 | 실용적 미학(Practical Aesthetics). "무엇을 더할 것인가"가 아닌 "무엇이 없어도 되는가" |
| LLM | Gemini 2.5 Pro (Vision 활성) |
| Visual Reference | practice.md Part I 디자인 토큰 (`directive_loader` 경유) |
| 구현 상태 | ✅ 구조 동작. 실제 이미지 생성(Imagen)은 ⏳ 미연동 |

**L2 데이터 흐름:**
```
knowledge/corpus/ (군집 성숙)
  → Gardener 트리거
  → CE (에세이 생성 + Ralph QA)
  → CE 완료 태스크
  → AD (시각 개념)
  → AD 완료 태스크
  → Layer 4 (CD → Publisher)
```

---

## Layer 3 — Service (현장)

### Ritual (`core/system/ritual.py`)

| 항목 | 내용 |
|------|------|
| 역할 | 아틀리에 고객 프로필, 방문 기록, 재방문 리듬 관리 |
| 입력 | 고객 정보, 방문 데이터 (수동 입력) |
| 출력 | `knowledge/clients/{client_id}.json` |
| 소거 렌즈 | 소거가 구현된 서비스 현장. "이치고 이치에(一期一会)". 고객이 아닌 사람. 재방문 리듬이 KPI |
| 구현 상태 | ✅ CRUD 완료. 스키마: `knowledge/system/schemas/ritual_client.schema.json` |
| 갭 | Ritual 데이터가 Growth 분석 및 SA 신호 피드백 루프와 단절. 현장 패턴이 L1으로 역류하지 않음 |

### Practice (`directives/practice.md`)

| 항목 | 내용 |
|------|------|
| 역할 | 외부 서비스 페이지 카피 기준. Part I 시각 규격, Part II 언어 규격, Part III 공간 규격 |
| 입력 | sage_architect.md §4 (어조 지형) |
| 출력 | website/ 서비스 페이지 카피 기준 (담백 모드 적용) |
| 소거 렌즈 | "기능만 남기고 모든 장식을 소거". 주어와 술어 직결 |
| 구현 상태 | ✅ 문서 완료. AD/CE 에이전트가 directive_loader로 섹션 단위 로드 |

**L3 데이터 흐름:**
```
방문 고객 경험 데이터
  → Ritual (프로필/기록)
  → knowledge/clients/

practice.md (시각/언어/공간 규격)
  → AD/CE directive_loader
  → website/ 서비스 페이지
```

---

## Layer 4 — Distribution (배포)

### Ralph QA (인라인 게이트)

| 항목 | 내용 |
|------|------|
| 역할 | 모든 레이어 통과 품질 게이트. CE→AD 이동 전 강제 검증 |
| 기준 | sage_architect.md §6.5 Ralph Loop. 4단계 스캔. 기준선 90점 |
| 소거 렌즈 | 클리셰, 시대 한정 어휘, 빈 공감 동사 제거. "소거의 언어 품질 게이트" |
| 구현 상태 | ✅ `core/utils/essay_quality_validator.py` 자동화. PipelineOrchestrator 인라인 통합 |
| 갭 | 70점 이상 통과 기준 (RALPH_PASS_SCORE=70). sage_architect.md 기준선 90점과 불일치 |

### Publisher (`core/system/content_publisher.py`)

| 항목 | 내용 |
|------|------|
| 역할 | CD 승인 후 최종 패키징 + 배포. Instagram + Archive 에세이 + Telegram push |
| 입력 | AD 완료 산출물 + CD 승인 신호 |
| 출력 | `knowledge/assets/published/YYYY-MM-DD/` (캡션, 해시태그, 에세이, 이미지) |
| 소거 렌즈 | 설명 없이 공명. 브랜드 주어 삭제, 감성 수식 제거 (sage_architect.md §4 카피 원칙) |
| 구현 상태 | ✅ Telegram 연동. Imagen 이미지 생성 ⏳ 미연동 |

**L4 데이터 흐름:**
```
CE 산출물
  → Ralph QA (점수 < 90: CE 재작업, ≥ 90: 통과)
  → AD 산출물
  → CD 검토 (propose_gate.py — Telegram 승인)
  → Publisher (패키징 + 배포)
  → website/archive/ + Telegram 채널
```

---

## Layer 5 — Evolution (자가 진화)

### Gardener (`core/agents/gardener.py`)

| 항목 | 내용 |
|------|------|
| 역할 | corpus 군집 성숙도 분석. 성숙 시 CE 트리거. 시스템 자가 진화 제안 |
| 입력 | `knowledge/corpus/entries/` 누적 데이터 |
| 출력 | CE 트리거 신호 + 주간 Telegram 리포트 + PROPOSE 개선안 |
| 소거 렌즈 | "신호의 지층화". 군집이 충분히 쌓일 때까지 기다린다. 서두르지 않는다 |
| 수정 권한 | FROZEN(the_origin, sage_architect) / PROPOSE(agents/*.md) / AUTO(state.md, signals) |
| 구현 상태 | ✅ 새벽 3시 데몬. 주간 리포트 자동화 |
| 갭 | 군집 성숙 판별 기준이 양적 임계치 기반. "공명 가능성" 같은 질적 기준 미반영 |

### Growth (`core/system/growth.py`)

| 항목 | 내용 |
|------|------|
| 역할 | 월별 수익/콘텐츠/서비스 지표 수집 + 추세 분석 |
| 입력 | Ritual 방문 데이터, corpus 콘텐츠 수, 수동 수익 입력 |
| 출력 | `knowledge/reports/growth/growth_YYYYMM.json` |
| 소거 렌즈 | "최적화" 추구가 아니다. 브랜드 패턴 추적. 수치가 방향의 신호일 뿐 |
| 구현 상태 | ✅ 월별 CRUD + 자동 집계. 스키마: `knowledge/system/schemas/growth_metrics.schema.json` |

**L5 데이터 흐름:**
```
knowledge/corpus/ (누적)
  → Gardener (군집 성숙도 분석)
  → CE 트리거 (성숙 임계치 도달 시)
  → 주간 Telegram 리포트 (every Monday)

knowledge/clients/ + knowledge/corpus/ + website/archive/
  → Growth (월별 지표 집계)
  → knowledge/reports/growth/growth_YYYYMM.json
```

---

## 전체 파이프라인 흐름

```
[외부]
  RSS/신호
    └─ Scout ────────────────────────── knowledge/signals/

[L1 Perception]
  knowledge/signals/
    └─ SA (소거 렌즈 독해) ───────────── knowledge/corpus/entries/

[L5 Evolution — 트리거]
  knowledge/corpus/entries/
    └─ Gardener (군집 성숙 감지) ──────► CE 트리거

[L2 Creation]
  CE 트리거
    └─ CE (에세이 생성)
         └─ Ralph QA (인라인, ≥90점)
              └─ AD (시각 개념)

[L4 Distribution]
  AD 완료
    └─ CD 검토 (propose_gate, Telegram)
         ├─ 승인 → Publisher → website/archive/ + Telegram
         └─ 거절 → CE 재작업 (max 2회)

[L3 Service — 병렬]
  방문 고객
    └─ Ritual ──────────────────────── knowledge/clients/
  practice.md
    └─ directive_loader ────────────── website/ 서비스 페이지 (AD/CE 참조)

[L5 Evolution — 집계]
  knowledge/clients/ + corpus/ + website/archive/
    └─ Growth ──────────────────────── knowledge/reports/growth/
```

---

## 에이전트-파일 매핑

| 에이전트/모듈 | 코드 경로 | 입력 경로 | 출력 경로 | 지시 문서 |
|---|---|---|---|---|
| Scout | `core/agents/scout_agent.py` | 외부 RSS | `knowledge/signals/` | — |
| SA | `core/agents/sa_agent.py` | `knowledge/signals/` | `knowledge/corpus/entries/` | `directives/agents/sa.md` |
| CE | `core/agents/ce_agent.py` | corpus + Gardener 트리거 | 에세이 태스크 | `directives/agents/ce.md` |
| AD | `core/agents/ad_agent.py` | CE 완료 태스크 | 시각 컨셉 태스크 | `directives/agents/ad.md` |
| Ralph | `core/utils/essay_quality_validator.py` | CE 산출물 | QA 점수/통과 신호 | `sage_architect.md §6.5` |
| Publisher | `core/system/content_publisher.py` | AD 완료 + CD 승인 | `knowledge/assets/published/` | `sage_architect.md §4` |
| Gardener | `core/agents/gardener.py` | `knowledge/corpus/entries/` | CE 트리거 + Telegram | `directives/system.md §2` |
| Growth | `core/system/growth.py` | clients + corpus + archive | `knowledge/reports/growth/` | `directives/system.md §1` |
| Ritual | `core/system/ritual.py` | 수동 입력 | `knowledge/clients/` | `sage_architect.md §4` |
| Orchestrator | `core/system/pipeline_orchestrator.py` | 큐 이벤트 | 다음 단계 태스크 생성 | `directives/system.md §3` |

---

## 구현 상태 요약

| Layer | 컴포넌트 | 상태 | 비고 |
|-------|----------|------|------|
| 0 | Foundation (the_origin.md) | ✅ | FROZEN, 영점 동결 |
| 1 | Scout | ✅ | feedparser 데몬 |
| 1 | SA | ✅ | Gemini Flash, 큐 기반 |
| 2 | CE | ✅ | NotebookLM RAG 연동 (쿠키 의존) |
| 2 | AD | ✅ | 시각 컨셉 생성. Imagen ⏳ |
| 3 | Ritual | ✅ | CRUD 완료 |
| 3 | Practice (문서) | ✅ | directive_loader 연동 |
| 4 | Ralph QA | ✅ | 자동화. 기준점 조정 필요 |
| 4 | Publisher | ✅ | Telegram 연동. Imagen ⏳ |
| 5 | Gardener | ✅ | 새벽 3시 데몬 |
| 5 | Growth | ✅ | 월별 집계 |

---

## 주요 갭 (현재 구현 vs 설계)

### GAP-1: Ralph QA 기준선 불일치
- **설계**: `sage_architect.md §6.5` — 기준선 90점
- **구현**: `pipeline_orchestrator.py` — `RALPH_PASS_SCORE = 70`
- **영향**: 브랜드 세계관 기준 미달 에세이가 AD 단계로 진행 가능
- **조치**: `RALPH_PASS_SCORE` 90으로 상향. 단, CE 재작업 루프 안정성 검증 후 적용

### GAP-2: L3 Service → L1 Perception 역류 단절
- **설계**: Ritual(현장 경험 데이터)이 브랜드 패턴으로 순환되어 SA의 신호 판독 기준을 갱신해야 함
- **구현**: Ritual 데이터(`knowledge/clients/`)가 Growth 집계로만 연결. SA 피드백 루프 없음
- **영향**: 현장에서 발견되는 패턴(방문 리듬, 고객 주파수)이 콘텐츠 방향에 반영되지 않음
- **조치**: Growth 월간 리포트 → SA 신호 inject 파이프 설계 필요

### GAP-3: 신호 수집 필터에 브랜드 공명 기준 부재
- **설계**: Scout는 "수집하지 않고 관찰"해야 함. 공명 가능성이 수집 필터
- **구현**: Scout는 RSS 전량 수집 후 SA에 위임. 필터링 기준 없음
- **영향**: SA가 처리해야 할 노이즈 신호 과다. "느림"의 원칙에 반함
- **조치**: Scout에 브랜드 허용 키워드 기반 1차 필터 추가 (`sage_architect.md §5` 허용 키워드 활용)

---

## 거버넌스

| 항목 | 기준 문서 |
|------|-----------|
| 세계관 판단 | `directives/the_origin.md` |
| 어조/언어 규격 | `directives/sage_architect.md` |
| 운영 프로토콜 | `directives/system.md` |
| 시각/서비스 규격 | `directives/practice.md` |
| 에이전트 역할 발현 | `directives/agents/sa.md`, `ce.md`, `ad.md` |
| 수정 권한 3단계 | FROZEN / PROPOSE / AUTO (system.md §2) |

---

> 이 문서는 구현 현황 추적 문서다. 철학 선언이 아니다.
> 레이어가 추가되거나 에이전트가 변경될 때마다 갱신한다.
> 상위 문서(the_origin.md, sage_architect.md)는 이 문서로 수정되지 않는다.
