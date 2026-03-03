#!/usr/bin/env python3
"""PostToolUse hook: .py 파일 편집 시 Gemini 자동 리뷰"""
import json
import os
import sys
from pathlib import Path

def main():
    project_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()

    # dotenv 로드
    env_file = project_root / ".env"
    if env_file.exists():
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())
        except Exception:
            pass

    # stdin JSON 파싱
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path or not file_path.endswith(".py"):
        sys.exit(0)

    if not os.path.exists(file_path):
        sys.exit(0)

    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit(0)

    # 파일 내용 (최대 150줄)
    try:
        lines = Path(file_path).read_text(encoding="utf-8").splitlines()[:150]
        content = "\n".join(lines)
        if len(Path(file_path).read_text(encoding="utf-8").splitlines()) > 150:
            content += "\n... (truncated)"
    except Exception:
        sys.exit(0)

    rel_path = file_path.replace(str(project_root) + "/", "")

    # Gemini 호출
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        prompt = (
            f"You are a code reviewer. Review this Python file and respond in Korean "
            f"with EXACTLY this format (no other text):\n\n"
            f"score: [0-100]\n"
            f"verdict: [APPROVE|REVISE]\n"
            f"issues: [최대 3개 이슈, 또는 없음]\n\n"
            f"File: {rel_path}\n```python\n{content}\n```"
        )
        resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        review = resp.text.strip()
    except Exception as e:
        sys.exit(0)

    # 파싱
    import re
    score_m = re.search(r"score:\s*(\d+)", review)
    verdict_m = re.search(r"verdict:\s*(\S+)", review)
    issues_m = re.search(r"issues:\s*(.+)", review)

    if not score_m:
        sys.exit(0)

    score = int(score_m.group(1))
    verdict = verdict_m.group(1) if verdict_m else "?"
    issues = issues_m.group(1).strip() if issues_m else ""

    # 색상
    if verdict == "APPROVE" or score >= 85:
        color = "\033[92m"   # green
    elif score >= 65:
        color = "\033[93m"   # yellow
    else:
        color = "\033[91m"   # red

    reset = "\033[0m"
    bold = "\033[1m"
    dim = "\033[2m"

    print(f"\n{dim}────────────────────────────────────────{reset}")
    print(f"🤖 {bold}Gemini Critic{reset} · {dim}{rel_path}{reset}")
    print(f"   score: {color}{bold}{score}/100{reset}  verdict: {color}{verdict}{reset}")
    if issues and issues not in ("없음", "none", "None"):
        print(f"   {dim}↳ {issues}{reset}")
    print(f"{dim}────────────────────────────────────────{reset}")

if __name__ == "__main__":
    main()
