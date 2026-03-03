#!/usr/bin/env python3
"""
Gemini Critic hook
  기본: --staged  → git commit 직전 staged .py 파일 일괄 리뷰
  단일: --file <path> → 특정 파일 리뷰 (레거시)
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def load_env(project_root: Path) -> None:
    env_file = project_root / ".env"
    if not env_file.exists():
        return
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass


def get_staged_py_files(project_root: Path) -> list[tuple[str, str]]:
    """staged .py 파일 목록 + 내용 반환."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=str(project_root), capture_output=True, text=True, timeout=10
        )
        files = []
        for rel in result.stdout.strip().splitlines():
            if not rel.endswith(".py"):
                continue
            path = project_root / rel
            if path.exists():
                all_lines = path.read_text(encoding="utf-8").splitlines()
                content = "\n".join(all_lines[:120])
                if len(all_lines) > 120:
                    content += "\n... (truncated)"
                files.append((rel, content))
        return files
    except Exception:
        return []


def review_files(files: list[tuple[str, str]], api_key: str) -> None:
    if not files:
        return

    from google import genai
    client = genai.Client(api_key=api_key)

    # 여러 파일을 하나의 요청으로 묶어서 비용 절감
    files_block = ""
    for rel, content in files:
        files_block += f"\n\n### {rel}\n```python\n{content}\n```"

    prompt = (
        "You are a code reviewer for the LAYER OS project (Python). "
        "Review the following staged files and respond in Korean with EXACTLY this format:\n\n"
        "overall_score: [0-100]\n"
        "verdict: [APPROVE|REVISE]\n"
        "files:\n"
        "  - path: [파일경로]\n"
        "    score: [0-100]\n"
        "    issues: [이슈 또는 없음]\n"
        "(위 files 블록을 각 파일마다 반복)\n\n"
        "Focus on: correctness, lazy logging (no f-strings in logger calls), "
        "no hardcoded secrets, edge cases.\n"
        f"Staged files:{files_block}"
    )

    try:
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        review = resp.text.strip()
    except Exception as e:
        print(f"\n\033[2mGemini Critic 스킵: {e}\033[0m")
        return

    # 전체 점수 파싱
    score_m = re.search(r"overall_score:\s*(\d+)", review)
    verdict_m = re.search(r"verdict:\s*(\S+)", review)
    score = int(score_m.group(1)) if score_m else None
    verdict = verdict_m.group(1) if verdict_m else "?"

    if score is None:
        return

    color = "\033[92m" if score >= 85 else ("\033[93m" if score >= 65 else "\033[91m")
    reset = "\033[0m"
    bold = "\033[1m"
    dim = "\033[2m"

    print(f"\n{dim}{'━' * 50}{reset}")
    print(f"🤖 {bold}Gemini Critic{reset}  {color}{bold}{score}/100{reset}  {color}{verdict}{reset}")

    # 파일별 결과 파싱
    file_blocks = re.findall(
        r"-\s*path:\s*(.+?)\n\s*score:\s*(\d+)\n\s*issues:\s*(.+?)(?=\n\s*-\s*path:|\Z)",
        review, re.DOTALL
    )
    for fpath, fscore, fissues in file_blocks:
        fpath = fpath.strip()
        fscore = int(fscore.strip())
        fissues = fissues.strip().replace("\n", " ")
        fc = "\033[92m" if fscore >= 85 else ("\033[93m" if fscore >= 65 else "\033[91m")
        print(f"  {dim}{fpath}{reset}  {fc}{fscore}/100{reset}")
        if fissues and fissues not in ("없음", "none", "None", "-"):
            # 최대 1줄로
            short = fissues[:120] + ("..." if len(fissues) > 120 else "")
            print(f"    {dim}↳ {short}{reset}")

    print(f"{dim}{'━' * 50}{reset}\n")


def main() -> None:
    args = sys.argv[1:]
    project_root = Path(args[0]) if args else Path.cwd()
    mode = args[1] if len(args) > 1 else "--staged"

    load_env(project_root)
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit(0)

    if mode == "--staged":
        files = get_staged_py_files(project_root)
        review_files(files, api_key)
    elif mode == "--file" and len(args) > 2:
        file_path = Path(args[2])
        if file_path.exists() and str(file_path).endswith(".py"):
            lines = file_path.read_text(encoding="utf-8").splitlines()[:150]
            content = "\n".join(lines)
            rel = str(file_path).replace(str(project_root) + "/", "")
            review_files([(rel, content)], api_key)


if __name__ == "__main__":
    main()
