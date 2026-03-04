# LAYER OS — WOOHWAHAE

> 슬로우라이프를 기록하고 실천하는 브랜드 운영 체제.

---

## 구조

```
directives/          뇌 — SAGE_ARCHITECT(인격) + SYSTEM(운영) + THE_ORIGIN(철학)
knowledge/           기억 — 신호, 상태, 리포트
core/                엔진 — 에이전트, 파이프라인, 스킬
website/             얼굴 — woohwahae.kr (Cloudflare Pages)
```

## 문서

| 파일 | 역할 |
|------|------|
| [sage_architect.md](directives/sage_architect.md) | 인격 SSOT. 모든 에이전트의 뿌리 |
| [the_origin.md](directives/the_origin.md) | 브랜드 철학 경전 |
| [system.md](directives/system.md) | 운영 매뉴얼. 아키텍처 + 배치 + 거버넌스 |

## 실행

```bash
# 리빌드 전 필수 게이트 (lock + 시각검증 + 빌드 + localhost:9700 스모크)
bash core/scripts/run_web_rebuild_prep.sh --agent HUMAN --task "ui-ux rebuild"

# 빌드
python3 core/scripts/build.py

# 배포 (Cloudflare Pages)
git push origin main
```

## 하네스 풀스택 (로컬 협업)

```bash
# SA/AD/CE/CD + Orchestrator + Scout
bash core/scripts/start_harness_fullstack.sh

# Gardener/Monitor까지 포함
bash core/scripts/start_harness_fullstack.sh --with-gardener --with-monitor
```

---

> "소음이 걷힌 진공에 다다라서야 명징한 본질이 나선다." — THE ORIGIN
