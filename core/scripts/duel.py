#!/usr/bin/env python3
"""
duel.py — Claude vs Gemini 코드 생성 대결 (실시간 critic 검증용)

사용법:
  python3 core/scripts/duel.py "텔레그램 note 커맨드 재시도 로직 추가"
  python3 core/scripts/duel.py --rounds 3 "SA 에이전트 캐싱 개선"
  python3 core/scripts/duel.py --apply "CE 프롬프트 개선"  # 최종 코드 파일 적용
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.WARNING, format="%(message)s")
logger = logging.getLogger(__name__)

# .env 로드 (로컬 실행 시 API 키 주입)
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

# code_agent 함수 재사용
from core.agents.code_agent import (
    _call_claude,
    _call_gemini,
    _critique_with_claude,
    _find_relevant_files,
    _apply_changes,
    SYSTEM_PROMPT,
)

CYAN  = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED   = "\033[91m"
BOLD  = "\033[1m"
DIM   = "\033[2m"
RESET = "\033[0m"


def _banner(text: str, color: str = CYAN) -> None:
    print(f"\n{color}{BOLD}{'─' * 60}{RESET}")
    print(f"{color}{BOLD}  {text}{RESET}")
    print(f"{color}{BOLD}{'─' * 60}{RESET}")


def _print_changes(changes: dict, label: str, color: str) -> None:
    print(f"\n{color}{BOLD}[{label}]{RESET}")
    print(f"  요약: {changes.get('summary', '—')}")
    for f in changes.get("files", []):
        print(f"  📄 {f['path']}")
        new_lines = f.get("new_content", "").splitlines()[:12]
        for line in new_lines:
            print(f"  {DIM}  {line}{RESET}")
        if len(f.get("new_content", "").splitlines()) > 12:
            print(f"  {DIM}  ... (생략){RESET}")


def _print_critique(critique: dict) -> None:
    score = critique.get("score", 0)
    verdict = critique.get("verdict", "—")
    color = GREEN if score >= 85 else (YELLOW if score >= 60 else RED)
    print(f"\n{color}{BOLD}[Claude Critic]{RESET}")
    print(f"  score: {color}{BOLD}{score}/100{RESET}  verdict: {color}{verdict}{RESET}")
    issues = critique.get("issues", [])
    suggestions = critique.get("suggestions", [])
    if issues:
        print(f"  Issues ({len(issues)}):")
        for i in issues:
            print(f"    {RED}✗ {i}{RESET}")
    if suggestions:
        print(f"  Suggestions:")
        for s in suggestions:
            print(f"    {YELLOW}→ {s}{RESET}")


def duel(instruction: str, max_rounds: int = 2, apply: bool = False) -> dict | None:
    _banner(f"DUEL: {instruction[:70]}")

    # 1. 관련 파일 검색
    print(f"\n{DIM}🔍 관련 파일 검색 중...{RESET}")
    context_files = _find_relevant_files(instruction)
    if context_files:
        print(f"  파일: {', '.join(f['path'] for f in context_files)}")
    else:
        print(f"  {YELLOW}관련 파일 없음 — 일반 지시로 진행{RESET}")

    context_text = ""
    for f in context_files:
        # duel용: 파일당 60줄로 제한 (프롬프트 과부하 방지)
        lines = f["content"].splitlines()
        snippet = "\n".join(lines[:60])
        if len(lines) > 60:
            snippet += "\n... (truncated)"
        context_text += f"\n\n### {f['path']}\n```\n{snippet}\n```"

    base_prompt = (
        f"지시: {instruction}\n\n"
        f"관련 파일:{context_text}\n\n"
        f"JSON만 반환:"
    )

    best = None

    for round_num in range(1, max_rounds + 1):
        _banner(f"Round {round_num} — Gemini Proposer", CYAN)

        # Gemini 생성
        print(f"{DIM}  생성 중...{RESET}", end="", flush=True)
        if round_num == 1:
            prompt = base_prompt
        else:
            # 이전 Critic 피드백 반영
            feedback = "\n".join(f"- {s}" for s in last_suggestions)
            prompt = (
                f"지시: {instruction}\n\n"
                f"관련 파일:{context_text}\n\n"
                f"이전 코드 검토 피드백 (반드시 반영):\n{feedback}\n\n"
                f"개선된 JSON만 반환:"
            )

        draft = _call_gemini(prompt)
        print(f"\r{' ' * 20}\r", end="")

        if not draft or not draft.get("files"):
            print(f"  {RED}Gemini 생성 실패{RESET}")
            if round_num == 1:
                # Round 1 실패 → Claude Proposer로 초안 생성
                _banner("Claude Proposer (Fallback)", YELLOW)
                print(f"{DIM}  생성 중...{RESET}", end="", flush=True)
                draft = _call_claude(base_prompt)
                print(f"\r{' ' * 20}\r", end="")
                if not draft:
                    print(f"  {RED}Claude도 실패. 종료.{RESET}")
                    return None
            else:
                # Round 2+ 실패 → Claude Reviser로 즉시 피드백 반영
                _banner("Claude Reviser (Gemini 실패 → 즉시 피드백 반영)", YELLOW)
                print(f"{DIM}  피드백 반영 중...{RESET}", end="", flush=True)
                draft_text = json.dumps(best, ensure_ascii=False, indent=2)
                feedback = "\n".join(f"- {s}" for s in last_suggestions)
                claude_prompt = (
                    f"지시: {instruction}\n\n"
                    f"현재 코드:\n```json\n{draft_text}\n```\n\n"
                    f"검토 결과 (score={score}/100) — 아래를 모두 반영:\n{feedback}\n\n"
                    f"피드백 반영 개선된 JSON만 반환:"
                )
                claude_rev = _call_claude(claude_prompt)
                print(f"\r{' ' * 30}\r", end="")
                if claude_rev and claude_rev.get("files"):
                    _print_changes(claude_rev, "Claude Revised", GREEN)
                    claude_rev["_critic"] = {"score": score, "verdict": "CLAUDE_REVISED"}
                    best = claude_rev
                else:
                    print(f"  {YELLOW}Claude Reviser도 실패 → 초안 채택{RESET}")
                break

        _print_changes(draft, f"Gemini Round {round_num}", CYAN)
        best = draft

        # Claude Critic
        _banner(f"Round {round_num} — Claude Critic", YELLOW)
        print(f"{DIM}  검토 중...{RESET}", end="", flush=True)
        critique = _critique_with_claude(draft, instruction)
        print(f"\r{' ' * 20}\r", end="")

        if not critique:
            print(f"  {YELLOW}Critic 호출 실패 → 현재 안 채택{RESET}")
            break

        _print_critique(critique)
        last_suggestions = critique.get("suggestions", []) or critique.get("issues", [])
        score = critique.get("score", 0)
        verdict = critique.get("verdict", "REVISE")

        if verdict == "APPROVE" or score >= 85:
            print(f"\n{GREEN}{BOLD}  ✓ APPROVED — Round {round_num} 채택{RESET}")
            best = draft
            best["_critic"] = critique
            break

        if round_num == max_rounds:
            # Gemini 재생성 실패 → Claude가 Critic 피드백 직접 반영
            _banner(f"Round {round_num} — Claude Reviser (Gemini 실패 fallback)", YELLOW)
            print(f"{DIM}  피드백 반영 중...{RESET}", end="", flush=True)
            draft_text = json.dumps(best, ensure_ascii=False, indent=2)
            feedback = "\n".join(f"- {s}" for s in last_suggestions)
            claude_prompt = (
                f"지시: {instruction}\n\n"
                f"현재 코드:\n```json\n{draft_text}\n```\n\n"
                f"검토 결과 (score={score}/100) — 아래를 모두 반영:\n{feedback}\n\n"
                f"피드백 반영 개선된 JSON만 반환:"
            )
            claude_rev = _call_claude(claude_prompt)
            print(f"\r{' ' * 30}\r", end="")
            if claude_rev and claude_rev.get("files"):
                _print_changes(claude_rev, "Claude Revised", GREEN)
                claude_rev["_critic"] = {"score": score, "verdict": "CLAUDE_REVISED"}
                best = claude_rev
            else:
                print(f"  {YELLOW}Claude Reviser도 실패 → 초안 채택{RESET}")
                best["_critic"] = critique

    # 최종 결과
    _banner("최종 코드", GREEN)
    if best:
        _print_changes(best, "FINAL", GREEN)
        critic_info = best.get("_critic", {})
        if critic_info:
            score = critic_info.get("score", "—")
            verdict = critic_info.get("verdict", "—")
            print(f"\n  Critic 최종 평가: score={score}/100 · {verdict}")

        if apply:
            print(f"\n{YELLOW}파일 적용 중...{RESET}")
            success, err = _apply_changes(best)
            if success:
                print(f"{GREEN}✓ 파일 적용 완료{RESET}")
            else:
                print(f"{RED}✗ 적용 실패: {err}{RESET}")
        else:
            print(f"\n{DIM}  --apply 플래그로 실제 파일에 적용 가능{RESET}")

    return best


def _pick_auto_task() -> str | None:
    """
    자율 태스크 선정:
    1. knowledge/system/propose_queue.json — 대기 중인 PROPOSE 태스크
    2. knowledge/system/decision_log.jsonl — 최근 미해결 이슈
    3. core/ Python 파일 중 TODO/FIXME 주석
    """
    # 1. propose_queue
    queue_path = PROJECT_ROOT / "knowledge" / "system" / "propose_queue.json"
    if queue_path.exists():
        try:
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            pending = [t for t in queue.get("tasks", []) if t.get("status") == "pending"]
            if pending:
                task = pending[0]
                desc = task.get("description") or task.get("diff_text", "")
                if desc:
                    return f"[propose_queue] {desc[:200]}"
        except Exception:
            pass

    # 2. decision_log — 최근 unresolved
    log_path = PROJECT_ROOT / "knowledge" / "system" / "decision_log.jsonl"
    if log_path.exists():
        try:
            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            for line in reversed(lines[-20:]):
                entry = json.loads(line)
                if entry.get("status") == "unresolved" and entry.get("description"):
                    return f"[decision_log] {entry['description'][:200]}"
        except Exception:
            pass

    # 3. TODO/FIXME 주석 (# TODO: 또는 # FIXME: 형태만)
    import subprocess
    result = subprocess.run(
        ["grep", "-rn", "-E", r"#\s*(TODO|FIXME):",
         "--include=*.py", "--exclude-dir=__pycache__",
         str(PROJECT_ROOT / "core")],
        capture_output=True, text=True, timeout=10
    )
    lines = [l for l in result.stdout.strip().splitlines() if l.strip()]
    if lines:
        line = lines[0]
        # "path:lineno:  # TODO: 설명"
        parts = line.split(":", 2)
        if len(parts) >= 3:
            rel = str(Path(parts[0]).relative_to(PROJECT_ROOT))
            comment = parts[2].strip().lstrip("#").strip()
            return f"{rel}: {comment}"

    return None


def auto_loop(rounds: int = 2, apply: bool = False) -> None:
    """지시 없이 스스로 태스크 선정 → duel 실행."""
    _banner("AUTO DUEL — 자율 태스크 선정", YELLOW)
    task = _pick_auto_task()
    if not task:
        print(f"{YELLOW}자율 태스크 없음. propose_queue / decision_log / TODO 모두 비어있음.{RESET}")
        return
    print(f"\n선정된 태스크:\n  {BOLD}{task}{RESET}\n")
    duel(task, max_rounds=rounds, apply=apply)


def main() -> None:
    parser = argparse.ArgumentParser(description="Claude vs Gemini 코드 대결")
    parser.add_argument("instruction", nargs="?", help="구현 지시문")
    parser.add_argument("--rounds", type=int, default=2, help="최대 라운드 수 (기본 2)")
    parser.add_argument("--apply", action="store_true", help="최종 코드를 파일에 적용")
    parser.add_argument("--auto", action="store_true", help="자율 태스크 선정 후 실행")
    args = parser.parse_args()

    if args.auto:
        auto_loop(rounds=args.rounds, apply=args.apply)
        return

    if not args.instruction:
        instruction = input(f"{BOLD}지시: {RESET}").strip()
        if not instruction:
            print("지시 없음. 종료.")
            sys.exit(1)
    else:
        instruction = args.instruction

    result = duel(instruction, max_rounds=args.rounds, apply=args.apply)
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
