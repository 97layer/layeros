# LAYER OS — System Architecture v1.0

> **목적**: 외부 에이전트 또는 신규 모델이 코드베이스를 역설계 없이 이해하는 단일 지도.
> **갱신 기준**: 에이전트 추가 / 파이프라인 변경 / 배포 구조 변경 시 동기화.
> **최종 갱신**: 2026-03-02

---

## 1. 핵심 원리

LAYER OS는 **신호(Signal)가 지식(Corpus)이 되고, 지식이 에세이(Essay)가 되고,
에세이가 다시 신호로 순환하는 자기강화 루프**다.

브랜드 철학(소거 → 영점 → 우화해)이 모든 연산의 필터다.
아키텍처는 그 철학을 코드로 구현한 물성이다.

---

## 2. 4축 파일 구조

```
97layerOS/
├── directives/     뇌 — 철학·규칙·이 문서
├── knowledge/      기억 — 신호·Corpus·상태
├── core/           엔진 — 에이전트·시스템·스크립트
└── website/        얼굴 — HTML/CSS/JS (Cloudflare Pages)
```

---

## 3. 유기적 순환 루프

```
┌─────────────────────────────────────────────────────────────┐
│                   THE CYCLE (자기강화 루프)                    │
│                                                             │
│  외부 세계                                                    │
│  (텔레그램 / YouTube / RSS)                                  │
│         │                                                   │
│         ▼  [수집]                                            │
│  knowledge/signals/          ← pub_*.json 재주입             │
│         │                    (loop closure)  ▲              │
│         ▼  [Orchestrator._scan_new_signals]  │              │
│  SA (StrategyAnalyst)                        │              │
│  core/agents/sa_agent.py                     │              │
│         │ analyze_signal()                   │              │
│         ▼  [_handle_sa_corpus]               │              │
│  knowledge/corpus/entries/                   │              │
│         │                                    │              │
│         ▼  [Gardener 군집 성숙 점검]           │              │
│  Gardener (core/agents/gardener.py)          │              │
│         │ _trigger_essay_for_cluster()       │              │
│         ▼  [CE 에세이 생성]                   │              │
│  CE (ChiefEditor)                            │              │
│  core/agents/ce_agent.py                     │              │
│         │ write_content()                    │              │
│         ▼  [Ralph Loop QA]                   │              │
│  EssayQualityValidator (4-Loop, 90점 기준)   │              │
│  core/utils/essay_quality_validator.py       │              │
│         │ score ≥ 90 → 통과                  │              │
│         ▼  [AD 시각 컨셉]                     │              │
│  AD (ArtDirector)                            │              │
│  core/agents/ad_agent.py                     │              │
│         │ create_visual_concept()            │              │
│         ▼  [CD 최종 게이트]                   │              │
│  CD (CreativeDirector)                       │              │
│  core/agents/cd_agent.py                     │              │
│         │ review_content()                   │              │
│         ▼  [승인]                             │              │
│  ContentPublisher                            │              │
│  core/system/content_publisher.py            │              │
│         │ publish()                          │              │
│         ├──→ website/archive/essay-NNN/      │              │
│         ├──→ Telegram (순호에게)              │              │
│         └──→ _inject_published_signal() ─────┘              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. 에이전트 매트릭스

| 에이전트 | 파일 | LLM | 입력 | 출력 | 품질 게이트 |
|---------|------|-----|------|------|------------|
| **SA** (Strategy Analyst) | `core/agents/sa_agent.py` | Gemini Flash | signal JSON | corpus entry | strategic_score ≥ 50 |
| **CE** (Chief Editor) | `core/agents/ce_agent.py` | Gemini Pro | corpus cluster | essay + caption | Ralph Loop 90점 |
| **AD** (Art Director) | `core/agents/ad_agent.py` | Gemini Pro | CE result | visual_concept | practice.md Part I |
| **CD** (Creative Director) | `core/agents/cd_agent.py` | Claude Sonnet | AD result | approve/reject | sage_architect.md §10 |
| **Gardener** | `core/agents/gardener.py` | Gemini Pro | corpus entries | cluster maturity | FROZEN 경계 |
| **Scout** | `core/agents/scout_agent.py` | — | RSS sources | signals | dedup |
| **Ralph** | `core/utils/essay_quality_validator.py` | regex | essay text | 0-100점 | 인라인 |

---

## 5. 파이프라인 오케스트레이터

**파일**: `core/system/pipeline_orchestrator.py`
**실행**: `run_forever(interval_seconds=30)` — 비동기 무한 폴링

```python
# 매 30초 사이클:
1. _scan_new_signals()          # knowledge/signals/ → SA 태스크 생성
2. _process_all_completed()     # 완료 태스크 dispatch
   ├── SA 완료 → _handle_sa_corpus()     # Corpus 누적
   ├── CE 완료 → _handle_ce_completed()  # Ralph QA → AD
   ├── AD 완료 → _handle_ad_completed()  # CD 리뷰
   └── CD 완료 → _handle_cd_completed()  # 승인→발행 / 거절→CE 재작업
```

**중복 방지**: `.infra/queue/orchestrated.json`
**재작업 한도**: CE 최대 2회 (Ralph 미달 또는 CD 거절)

---

## 6. 품질 게이트 레이어 (2-Stage)

```
Stage 1 — STAP (콘텐츠 전략):   practice.md §II-4
  5개 Pillar × 20점 = 100점. 70점+ 통과.

Stage 2 — Ralph Loop (언어 품질): sage_architect.md §6.5
  Loop 1: 시대 초월성   (25점) — 트렌드 표현 금지
  Loop 2: 논리 일관성   (25점) — 반복 구조 금지
  Loop 3: 클리셰 제거   (25점) — 빈 공감·강조 부사 금지
  Loop 4: 리듬/호흡     (25점) — 약한 명사 대체
  기준선: 90점. 미달 → CE 재작업.
```

---

## 7. 능동 사고 레이어 (ProactiveScan)

**파일**: `core/system/proactive_scan.py`
**적용**: 모든 에이전트 (CE/SA/AD/CD/Gardener/Scout)

```python
# 모든 주요 실행 전 자동 스캔:
① SIDE EFFECTS — FROZEN 파일 접근 감지 (침범 시 RuntimeError)
② BLIND SPOTS  — work_lock, 미로드 상태 감지
③ SIMPLER PATH — 빈 신호, 과다 재작업 등 불필요한 실행 감지

# FROZEN 경계: the_origin.md, sage_architect.md — 임의 수정 불가
# PROPOSE 경계: practice.md, agents/*.md — 순호 승인 후 적용
```

---

## 8. 문서 위계 (Authority Layers)

```
FROZEN   the_origin.md          — 세계관 SSOT (절대 불변)
FROZEN   sage_architect.md      — 인격 SSOT (CD 승인 완료)
         system.md              — 운영 매뉴얼
PROPOSE  practice.md            — 시각/언어/공간 규격
PROPOSE  directives/agents/     — 에이전트별 행동 지침
AUTO     knowledge/system/      — 상태·큐·메모리 (자동 갱신)
```

---

## 9. 인프라

| 구성요소 | 위치 | 역할 |
|---------|------|------|
| **Cloudflare Pages** | woohwahae.kr | 정적 웹사이트 (git push = 자동 배포) |
| **GCP VM** | 136.109.201.201 | 에이전트 데몬 실행 환경 |
| **nginx** | VM | api.woohwahae.kr → VM 역방향 프록시 |
| **systemd** | VM | 5개 서비스 상시 실행 |

**5개 active 서비스**:
- `97layer-telegram` — 텔레그램 봇 + ConversationEngine
- `97layer-ecosystem` — SA·CE·AD·CD 에이전트 풀
- `97layer-gardener` — Gardener 데몬 (매일 03:00)
- `woohwahae-backend` — REST API
- `cortex-admin` — 관리 인터페이스

---

## 10. 개발 규칙 빠른 참조

```bash
# 웹 배포
git push origin main              # Cloudflare Pages 자동 반영

# VM 배포
/deploy                           # 전체 배포 스킬

# 코드 품질
python3 core/scripts/build.py     # 빌드 + cache bust
```

**파일 생성 전**: `knowledge/system/filesystem_cache.json` 확인
**FROZEN 파일**: 절대 수정 금지 (the_origin.md, sage_architect.md)
**로깅**: f-string 금지, lazy `%` formatting 사용

---

_이 문서가 코드와 불일치하면 코드가 진실이다._
_코드가 이 문서와 불일치하면 이 문서를 수정하라._
