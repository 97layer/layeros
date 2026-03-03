---
description: 딥워크 세션 — 플랜에서 TODO 추출 후 사용자 개입 없이 완료까지 실행
---

# /deepwork — 딥워크 자율 실행

## 즉시 실행 순서

**1. deepwork.md 초기화**

`knowledge/agent_hub/deepwork.md`를 아래 형식으로 덮어쓴다:

```
status: active
task: $ARGUMENTS
plan: [현재 plan 파일 — 없으면 —]
started: [현재 시각]
last_activity: [현재 시각]

## TODO
- [ ] [작업 1]
- [ ] [작업 2]
...

## Modified
```

플랜 파일이 있으면 (`~/.claude/plans/*.md`) 내용에서 TODO 추출.
없으면 $ARGUMENTS 기반으로 합리적 TODO 리스트 직접 작성.

**2. 실행 루프 — 핵심 규칙**

- 스크린샷 찍고 사용자 대기: **절대 금지**
- CSS/레이아웃 검증: `puppeteer_evaluate`로 `visual-validate.js` 실행 → 수치로 판단
- fail → 자가 수정 → 재측정 → 반복 (사용자 보고 없음)
- HTML/CSS 수정 후: `puppeteer_navigate(현재URL)` 리로드 → evaluate 측정
- 각 TODO 완료 시: deepwork.md의 `- [ ]` → `- [x]` 로 수정

**3. 블로커 조건 (이것만 사용자에게 질문)**

- 존재하지 않는 외부 파일/API 키
- 3회 수정 후에도 동일 fail 반복 시 (원인 설명 + 선택지 제시)

**4. 완료**

- 모든 `- [ ]` → `- [x]` 확인
- 빌드: `python3 core/scripts/build.py --components --bust`
- 커밋 + push
- deepwork.md `status: idle`로 갱신
- 완료 보고 **1회만** (무엇을 했는지, 수치 결과)

## 컨텍스트 압축 후 재개

session-start가 deepwork.md를 자동 주입한다.
`## TODO`에서 미완료 항목 확인 → `## Modified`에서 이미 수정된 파일 확인 → 중단 지점부터 질문 없이 재개.

## visual-validate.js 사용법

```javascript
// puppeteer_evaluate에 아래 내용 붙여넣기
// website/assets/js/visual-validate.js 참조
// 결과: { verdict: "✅ PASS" | "❌ FAIL", fail: N, details: {...} }
```
