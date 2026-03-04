# Homepage Design Plan (Preflight)

- Date: 2026-03-04
- Scope: 홈페이지 IA + 섹션 카피 초안 (구현 전 단계)
- Source of truth: directives/the_origin.md, directives/sage_architect.md, directives/practice.md Part I/II
- Council status: degraded / hard_stop (dual model unavailable)

## 1. 전제 및 제한

1. 현재 Plan Council은 Claude/Gemini 동시 호출 실패 상태입니다.
2. 따라서 이 문서는 구현 지시서가 아니라 안전한 preflight 설계안입니다.
3. 웹 파일(`website/`) 수정은 정규 협의 READY 재확인 후 시작합니다.

## 2. 목표 정의

1. 홈페이지를 `입구`로 고정합니다.
2. 첫 화면에서 브랜드 원리(소거)와 이동 경로(Archive/Practice/About)를 동시에 인지시킵니다.
3. 스크롤 이후에는 정보 밀도를 올려 실사용 경로를 분명하게 제시합니다.

## 3. IA 초안 (Home)

1. Hero Field (기존 유지)
- 목적: 브랜드 좌표 고정 + 1차 분기(Archive/Practice/About)
- 구성: kicker 1줄 + statement 1~2줄 + 3개 nav item

2. Section A: What Stays
- 목적: 홈페이지 방문 즉시 브랜드 작동 원리 제시
- 구성: 짧은 선언문 2~3문장 + 핵심 명사 3개(리듬/여백/기록)

3. Section B: Archive Preview
- 목적: 사유 기록 진입
- 구성: 최신 글 3개 카드 + Archive 전체 보기 링크

4. Section C: Practice Preview
- 목적: 서비스/실천 연결
- 구성: Practice 핵심 블록 3개(Atelier/Direction/Project)

5. Section D: About Bridge
- 목적: 창시자 페르소나와 세계관 연결
- 구성: 1문단 + About 이동 CTA

6. Footer (공통 컴포넌트 유지)
- 목적: 법적/연락 정보 고정

## 4. 섹션별 카피 초안

1. Hero
- Kicker: `WOOHWAHAE FIELD`
- Statement: `걷어낸 자리에서 남는 리듬을 기록하고, 일상의 실천으로 연결합니다.`

2. Section A: What Stays
- Label: `01. WHAT STAYS`
- Heading: `덜어낼수록, 기준이 보입니다.`
- Body: `많이 더하는 방식으로는 방향을 지키기 어렵습니다. 덧씌워진 기준을 걷어내고 남는 것을 기준으로 삼습니다.`

3. Section B: Archive Preview
- Label: `02. ARCHIVE`
- Heading: `관찰을 기록으로 남깁니다.`
- Body: `짧은 자극보다 오래 남는 문장을 선택합니다.`
- CTA: `Archive 보기`

4. Section C: Practice Preview
- Label: `03. PRACTICE`
- Heading: `생각을 형태로 옮깁니다.`
- Body: `공간, 손, 도구를 통해 일상의 리듬을 다시 맞춥니다.`
- CTA: `Practice 보기`

5. Section D: About Bridge
- Label: `04. ABOUT`
- Heading: `우화해는 명사가 아니라 동사입니다.`
- Body: `완성보다 반복을 기준으로 삼습니다. 걷어내는 실천이 쌓일 때, 본래의 방향이 드러납니다.`
- CTA: `About 보기`

## 5. 레이아웃/컴포넌트 초안

1. nav/footer는 기존 `_components`를 그대로 사용합니다.
2. Home 본문은 `max 960px` 그리드에서 2열(데스크톱) / 1열(모바일)로 전환합니다.
3. 모바일 우선 간격은 `space-sm → space-md`를 기본으로 적용합니다.
4. 인라인 스타일 금지, style.css 단일 소스로만 변경합니다.

## 6. 검증 시나리오 (구현 단계 진입 시)

1. lock
- `python3 core/system/web_consistency_lock.py --acquire AD --task "home ia/copy implementation"`
- `python3 core/system/web_consistency_lock.py --validate AD`

2. quality
- `python3 core/system/visual_validator.py`
- `python3 core/scripts/build.py --components --bust`

3. responsive smoke (playwright)
- viewport: 390, 768, 1440
- check: nav 가독성, hero 문장 줄바꿈, preview card 겹침 여부, footer 링크 접근성

4. release
- `python3 core/system/web_consistency_lock.py --release AD`

## 7. 역할 분담 (Agent Routing)

1. Claude
- IA/카피 방향성 확정
- 금칙어/어조 리스크 사전 검토

2. Codex
- 컴포넌트 구조 변경
- CSS/JS 최소 변경 구현
- 검증 명령 실행 및 결과 정리

3. Gemini
- 카피/IA 비평
- 회귀 및 누락 시나리오 검증

## 8. 리스크 및 대응

1. 리스크: Plan Council degraded로 이견 검증 부재
- 대응: 구현 전 정규 council READY 재실행

2. 리스크: 홈 비주얼 과밀화
- 대응: 섹션당 메시지 1개 원칙 유지, 보조문장 2문장 제한

3. 리스크: 모바일 가독성 저하
- 대응: 390px 우선 점검, 긴 문장 강제 분할

## 9. 착수 게이트

1. `plan_dispatch --auto` 결과가 READY 또는 최소 안정권으로 회복될 것
2. `evidence_guard --check`가 READY일 것
3. web lock acquire/validate 완료 후 편집 시작
