"""
Repo guardrail audit.

Checks currently implemented (fail-fast if any violation found):
1) Forbidden paths/files (AGENTS.md Filesystem Hard Rules)
2) Forbidden vocabulary (sage_architect.md §9 금지 어휘)

Output: human-readable text by default, or JSON via --json.
Exit code: 0 if clean, 1 if any finding, 2 on runtime error.

Note: Lightweight by design (no external deps). Uses rg when available for speed.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any

ROOT = Path(__file__).resolve().parents[2]  # /Users/97layer/97layerOS

ALLOW_DIR_PREFIXES = [
    "knowledge/system/quarantine",
]

SKIP_TERM_PREFIXES = [
    "directives",  # 규약 문서 내 금지어 예시는 스킵
    "knowledge/system",  # 시스템 로그·리포트
    "knowledge/system/quarantine",
    "website/lab",
    "website/assets/media",
    "website/woosunho/works",
    ".git",
    ".venv",
    ".codex",
]

SKIP_TERM_FILES = {
    (ROOT / "core/scripts/code_audit.py").resolve(),  # 자기 자신 (금지어 목록 포함)
    (ROOT / "website/privacy.html").resolve(),  # 법적 문구 예외
    (ROOT / "website/terms.html").resolve(),  # 법적 문구 예외
}

TERM_SCAN_SUFFIXES = {".html", ".md", ".json", ".txt", ".yaml", ".yml"}

FORBIDDEN_PATHS = [
    ROOT / "src",
    ROOT / "output",
    ROOT / "package.json",
    ROOT / "package-lock.json",
    ROOT / "woohwahae_cms.db",
]

FORBIDDEN_GLOBS = ["*.db", "*.sqlite", "*.sqlite3"]

FORBIDDEN_TERMS = [
    "트렌드",
    "유행",
    "핫한",
    "최고",
    "최상",
    "베스트",
    "성공",
    "성취",
    "정복",
    "레벨업",
    "업그레이드",
    "효율",
    "생산성",
    "ROI",
    "꿀팁",
    "노하우",
    "공략",
    "힐링",
    "치유",
    "행복",
    "만족",
    "기쁨",
    "함께",
    "연결",
    "소통",
    "특별한",
    "특별함",
]


def check_forbidden_paths() -> List[str]:
    issues: List[str] = []
    for path in FORBIDDEN_PATHS:
        if path.exists():
            issues.append(f"forbidden path exists: {path.relative_to(ROOT)}")
    for pattern in FORBIDDEN_GLOBS:
        for hit in ROOT.rglob(pattern):
            rel = hit.relative_to(ROOT)
            rel_posix = rel.as_posix()
            if any(rel_posix.startswith(pref) for pref in ALLOW_DIR_PREFIXES):
                continue
            if any(part.startswith(".git") or part == ".venv" for part in hit.parts):
                continue
            issues.append(f"forbidden glob match: {rel}")
    return issues


def _normalize_issue(issue_type: str, issue: str) -> str:
    if issue_type == "terms":
        # expected: path:line: snippet (term='...')
        m = re.match(r"^(.*?):\d+:.*\(term='(.+)'\)$", issue)
        if m:
            return f"terms|{m.group(1)}|{m.group(2)}"
    return f"{issue_type}|{issue}"


def _load_baseline_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    ids = data.get("issue_ids")
    if not isinstance(ids, list):
        return set()
    return {str(x) for x in ids}


def _save_baseline(path: Path, findings: Dict[str, Any]) -> None:
    issue_ids: List[str] = []
    for issue in findings.get("paths", []):
        issue_ids.append(_normalize_issue("paths", issue))
    for issue in findings.get("terms", []):
        issue_ids.append(_normalize_issue("terms", issue))
    payload = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "issue_ids": sorted(set(issue_ids)),
        "counts": {
            "paths": len(findings.get("paths", [])),
            "terms": len(findings.get("terms", [])),
            "total_ids": len(set(issue_ids)),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_probably_text(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:8192]
    except Exception:
        return False
    if not chunk:
        return True
    if b"\x00" in chunk:
        return False
    bad = sum(1 for b in chunk if (b < 9) or (13 < b < 32))
    return (bad / len(chunk)) < 0.30


def _git_changed_files(scope: str = "head") -> List[Path]:
    files: List[Path] = []
    if scope == "staged":
        cmds = [["git", "diff", "--name-only", "--cached"]]
    elif scope == "unstaged":
        cmds = [["git", "diff", "--name-only"]]
    else:
        # HEAD scope captures staged + unstaged changes relative to HEAD.
        cmds = [["git", "diff", "--name-only", "HEAD"]]
    for cmd in cmds:
        res = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, check=False)
        for line in res.stdout.splitlines():
            p = (ROOT / line.strip()).resolve()
            if p.exists() and p.is_file():
                files.append(p)
    # de-dup while preserving order
    seen = set()
    uniq: List[Path] = []
    for p in files:
        if p in seen:
            continue
        seen.add(p)
        uniq.append(p)
    return uniq


def _fallback_target_files() -> List[Path]:
    targets = []
    for d in ["website"]:
        base = ROOT / d
        if base.exists():
            targets.extend([p for p in base.rglob("*") if p.is_file()])
    return targets


def _candidate_files(scan_all: bool, scope: str) -> List[Path]:
    if scan_all:
        return _fallback_target_files()
    return _git_changed_files(scope=scope)


def check_forbidden_terms(scan_all: bool, scope: str) -> List[str]:
    issues: List[str] = []
    for path in _candidate_files(scan_all, scope):
        try:
            rel = path.relative_to(ROOT)
        except Exception:
            rel = path
        rel_posix = rel.as_posix()
        if any(rel_posix.startswith(pref) for pref in ALLOW_DIR_PREFIXES):
            continue
        if any(rel_posix.startswith(pref) for pref in SKIP_TERM_PREFIXES):
            continue
        if path.resolve() in SKIP_TERM_FILES:
            continue
        if path.suffix.lower() not in TERM_SCAN_SUFFIXES:
            continue
        try:
            if path.stat().st_size > 512 * 1024:
                continue
            if not _is_probably_text(path):
                continue
            text = path.read_text(errors="ignore")
        except Exception:
            continue
        lower = text.lower()
        for term in FORBIDDEN_TERMS:
            if term.isascii():
                # ASCII terms (e.g., ROI) should match as whole words only.
                m = re.search(rf"\b{re.escape(term)}\b", text, flags=re.IGNORECASE)
                if not m:
                    continue
                idx = m.start()
            else:
                idx = lower.find(term.lower())
                if idx == -1:
                    continue
            # find line number for first occurrence
            line_no = lower.count("\n", 0, idx) + 1
            snippet = text.splitlines()[line_no - 1].strip() if text.splitlines() else ""
            issues.append(f"{rel}:{line_no}: {snippet} (term='{term}')")
    return issues


def collect_findings(args) -> Dict[str, Any]:
    findings: Dict[str, Any] = {"paths": [], "terms": []}
    if args.check in ("all", "paths"):
        findings["paths"] = check_forbidden_paths()
    if args.check in ("all", "terms"):
        findings["terms"] = check_forbidden_terms(scan_all=args.scan_all, scope=args.scope)
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Run repo guardrail audit")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--output", type=Path, help="write report to file")
    parser.add_argument("--scan-all", action="store_true", help="scan all allowed content even if git diff is empty")
    parser.add_argument("--warn-only", action="store_true", help="always exit 0 (useful for CI soft gates)")
    parser.add_argument(
        "--check",
        choices=["all", "paths", "terms"],
        default="all",
        help="which checks to run",
    )
    parser.add_argument(
        "--scope",
        choices=["head", "staged", "unstaged"],
        default="head",
        help="changed-file scope when not using --scan-all",
    )
    parser.add_argument(
        "--use-baseline",
        action="store_true",
        help="treat issues present in baseline as allowed; fail only on new issues",
    )
    parser.add_argument(
        "--baseline-file",
        type=Path,
        default=ROOT / "knowledge/system/code_audit_baseline.json",
        help="baseline JSON file path",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="write current findings to baseline file and exit 0",
    )
    args = parser.parse_args()

    try:
        findings = collect_findings(args)
    except Exception as e:  # defensive
        print(f"ERROR: audit failed: {e}", file=sys.stderr)
        return 2

    if args.update_baseline:
        _save_baseline(args.baseline_file, findings)
        print(f"[code-audit] baseline updated: {args.baseline_file}")
        return 0

    filtered = {"paths": list(findings["paths"]), "terms": list(findings["terms"])}
    baseline_existing = 0
    if args.use_baseline:
        baseline_ids = _load_baseline_ids(args.baseline_file)
        new_paths = []
        new_terms = []
        for issue in findings["paths"]:
            if _normalize_issue("paths", issue) in baseline_ids:
                baseline_existing += 1
                continue
            new_paths.append(issue)
        for issue in findings["terms"]:
            if _normalize_issue("terms", issue) in baseline_ids:
                baseline_existing += 1
                continue
            new_terms.append(issue)
        filtered["paths"] = new_paths
        filtered["terms"] = new_terms

    has_issues = bool(filtered["paths"] or filtered["terms"])

    if args.json:
        payload = {
            "root": str(ROOT),
            "has_issues": has_issues,
            "findings": findings,
            "filtered_findings": filtered,
            "baseline_existing": baseline_existing,
        }
        out = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        lines: List[str] = []
        status = "FAIL" if has_issues else "PASS"
        lines.append(f"[code-audit] status: {status}")
        if args.use_baseline:
            lines.append(f"- baseline matched (ignored): {baseline_existing}")
        if filtered["paths"]:
            lines.append("- forbidden paths:")
            lines.extend([f"  - {item}" for item in filtered["paths"]])
        if filtered["terms"]:
            lines.append("- forbidden terms:")
            lines.extend([f"  - {item}" for item in filtered["terms"]])
        if not has_issues:
            lines.append("- clean: no forbidden paths or terms found")
        out = "\n".join(lines)

    if args.output:
        args.output.write_text(out)
    print(out)
    if args.warn_only:
        return 0
    return 1 if has_issues else 0


if __name__ == "__main__":
    sys.exit(main())
