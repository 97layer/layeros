# PRACTICE — 브랜드 실행 규격

> **상위**: sage_architect.md (인격 SSOT)
> **역할**: 브랜드가 세상과 닿는 모든 접점의 물리적 규격.
> **권한**: PROPOSE
> **구조**: Part I 시각 / Part II 언어 / Part III 공간

---

# Part I. 시각 (Visual)

> 참조 에이전트: AD (필수), CE (이미지 선정 시)
> CSS SSOT. style.css 변경 시 반드시 동기화.

---

## I-0. 시각의 침묵 (Visual Silence)

사유를 담아내는 공간의 기본 콘셉트: **"낡은 종이 위에 0.5mm 연필선으로 그린 동심원의 파동"**.

창백하게 낡아가는 회색빛(#E3E2E0) 종이와 먹처럼 단정한 검은 잉크(#1A1A1A)만 허용한다. 덧칠이 아니라 긁어내듯 그린다.

인간의 호흡에 가장 닿아 있는 **3.8초의 맥동**과 절대적으로 강제된 **60% 이상의 텅 빈 여백**. 화면은 화려한 캔버스가 아니라 사유를 담기 위한 빈 그릇이다.

가벼움과 무의미한 유행을 경계한다. 구도자의 도면을 닮은 극단적인 폰트(IBM Plex Mono)만을 건축 자재로 사용한다.

---

## I-1. Colors

### 우선순위 체계

| Token | 값 | 용도 | 우선순위 |
|-------|-----|------|---------|
| `--bg` | #E3E2E0 | 메인 배경 (낡은 종이) | ★★★ PRIMARY |
| `--bg-dark` | #DDDCDA | 보조 배경 | ★★★ PRIMARY |
| `--text` | #1a1a1a | 본문 텍스트 (잉크) | ★★★ PRIMARY |
| `--text-sub` | #4a4a4a | 보조 텍스트 | ★★★ PRIMARY |
| `--text-faint` | #7A7A74 | 희미한 텍스트 (WCAG AA 4.5:1 확보) | ★★★ PRIMARY |
| `--white` | #FFFFFF | 흰색 (반전용) | ★★★ PRIMARY |
| `--line` | #D5D4CF | 구분선 | ★★★ PRIMARY |

### Stone Palette (SECONDARY)

| Token | 값 | 용도 |
|-------|-----|------|
| `--stone-dark` | #7A6E5A | 어두운 갈색 (그림자, 강조) |
| `--stone-mid` | #8B7355 | 중간 갈색 (텍스트 포인트) |
| `--stone-light` | #A89880 | 밝은 갈색 (배경 톤) |

### Deep Navy (OPTIONAL)

| Token | 값 | 용도 |
|-------|-----|------|
| `--navy` | #1B2D4F | ::selection, blockquote border |

**원칙**: Monochrome 기본 (90%+). Warm Gray 포인트 (10%). Deep Navy 극소수 영역만.
**금지**: 비비드 계열의 과도한 색채.

---

## I-2. Typography

| Token | 값 | 용도 |
|-------|-----|------|
| `--font-body` | Pretendard Variable | 본문 (한국어 가독성) |
| `--font-mono` | IBM Plex Mono | 레이블, 코드, 보조 텍스트 |

> **폰트 규칙**: Pretendard + IBM Plex Mono만 사용. Crimson Text 사용 금지. italic 사용 금지. 텍스트에 색상 없음 (--text / --text-sub / --text-faint만 허용).

| Token | 값 | 용도 |
|-------|-----|------|
| `--ls-label` | 0.10em | nav, section-label |
| `--ls-wide` | 0.16em | 카테고리, 필터 버튼 |
| `--ls-heading` | -0.03em | h1, h2 헤딩 |

| Token | 값 |
|-------|-----|
| `--fw-thin` | 200 |
| `--fw-light` | 300 |
| `--fw-regular` | 400 |
| `--fw-medium` | 500 |

---

## I-3. Spacing

| Token | 값 | 용도 |
|-------|-----|------|
| `--space-xs` | 0.5rem | 최소 간격 |
| `--space-sm` | 1rem | 요소 내부 |
| `--space-md` | 2rem | 섹션 내부 |
| `--space-lg` | 4rem | 섹션 간 |
| `--space-xl` | 8rem | 대형 여백 |
| `--space-2xl` | 12rem | 히어로 여백 |

| Token | 값 |
|-------|-----|
| `--max-content` | 680px |
| `--max-wide` | 960px |

---

## I-4. Breath System

> 인간의 호흡 주기 ~0.27Hz(3.8초)를 시각적 맥동의 기준으로 삼는다.

| Token | 값 | 의미 |
|-------|-----|------|
| `--breath` | 3.8s | 한 호흡 주기 |
| `--breath-half` | 1.9s | 반 호흡 |
| `--breath-quarter` | 0.95s | 1/4 호흡 |

시간대별 변조: dawn 4.8s / day 3.8s / evening 4.2s / night 5.2s

| Token | 값 | 성격 |
|-------|-----|------|
| `--ease-wave` | cubic-bezier(0.37, 0, 0.63, 1) | 정현파 근사 S곡선 |
| `--ease-out` | cubic-bezier(0.16, 1, 0.3, 1) | 내쉬는 곡선 |
| `--duration` | 0.6s | 기본 전환 |
| `--duration-slow` | 1.2s | 중요 요소 |

---

## I-5. Glassmorphism

| Token | 값 |
|-------|-----|
| `--glass-surface` | rgba(255, 255, 255, 0) |
| `--glass-blur` | saturate(180%) blur(20px) |
| `--glass-border` | rgba(0, 0, 0, 0.05) |

---

## I-6. Photography

- 톤: 채도를 낮춘 차분한 색감 (muted, desaturated)
- 질감: 35mm 필름 그레인
- 구도: 여백(Negative space)을 우선하는 삼분할법
- 조명: 자연광, 깊이를 더하는 그림자
- 금지: 과포화, 플래시, 작위적 보정

---

## I-7. Family Look

### 마이크로 디테일 감도

| 요소 | 규격 |
|------|------|
| SVG 선 | `stroke-width: 0.5` |
| SVG 노드 | `r: 3.5px`, opacity 단계 (0.9→0.7→0.5→0.35) |
| SVG 레이블 | IBM Plex Mono 9px, 300, ls 0.1em |
| 드로잉 모션 | `stroke-dashoffset` 2s ease-out |
| 순차 페이드 | 0.4s 간격 stagger |
| blockquote | navy 1px 좌측 border + Crimson Text italic |
| 제목 이탈릭 | font-weight 200, italic, clamp(1.5-2.2rem) |

### 배경 레이어

| 페이지 | z-0 배경 | 구현 |
|--------|---------|------|
| Home | Three.js 쌍극자 자기장 | `bg-field.js` + `<canvas>` |
| 내부 페이지 | SVG 동심원 파동 (3.8s) | `<div class="wave-bg">` |
| 에세이 | 없음 (텍스트 집중) | 배경 비움 |

Three.js: 색상 #E3E2E0, 선 96/32개, 곡선 500/120pt, Fog 0.035, prefers-reduced-motion 감지.

### 모션 패밀리

| 이름 | CSS |
|------|-----|
| `wave-fade-in` | opacity 0→1, translateY 12→0, 2.4s ease-wave |
| `line-breathe` | opacity 1↔0.5, --breath 주기 |
| `[data-reveal]` | opacity 0→1, translateY 16→0, IO threshold 0.12 |

### 레이아웃 프레임

```
┌─────────────────────────────────┐
│ nav-brand    Archive Practice About │ ← 고정 상단
├─────────────────────────────────┤
│      [wave-bg: 동심원 파동]         │ ← z-0, fixed
│   ┌──── max 680px ────┐          │
│   │  section-label     │          │ ← z-1
│   │  headline          │          │
│   │  body text         │          │
│   └────────────────────┘          │
│   ┌──── max 960px ────┐          │
│   │  card grid (2col)  │          │
│   └────────────────────┘          │
├─────────────────────────────────┤
│ footer: brand · nav · legal · ©    │
└─────────────────────────────────┘
```

---

## I-8. Symbol & Wordmark

심볼: 전각(篆刻) 인장 형태 우화(羽化) 나비 문양.
에셋: `website/assets/media/brand/` (symbol.svg/png/jpg, icon-192/512.png)
최소 크기: 24px(웹), 8mm(인쇄). 보호 영역: 심볼 높이 50%.
워드마크: `WOOHWAHAE` — IBM Plex Mono, 300, ls 0.10em, uppercase.
금지: 비율 왜곡, 텍스트 오버레이, 그림자/글로우, 컬러 변형.

---

## I-9. 웹 경험 설계

### 사이트 구조 (IA)

```text
woohwahae.kr/
├── about/     브랜드 서사
├── archive/   매거진 (essay-NNN, magazine/, lookbook/)
├── practice/  수행의 실천 (아틀리에, 디렉션, 프로젝트, 프로덕트, 연락)
├── woosunho/  에디터 포트폴리오
└── lab/       실험 (네비 미노출)
```

네비: `Archive | Practice | About` — 고정 상단, 드롭다운 없음.

### 기술 스택

순수 HTML/CSS/JS. 프레임워크 없음. 모바일 우선. Cloudflare Pages 배포.

### 금지된 경험

팝업/모달/강제 구독/좋아요 수/외부 광고/맥락 없는 레이아웃 변경.

---

# Part II. 언어 (Content)

> 참조 에이전트: CE (필수), SA, Ralph/QA (품질 게이트)

---

## II-1. 에세이 구조

About 페이지 역설계 기반 원칙. CE `write_corpus_essay()` 프롬프트가 SSOT.

- **첫 문장**: 물리적·감각적 관찰로 시작. 원리 선언 금지.
- **비유**: 섹션당 1개. 겹치면 초점 분산.
- **리듬**: 단언(단문) → 탐구(복문) → 열린 결말
- **마무리**: 결론 맺지 않는다. 독자가 다음을 느끼게.
- **전환**: 명시하지 않는다. 이전 섹션의 마지막 이미지가 다음을 불러들임.
- **교훈**: 금지. 관찰만. 독자를 이끌거나 설득하지 않는다.
- **접속사**: 최소화. "또한/그리고/뿐만 아니라" → 단문 분리.
- **수식어**: 1문장 1개 이하.

---

## II-2. 어조 규격

sage_architect.md §4-§6이 SSOT. 본 문서에서는 중복 나열하지 않는다.

---

## II-3. 이슈 발행 프로토콜

Issue = 하나의 브랜드 또는 개념에 대한 깊이 있는 탐구.
구성: Cover(AD 검증) + Title + Body(에세이) + Metadata(themes[], date, slug).
소싱: Brand Scout 크롤링 / 텔레그램 신호 → 군집 성숙.

---

## II-4. 품질 게이트 (STAP v4.0)

- **S (Stop)**: 완성 조건 명확화
- **T (Task)**: CE 에세이 수신 → 기준 대조
- **A (Assess)**: 5-pillar 점수화 (각 20점, 총 100점)
- **P (Process)**: 70점+ 통과 → AD. 미달 → CE 피드백.

| Pillar | 배점 | 기준 |
|--------|------|------|
| 사유의 질량 | 20 | 시간의 퇴적이 느껴지는 깊이 |
| 진정성의 고립 | 20 | 내면 관찰. 인용이 사유를 대신하지 않는가 |
| 실효적 파동 | 20 | 독자의 일상 물성에 닿는가 |
| 사유의 여백 | 20 | 독자가 스스로 사유할 틈 |
| 고유한 주파수 | 20 | 이 글이 아니면 존재하지 않을 문장인가 |

---

## II-5. 카테고리 × 타입

### 카테고리 (주제)

| 카테고리 | 정의 |
|----------|------|
| Seeing | 철학, 관점, 감각적 관찰 |
| Living | 라이프스타일, 공간, 일상 |
| Working | 직업, 미용, 아틀리에 철학 |
| Making | 시스템, 브랜딩, 빌드 과정 |
| Listening | 관계, 공명, 타인과의 접점 |

### 타입 (형식)

| 타입 | 어체 | 구조 | 길이 |
|------|------|------|------|
| Essay | 한다체 | 감각 관찰 → 탐구 → 열린 결말 | 300-800자 |
| Journal | 합니다체 | 리드+본문+실천 | 1200-3000자 |

---

## II-6. 콘텐츠 파이프라인

```
Signal → [SA] 분석 → [Gardener] 군집 성숙 → [CE] 에세이
  → [Ralph] STAP 검증 → [AD] 시각 검증 → [CD] 최종 승인 → 발행
```

---

## II-7. 5포맷 변환

| # | 포맷 | 용도 |
|---|------|------|
| 1 | 본문 기록 | Archive 발행 |
| 2 | 시선의 조각 | SNS 캡션 (가장 울림 있는 단락 발췌) |
| 3 | 신호 요약 | 내부 알림 |
| 4 | 한 줄 | 메타정보 (검색/공유용) |
| 5 | 주파수 | 핵심 키워드 (명사 3개 이내) |

---

## II-8. 카피 원칙

> **채널별 어조 SSOT → `sage_architect.md §4`**

Archive 에세이 기준: 한다체. 짧게. 마침표. 브랜드 주어 금지. 행위/현상이 주어.

---

## II-9. 공명 대상

### 공명자 (Resonator)

고유한 리듬질서를 지키며 살아가는 사람들. 태도로 관측:
- 속도보다 방향을 택하는 사람
- "왜?"를 먼저 묻는 사람
- 적게 갖되 깊이 쓰는 사람
- 동아시아적 감수성에 반응하는 사람

### 페르소나

| 페르소나 | 태도 | 접점 |
|---------|------|------|
| 고요한 실천자 | 자기만의 리듬 | Archive, Service |
| 감각적 창작자 | 시스템/철학 구축 | Archive, Project |
| 느린 관찰자 | 속도 마모 경계 | Practice, Archive |

### Anti-Audience

빠른 결실만 쫓는 사람 / 유행에 몸을 맡기는 사람 / 즉각적 자극만 원하는 사람.
걸러내는 것 자체가 정체성.

---

# Part III. 공간 (Service)

> 참조: Ritual Module (L4 Service Layer)

---

## III-1. 아틀리에 철학

헤어 아틀리에는 기술을 파는 공간이 아니다. 사람을 만나는 공간이다.
**Wash & Go**: 매일 아침 30초로 완성되는 헤어. 과도한 유지보수가 필요한 스타일은 시간을 빼앗는다.

---

## III-2. Client Journey (7단계)

| # | 단계 | 핵심 |
|---|------|------|
| 1 | Signal (발견) | 억지 광고 없이 주파수가 닿는다 |
| 2 | Resonance (공명) | woohwahae.kr 탐색 및 에세이 교감 |
| 3 | Transition (전환) | 3일 전 예약 확정. 조용하고 정확한 톤 |
| 4 | Submersion (입수) | 트렌드가 아닌 일상 리듬 기반 상담 |
| 5 | Circulation (순환) | 조용한 시술. 침묵. 본질에 집중 |
| 6 | Object (물성) | 홈케어 가이드(Wash & Go). 재방문 압박 금지 |
| 7 | Echo (잔향) | 방문 기록 보존. 비강제적 리듬 알림 |

---

## III-3. 커뮤니케이션 프로토콜

| 상황 | 톤 | 예시 |
|------|-----|------|
| 예약 확인 | 정중, 간결 | "2월 28일 14시 예약 확인되었습니다." |
| 변경/취소 | 이해, 명확 | "변경 가능합니다. 희망 일시를 알려주세요." |
| 홈케어 안내 | 실용, 구체 | "2일에 한 번 세정, 타월 드라이 후 자연 건조." |
| 재방문 알림 | 제안, 비강제 | "마지막 방문 6주 전입니다. 시간 되실 때 알려주세요." |

---

## III-4. Product (미활성 — 2027 Expansion)

선정 기준: 본질주의 (더 뺄 것이 있는가?) / 수행성 (의식에 편입 가능?) / 시간성 (가치가 깊어지는가?)
카테고리: 케어(헤어/스킨) / 공간(향/오브제) / 기록(노트/펜)

---

## 공통 금지

- 트렌드 스타일/제품 강요
- "이번 시즌 유행" 언급
- 과도한 제품 추천 / 재방문 압박
- 후기 요청
- 브랜드 로고가 주가 되는 제품

---

**Last Updated**: 2026-02-27
