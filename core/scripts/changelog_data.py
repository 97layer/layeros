#!/usr/bin/env python3
"""
changelog_data.py — website/lab/changelog/data.json 생성
git log + git status(미커밋) + 파일 수정시각 통합

실행: python3 core/scripts/changelog_data.py
"""
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
WEBSITE_DIR  = PROJECT_ROOT / "website"
OUTPUT       = PROJECT_ROOT / "website" / "lab" / "changelog" / "data.json"
START_DATE   = "2026-02-18"

def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT).stdout.strip()

def git_commits():
    """website/ 경로 커밋 로그"""
    log = run([
        "git", "log", "--format=%H|%aI|%s", "--", "website/"
    ])
    entries = []
    for line in log.splitlines():
        if not line.strip():
            continue
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        sha, date_str, subject = parts
        subject = subject.strip()
        # prefix 제거
        import re
        subject = re.sub(r'^(feat|fix|refactor|chore|style|docs|test):\s*', '', subject, flags=re.I)
        entries.append({
            "type": "commit",
            "sha": sha[:7],
            "date": date_str.strip(),
            "msg": subject,
            "rawMsg": parts[2].strip()
        })
    return entries

def git_uncommitted():
    """미커밋 변경 (website/ 한정)"""
    status = run(["git", "status", "--short", "--", "website/"])
    entries = []
    now = datetime.now(timezone.utc).isoformat()
    for line in status.splitlines():
        if not line.strip():
            continue
        code = line[:2].strip()
        path = line[3:].strip()
        if not path.startswith("website/"):
            continue
        label_map = {"M": "수정", "A": "추가", "D": "삭제", "?": "미추적", "R": "이름변경"}
        label = label_map.get(code[0], code)
        entries.append({
            "type": "local",
            "sha": "local",
            "date": now,
            "msg": f"[{label}] {path.replace('website/', '')}"
        })
    return entries

def recently_modified():
    """git 외 로컬 파일 수정시각 (최근 7일, 커밋/미커밋 중복 제외)"""
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).timestamp()
    entries = []
    for f in WEBSITE_DIR.rglob("*"):
        if not f.is_file():
            continue
        # 제외: node_modules, .git, data.json 자기 자신
        rel = f.relative_to(PROJECT_ROOT)
        rel_str = str(rel)
        if any(p in rel_str for p in ["node_modules", ".git", "changelog/data.json"]):
            continue
        mtime = f.stat().st_mtime
        if mtime < cutoff:
            continue
        dt = datetime.fromtimestamp(mtime, tz=timezone.utc)
        entries.append({
            "type": "file",
            "sha": "fs",
            "date": dt.isoformat(),
            "msg": f"[파일] {str(f.relative_to(WEBSITE_DIR))}"
        })
    return entries

def calculate_invested_hours(commits):
    if not commits: return 0
    sorted_commits = sorted(commits, key=lambda x: x["date"])
    total_minutes = 0
    previous_time = None
    
    for c in sorted_commits:
        try:
            dt = datetime.fromisoformat(c["date"])
            if previous_time is None:
                total_minutes += 45
            else:
                diff = (dt - previous_time).total_seconds() / 60
                if diff < 120:
                    total_minutes += diff
                else:
                    total_minutes += 45
            previous_time = dt
        except Exception:
            pass
            
    return round(total_minutes / 60, 1)

def git_diff_stats():
    """website/ 경로의 삽입/삭제 라인 수 집계"""
    import re
    log = run(["git", "log", "--shortstat", "--", "website/"])
    added = 0
    deleted = 0
    for line in log.splitlines():
        if "changed" in line:
            ins_match = re.search(r'(\d+)\s+insertion', line)
            del_match = re.search(r'(\d+)\s+deletion', line)
            if ins_match:
                added += int(ins_match.group(1))
            if del_match:
                deleted += int(del_match.group(1))
    return added, deleted

def main():
    commits     = git_commits()
    uncommitted = git_uncommitted()
    invested_hours = calculate_invested_hours(commits)

    # 커밋에 이미 있는 파일은 recently_modified에서 제외
    committed_paths = set()
    for c in commits:
        if c["msg"].startswith("[파일]"):
            committed_paths.add(c["msg"])

    # 병합 — uncommitted 먼저, 커밋, 파일
    all_entries = uncommitted + commits
    # date 기준 정렬 (최신순)
    all_entries.sort(key=lambda x: x["date"], reverse=True)

    lines_added, lines_deleted = git_diff_stats()

    days = (datetime.now(timezone.utc) - datetime.fromisoformat(START_DATE + "T00:00:00+00:00")).days + 1

    output = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "start_date": START_DATE,
        "days": days,
        "total_commits": len(commits),
        "uncommitted": len(uncommitted),
        "invested_hours": invested_hours,
        "lines_added": lines_added,
        "lines_deleted": lines_deleted,
        "entries": all_entries
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"생성 완료: {OUTPUT}")
    print(f"  커밋: {len(commits)}건 / 미커밋: {len(uncommitted)}건 / 기간: {days}일째")

if __name__ == "__main__":
    main()
