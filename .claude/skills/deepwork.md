# /deepwork — 딥워크 세션 시작

## 트리거
`/deepwork [작업명]` 또는 `deepwork.md status: active` 감지 시

## 실행 프로토콜

### 1. 딥워크 초기화
args가 있으면 deepwork.md를 새로 작성:

```
status: active
task: [args]
plan: [현재 plan 파일 경로 — 없으면 —]
started: [현재 시각]
last_activity: [현재 시각]

## TODO
- [ ] [플랜에서 추출한 항목 1]
- [ ] [항목 2]
...

## Modified
```

### 2. 실행 루프 (핵심 규칙)

**금지 행동:**
- 스크린샷 찍고 사용자에게 제시하며 대기 — **절대 금지**
- 중간 완료 확인 요청 ("이 부분 맞나요?")
- 각 단계 후 빈 대기 상태

**시각 검증 방식 — JS 측정 우선:**
```
# 스크린샷 대신 이것을 사용
puppeteer_evaluate("website/assets/js/visual-validate.js 내용")
→ { verdict: "✅ PASS", fail: 0 } → 다음 단계
→ { verdict: "❌ FAIL", fail: 2 } → 자가 수정 → 재측정 → 반복
```

**스크린샷 허용 조건 (1회만):**
- 모든 TODO 완료 후 최종 완성 확인용 1장
- 사용자가 명시적으로 "보여줘" 요청 시

**수치 판단 기준 (visual-validate.js 기준):**
- gap 값 fail → CSS 수정 → 재측정
- opacity:0 잔여 → data-reveal 강제 해제
- 3회 재측정 후에도 fail → 원인 분석 후 접근법 전환

**TODO 항목을 체크하며 진행 → deepwork.md 자동 업데이트됨**

**완료 조건:**
- 모든 TODO ✅ + 빌드 + 커밋 + push
- 그 후 딥워크 종료 보고 (한 번만)

**블로커 발생 시:**
- 해결 불가능한 외부 의존성(API 키, 존재하지 않는 파일 등)만 사용자에게 질문
- CSS/레이아웃/텍스트 문제는 스스로 해결

### 3. 딥워크 종료
모든 TODO 완료 후 deepwork.md를 닫음:

```
status: idle
task: [완료된 작업명] ✓
```

그리고 완료 요약 1-2줄로 보고.

## 실제 사용 예시

```
/deepwork Practice 콘텐츠 담백화
```
→ 현재 플랜 파일(`/Users/97layer/.claude/plans/*.md`)이 있으면 자동으로 TODO 추출
→ 없으면 사용자에게 작업 목록 요청 (1회만)
→ 이후 전체 완료까지 개입 없이 실행

## 컨텍스트 압축 후 재개

세션 시작 시 `deepwork.md status: active` 감지되면:
1. ## TODO 에서 미완료 항목(`- [ ]`) 확인
2. ## Modified 에서 이미 수정된 파일 확인
3. 중단 지점부터 자동 재개
4. 추가 질문 없음
