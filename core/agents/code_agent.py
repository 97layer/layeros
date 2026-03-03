#!/usr/bin/env python3
"""
code_agent.py — 텔레그램 지시 → VM 코드 수정 자동화

흐름:
  1. 태스크 수신 (텔레그램 → queue)
  2. 관련 파일 특정 (Grep/Glob)
  3. Flash → Claude 에스컬레이션으로 변경 생성
  4. ProposeGate diff 전송 → 순호 ok/no 대기
  5. 승인 시 파일 적용. Production 재시작은 별도 PROPOSE.

비용 제어:
  - Flash 2회 재시도 후 Claude 에스컬레이션
  - 일일 $3 캡 (CODE_AGENT_DAILY_CAP 환경변수)
  - 전체 호출 하드캡: 5회/태스크
"""
import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
# sys.path에 프로젝트 루트 추가 (systemd 직접 실행 환경 대응)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

PRIMARY_MODEL = "gemini-2.5-flash"
FALLBACK_MODEL = "claude-sonnet-4-6"
MAX_FLASH_RETRIES = 2
MAX_API_CALLS_TOTAL = 5
DAILY_COST_CAP_USD = float(os.getenv("CODE_AGENT_DAILY_CAP", "3"))

# Dual-model 설정
DUEL_ENABLED = os.getenv("CODE_AGENT_DUEL", "1") == "1"  # 기본 활성화
COST_LOG_PATH = PROJECT_ROOT / "knowledge" / "system" / "code_agent_cost.json"

# 변경 불가 경로 (FROZEN)
FROZEN_PATHS = {
    "directives/the_origin.md",
    "knowledge/agent_hub/state.md",
}

CRITIC_PROMPT = """You are a senior code reviewer for the LAYER OS / WOOHWAHAE project.

Your job: find problems in a proposed code change, then suggest improvements.

Return ONLY a JSON object:
{
  "score": 0-100,
  "issues": ["issue 1", "issue 2", ...],
  "suggestions": ["specific fix 1", "specific fix 2", ...],
  "verdict": "APPROVE" | "REVISE"
}

Rules:
- score >= 85 → APPROVE (good enough, no revision needed)
- score < 85 → REVISE (list concrete fixes)
- Be specific: point to exact lines or patterns, not vague criticism
- Focus on: correctness, edge cases, security, LAYER OS conventions (lazy logging, no hardcoded secrets)
- Do NOT rewrite the code — only critique it
"""

SYSTEM_PROMPT = """You are a surgical code editor for the LAYER OS / WOOHWAHAE project.

Rules:
- Return ONLY a JSON object. No prose, no explanation.
- JSON format:
  {
    "files": [
      {
        "path": "relative/path/from/project/root",
        "old_content": "exact original lines to replace (empty string if new file)",
        "new_content": "replacement lines"
      }
    ],
    "summary": "one-line Korean summary of what changed"
  }
- Make minimal, targeted changes. Do not refactor unrelated code.
- Never modify files in: directives/the_origin.md, knowledge/agent_hub/state.md
- Use lazy logging format in Python: logger.info("msg: %s", var) not f-strings
- Never hardcode secrets or API keys
"""


# ─── 비용 추적 ───────────────────────────────────────────────────────────────

def _load_cost_log() -> dict:
    if COST_LOG_PATH.exists():
        try:
            return json.loads(COST_LOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"daily": {}, "total_usd": 0.0}


def _save_cost_log(data: dict) -> None:
    COST_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    COST_LOG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_today_cost() -> float:
    log = _load_cost_log()
    today = datetime.now().strftime("%Y-%m-%d")
    return log["daily"].get(today, 0.0)


def _add_cost(usd: float) -> None:
    log = _load_cost_log()
    today = datetime.now().strftime("%Y-%m-%d")
    log["daily"][today] = log["daily"].get(today, 0.0) + usd
    log["total_usd"] = log.get("total_usd", 0.0) + usd
    _save_cost_log(log)


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """대략적 비용 추정 (USD)."""
    rates = {
        "gemini-2.5-flash": (0.0000003, 0.0000025),   # $0.3/$2.5 per 1M
        "claude-sonnet-4-6": (0.000003, 0.000015),     # $3/$15 per 1M
    }
    inp_rate, out_rate = rates.get(model, (0.000003, 0.000015))
    return inp_rate * input_tokens + out_rate * output_tokens


# ─── 파일 검색 ───────────────────────────────────────────────────────────────

def _find_relevant_files(instruction: str, max_files: int = 5) -> list[dict]:
    """
    지시문에서 키워드를 추출해 관련 파일을 Grep/Glob으로 찾는다.
    전체 프로젝트를 blindly 읽지 않음.
    """
    keywords = re.findall(r'\b[\w가-힣]+\b', instruction)
    # 짧은 단어 제거
    keywords = [k for k in keywords if len(k) >= 3][:6]

    found = []
    seen_paths = set()

    # 코드가 있는 디렉토리만 검색 (속도 최적화 — .venv/knowledge/signals 제외)
    SEARCH_DIRS = [
        PROJECT_ROOT / "core",
        PROJECT_ROOT / "website",
        PROJECT_ROOT / "directives",
        PROJECT_ROOT / "scripts",
    ]

    # 1. 지시문에 파일 경로처럼 보이는 것 우선 검색
    path_hints = re.findall(r'[\w/\-]+\.(?:py|html|md|json|sh|js|css)', instruction)
    for hint in path_hints:
        for search_dir in SEARCH_DIRS:
            matches = list(search_dir.rglob(hint))
            for m in matches:
                rel = str(m.relative_to(PROJECT_ROOT))
                if rel not in seen_paths and _is_editable(rel):
                    seen_paths.add(rel)
                    found.append({"path": rel, "content": m.read_text(encoding="utf-8", errors="replace")})

    # 2. 키워드 Grep — 코드 디렉토리만
    for kw in keywords:
        if len(found) >= max_files:
            break
        for search_dir in SEARCH_DIRS:
            if not search_dir.exists() or len(found) >= max_files:
                continue
            try:
                result = subprocess.run(
                    ["grep", "-rl",
                     "--include=*.py", "--include=*.html", "--include=*.md", "--include=*.sh",
                     "--exclude-dir=__pycache__",
                     kw, str(search_dir)],
                    capture_output=True, text=True, timeout=8
                )
                for line in result.stdout.strip().splitlines():
                    path = Path(line)
                    if not path.exists():
                        continue
                    rel = str(path.relative_to(PROJECT_ROOT))
                    if rel in seen_paths or not _is_editable(rel):
                        continue
                    seen_paths.add(rel)
                    found.append({"path": rel, "content": path.read_text(encoding="utf-8", errors="replace")})
                    if len(found) >= max_files:
                        break
            except subprocess.TimeoutExpired:
                logger.warning("grep timeout on keyword: %s in %s", kw, search_dir.name)

    # 파일당 최대 300줄로 자름 (토큰 절약)
    for f in found:
        lines = f["content"].splitlines()
        if len(lines) > 300:
            f["content"] = "\n".join(lines[:300]) + "\n... (truncated)"

    return found[:max_files]


def _is_editable(rel_path: str) -> bool:
    """FROZEN 경로, .env / 시크릿 파일, path traversal 차단."""
    if rel_path in FROZEN_PATHS:
        return False
    blocked = [".env", "credentials", "secrets", "__pycache__", ".git/"]
    if any(b in rel_path for b in blocked):
        return False
    # path traversal 방어: resolve 후 PROJECT_ROOT 내부인지 확인
    try:
        resolved = (PROJECT_ROOT / rel_path).resolve()
        if not str(resolved).startswith(str(PROJECT_ROOT.resolve())):
            return False
    except Exception:
        return False
    return True


# ─── LLM 호출 ────────────────────────────────────────────────────────────────

def _call_gemini(prompt: str) -> Optional[dict]:
    """Gemini Flash로 변경 생성. 실패 시 None."""
    try:
        from google import genai
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        resp = client.models.generate_content(
            model=PRIMARY_MODEL,
            contents=prompt,
        )
        raw = resp.text.strip()
        # JSON 블록 추출
        m = re.search(r'```json\s*([\s\S]+?)\s*```', raw)
        if m:
            raw = m.group(1)
        return json.loads(raw)
    except Exception as e:
        logger.warning("Gemini 호출 실패: %s", e)
        return None


def _call_claude(prompt: str, system: str = SYSTEM_PROMPT) -> Optional[dict]:
    """Claude Sonnet 호출 (Proposer 또는 Critic). 실패 시 None."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        msg = client.messages.create(
            model=FALLBACK_MODEL,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        m = re.search(r'```json\s*([\s\S]+?)\s*```', raw)
        if m:
            raw = m.group(1)
        result = json.loads(raw)
        inp = msg.usage.input_tokens
        out = msg.usage.output_tokens
        cost = _estimate_cost(FALLBACK_MODEL, inp, out)
        _add_cost(cost)
        logger.info("Claude 호출 완료: in=%s out=%s cost=$%.4f", inp, out, cost)
        return result
    except Exception as e:
        logger.error("Claude 호출 실패: %s", e)
        return None


def _critique_with_claude(draft: dict, instruction: str) -> Optional[dict]:
    """Claude가 Gemini 초안을 비판. score/issues/suggestions/verdict 반환."""
    draft_text = json.dumps(draft, ensure_ascii=False, indent=2)
    prompt = (
        f"지시: {instruction}\n\n"
        f"Gemini가 생성한 코드 변경안:\n```json\n{draft_text}\n```\n\n"
        f"이 변경안을 검토하고 JSON으로만 응답:"
    )
    return _call_claude(prompt, system=CRITIC_PROMPT)


def _generate_changes(instruction: str, context_files: list[dict]) -> Optional[dict]:
    """
    Dual-model 생성:
      Round 1) Gemini Flash → 초안
      Round 2) Claude Critic → score/issues/suggestions
               score >= 85 → APPROVE (초안 채택)
               score < 85  → Gemini Flash → 피드백 반영 최종안
      Fallback) Gemini 연속 실패 시 Claude Proposer 에스컬레이션
    """
    today_cost = _get_today_cost()
    if today_cost >= DAILY_COST_CAP_USD:
        logger.error("일일 비용 캡 초과: $%.2f / $%.2f", today_cost, DAILY_COST_CAP_USD)
        return None

    context_text = ""
    for f in context_files:
        context_text += f"\n\n### {f['path']}\n```\n{f['content']}\n```"

    base_prompt = (
        f"지시: {instruction}\n\n"
        f"관련 파일:{context_text}\n\n"
        f"JSON만 반환:"
    )

    # ── Round 1: Gemini 초안 생성 ──────────────────────────────────────
    draft = None
    for attempt in range(MAX_FLASH_RETRIES):
        draft = _call_gemini(base_prompt)
        if draft and "files" in draft:
            cost = _estimate_cost(PRIMARY_MODEL, len(base_prompt) // 4, 500)
            _add_cost(cost)
            logger.info("Gemini 초안 생성 (attempt %s)", attempt + 1)
            break
        logger.warning("Gemini attempt %s 실패", attempt + 1)

    if not draft or not draft.get("files"):
        logger.info("Gemini 실패 → Claude Proposer 에스컬레이션")
        return _call_claude(base_prompt)

    if not DUEL_ENABLED:
        return draft

    # ── Round 2: Claude Critic ──────────────────────────────────────────
    critique = _critique_with_claude(draft, instruction)
    if not critique:
        logger.warning("Critic 호출 실패 → Gemini 초안 채택")
        return draft

    score = critique.get("score", 0)
    verdict = critique.get("verdict", "REVISE")
    issues = critique.get("issues", [])
    suggestions = critique.get("suggestions", [])
    logger.info("Critic 결과: score=%s verdict=%s issues=%s", score, verdict, len(issues))

    if verdict == "APPROVE" or score >= 85:
        logger.info("Critic APPROVE → 초안 채택")
        draft["_critic"] = {"score": score, "verdict": "APPROVE"}
        return draft

    # ── Round 3: Gemini 재생성 (Critic 피드백 반영, context 제외로 토큰 절감) ───
    feedback_block = "\n".join(f"- {s}" for s in suggestions) or "\n".join(f"- {i}" for i in issues)
    draft_text = json.dumps(draft, ensure_ascii=False, indent=2)
    revised_prompt = (
        f"지시: {instruction}\n\n"
        f"이전 코드 (수정 대상):\n```json\n{draft_text}\n```\n\n"
        f"검토 결과 (score={score}/100) — 반드시 반영:\n{feedback_block}\n\n"
        f"위 피드백을 모두 반영한 개선된 JSON만 반환:"
    )
    revised = _call_gemini(revised_prompt)
    if revised and revised.get("files"):
        cost = _estimate_cost(PRIMARY_MODEL, len(revised_prompt) // 4, 500)
        _add_cost(cost)
        revised["_critic"] = {"score": score, "verdict": "REVISED", "issues": issues}
        logger.info("Gemini 수정안 생성 완료 (critic score=%s)", score)
        return revised

    # Round 3 Gemini 실패 → Claude가 직접 Critic 피드백 반영
    logger.info("Gemini Round 3 실패 → Claude Reviser 에스컬레이션")
    claude_revised_prompt = (
        f"지시: {instruction}\n\n"
        f"현재 코드:\n```json\n{draft_text}\n```\n\n"
        f"코드 리뷰 결과 (score={score}/100) — 아래 모든 항목을 반드시 반영:\n{feedback_block}\n\n"
        f"피드백을 모두 반영한 개선된 JSON만 반환:"
    )
    claude_revised = _call_claude(claude_revised_prompt)
    if claude_revised and claude_revised.get("files"):
        claude_revised["_critic"] = {"score": score, "verdict": "CLAUDE_REVISED", "issues": issues}
        logger.info("Claude 수정안 생성 완료 (critic score=%s)", score)
        return claude_revised

    logger.warning("모든 재생성 실패 → 초안 채택")
    return draft


# ─── 파일 적용 ───────────────────────────────────────────────────────────────

def _apply_changes(changes: dict) -> tuple[bool, str]:
    """
    변경을 실제 파일에 적용.
    Returns: (success, error_message)
    """
    for file_change in changes.get("files", []):
        rel_path = file_change.get("path", "")
        old_content = file_change.get("old_content", "")
        new_content = file_change.get("new_content", "")

        if not _is_editable(rel_path):
            return False, f"편집 불가 경로: {rel_path}"

        target = PROJECT_ROOT / rel_path

        if old_content == "":
            # 신규 파일
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(new_content, encoding="utf-8")
            logger.info("신규 파일 생성: %s", rel_path)
        else:
            if not target.exists():
                return False, f"파일 없음: {rel_path}"
            current = target.read_text(encoding="utf-8")
            if old_content not in current:
                preview = "\n".join(current.splitlines()[:10])
                return False, f"old_content 미매칭: {rel_path}\n파일 앞 10줄:\n{preview}"
            updated = current.replace(old_content, new_content, 1)
            target.write_text(updated, encoding="utf-8")
            logger.info("파일 수정: %s", rel_path)

    return True, ""


def _build_diff_text(changes: dict) -> str:
    """변경 내용을 텔레그램용 diff 텍스트로 변환."""
    critic = changes.get("_critic", {})
    if critic:
        score = critic.get("score", "—")
        verdict = critic.get("verdict", "—")
        critic_line = f"🤖 Critic: score={score}/100 · {verdict}"
        if critic.get("issues"):
            critic_line += f" · {len(critic['issues'])}건 지적"
        lines = [critic_line, f"변경 요약: {changes.get('summary', '—')}"]
    else:
        lines = [f"변경 요약: {changes.get('summary', '—')}"]
    for f in changes.get("files", []):
        lines.append(f"\n📄 {f['path']}")
        old = f.get("old_content", "")
        new = f.get("new_content", "")
        if old:
            for l in old.splitlines()[:10]:
                lines.append(f"- {l}")
        for l in new.splitlines()[:10]:
            lines.append(f"+ {l}")
        if len(old.splitlines()) > 10 or len(new.splitlines()) > 10:
            lines.append("... (truncated)")
    return "\n".join(lines)


# ─── 메인 에이전트 ────────────────────────────────────────────────────────────

class CodeAgent:
    """
    텔레그램 코드 수정 에이전트.

    사용 방법 (telegram_secretary에서):
        agent = CodeAgent()
        result = await agent.handle_task(instruction, chat_id, send_fn)
    """

    def __init__(self):
        from core.system.propose_gate import ProposeGate
        self.gate = ProposeGate()

    async def handle_task(
        self,
        instruction: str,
        chat_id: int,
        send_fn,  # async fn(text: str) → Message
    ) -> None:
        """
        지시 처리 → diff PROPOSE → ok 시 파일 적용.
        Production 재시작은 절대 자동 금지. 별도 PROPOSE.
        """
        task_id = f"code_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        logger.info("CodeAgent 태스크 시작: %s | %s", task_id, instruction[:80])

        # 비용 캡 사전 확인
        today_cost = _get_today_cost()
        if today_cost >= DAILY_COST_CAP_USD:
            await send_fn(
                f"[Code Agent] 일일 비용 캡 초과 (${today_cost:.2f}/${ DAILY_COST_CAP_USD}). "
                "내일 다시 시도하세요."
            )
            return

        # 1. 관련 파일 검색
        status_msg = await send_fn("🔍 관련 파일 검색 중...")
        context_files = _find_relevant_files(instruction)

        if not context_files:
            await status_msg.edit_text("⚠️ 관련 파일을 찾지 못했습니다. 지시를 더 구체적으로 작성해주세요.")
            return

        file_list = ", ".join(f["path"] for f in context_files)
        await status_msg.edit_text(f"🔍 파일 특정: {file_list}\n\n⚙️ 변경 생성 중...")

        # 2. 변경 생성 (Flash → Claude)
        changes = _generate_changes(instruction, context_files)

        if not changes or not changes.get("files"):
            await status_msg.edit_text("❌ 변경 생성 실패. 지시를 재확인하거나 다시 시도하세요.")
            return

        # 3. PROPOSE diff 전송
        diff_text = _build_diff_text(changes)
        propose_result = self.gate.propose(task_id, diff_text, chat_id, {"changes": changes})
        msg = await send_fn(propose_result["message"])

        # 메시지 ID 등록 (reply 기반 confirm용)
        if hasattr(msg, "message_id"):
            self.gate.register_message_id(task_id, msg.message_id)

        await status_msg.delete()
        logger.info("PROPOSE 전송 완료: %s", task_id)

    async def apply_confirmed(
        self,
        task_id: str,
        send_fn,
    ) -> None:
        """
        순호가 ok → 파일 적용 실행.
        서비스 재시작이 필요하면 별도 PROPOSE.
        """
        task = self.gate.get_task(task_id)
        if not task:
            logger.error("태스크 없음: %s", task_id)
            return

        changes = task.get("callback_data", {}).get("changes", {})
        success, err = _apply_changes(changes)

        if success:
            file_list = ", ".join(f["path"] for f in changes.get("files", []))
            # git commit 자동화
            git_status = ""
            try:
                changed_files = [f["path"] for f in changes.get("files", [])]
                subprocess.run(
                    ["git", "add"] + changed_files,
                    cwd=PROJECT_ROOT, check=True, timeout=15
                )
                summary = changes.get("summary", "코드 수정")
                subprocess.run(
                    ["git", "commit", "-m", f"fix: {summary}"],
                    cwd=PROJECT_ROOT, check=True, timeout=15
                )
                git_status = "✅ git commit 완료"
                logger.info("git commit 완료: %s", task_id)
            except subprocess.CalledProcessError as git_e:
                git_status = "⚠️ git commit 실패 (파일 적용은 완료)"
                logger.warning("git commit 실패: %s", git_e)
            except Exception as git_e:
                git_status = "⚠️ git commit 실패 (파일 적용은 완료)"
                logger.warning("git commit 실패: %s", git_e)

            await send_fn(
                f"✅ 적용 완료\n\n"
                f"파일: {file_list}\n"
                f"요약: {changes.get('summary', '—')}\n"
                f"{git_status}\n\n"
                f"서비스 재시작이 필요하면 '재시작: [서비스명]' 으로 요청해주세요."
            )
            logger.info("변경 적용 완료: %s", task_id)
        else:
            await send_fn(f"❌ 적용 실패: {err}")
            logger.error("변경 적용 실패: %s | %s", task_id, err)

    async def handle_restart_request(
        self,
        service_name: str,
        chat_id: int,
        send_fn,
    ) -> None:
        """
        서비스 재시작 PROPOSE. 자동 실행 금지.
        ok 응답 후 별도 confirm_restart 호출 필요.
        """
        task_id = f"restart_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        diff_text = f"systemctl restart {service_name} 실행 예정"
        propose_result = self.gate.propose(
            task_id, diff_text, chat_id,
            {"type": "restart", "service": service_name}
        )
        msg = await send_fn(propose_result["message"])
        if hasattr(msg, "message_id"):
            self.gate.register_message_id(task_id, msg.message_id)

    async def confirm_restart(self, task_id: str, send_fn) -> None:
        """재시작 PROPOSE 승인 처리."""
        task = self.gate.get_task(task_id)
        if not task:
            return
        service = task.get("callback_data", {}).get("service", "")
        if not service:
            await send_fn("❌ 서비스명 없음")
            return
        try:
            subprocess.run(
                ["sudo", "systemctl", "restart", service],
                check=True, timeout=30
            )
            await send_fn(f"✅ {service} 재시작 완료")
        except Exception as e:
            await send_fn(f"❌ 재시작 실패: {e}")


# ─── 스케줄러 모드 (systemd ExecStart용) ────────────────────────────────────

async def _scheduler_loop():
    """큐에서 code_task를 polling해 처리. VM에서 systemd로 실행."""
    logger.info("Code Agent scheduler 시작")
    try:
        from core.system.queue_manager import QueueManager
        qm = QueueManager()
    except Exception as e:
        logger.error("QueueManager 초기화 실패: %s", e)
        return

    from core.system.propose_gate import ProposeGate
    gate = ProposeGate()

    while True:
        try:
            # 만료 태스크 정리
            expired = gate.expire_old()
            if expired:
                logger.info("만료된 PROPOSE: %s개", len(expired))

            # 비용 캡 확인
            if _get_today_cost() >= DAILY_COST_CAP_USD:
                logger.warning("일일 비용 캡 초과. 60초 대기.")
                await asyncio.sleep(60)
                continue

            # 큐에서 code_task 가져오기 (현재는 텔레그램 봇이 직접 호출하므로 poll 불필요)
            # 향후 독립 실행 필요 시 여기서 qm.claim_task('CodeAgent') 추가

        except Exception as e:
            logger.error("scheduler_loop 오류: %s", e)

        await asyncio.sleep(30)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    if "--schedule" in sys.argv:
        asyncio.run(_scheduler_loop())
    else:
        print("Usage: python3 code_agent.py --schedule")
