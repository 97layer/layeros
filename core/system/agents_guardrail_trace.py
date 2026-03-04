#!/usr/bin/env python3
"""
agents_guardrail_trace.py

Static linkage audit for AGENTS.md runtime guardrails.

Purpose:
- Verify AGENTS.md intent is wired to executable hooks/scripts.
- Detect drift between root-file allowlists (guard_rules / validator / hook).
- Provide a single READY/BLOCKED signal for bootstrap integration.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set


ROOT = Path(__file__).resolve().parents[2]

AGENTS_MD = ROOT / "AGENTS.md"
SETTINGS_JSON = ROOT / ".claude" / "settings.json"
PLAN_CMD_MD = ROOT / ".claude" / "commands" / "plan.md"
PLAN_COUNCIL_CMD_MD = ROOT / ".claude" / "commands" / "plan-council.md"
PROACTIVE_TOOLS_MD = ROOT / ".claude" / "rules" / "proactive-tools.md"
GUARD_RULES_JSON = ROOT / "knowledge" / "system" / "guard_rules.json"
VALIDATOR_PY = ROOT / "core" / "system" / "filesystem_validator.py"
VALIDATE_PATH_SH = ROOT / ".claude" / "hooks" / "validate-path.sh"
PRACTICAL_HOOKS_PY = ROOT / "core" / "scripts" / "practical_hooks.py"
WEB_LOCK_PY = ROOT / "core" / "system" / "web_consistency_lock.py"

REQUIRED_ROOT_FILES = {"AGENTS.md", "CLAUDE.md", "README.md"}

REQUIRED_AGENTS_MARKERS = [
    "## Mandatory Read Order",
    "## Mandatory Startup",
    "## Web Work Lock Protocol",
    "## MCP Trigger Rule (Mandatory)",
    "## Anti-Hallucination Protocol (Mandatory)",
    "## Plan Council Protocol (Mandatory)",
    "## Filesystem Hard Rules (Mandatory)",
    "## Practical Automation Hooks (Mandatory)",
]

REQUIRED_PROACTIVE_TOOLS = [
    "plan-council",
    "sequential-thinking",
    "context7",
    "notebooklm",
]

REQUIRED_HOOK_COMMANDS = {
    "UserPromptSubmit": [
        ".claude/hooks/plan-council.sh",
        ".claude/hooks/proactive-advisor.sh",
    ],
    "SessionStart": [".claude/hooks/session-start.sh"],
    "PreToolUse": [
        ".claude/hooks/command-guard.sh",
        ".claude/hooks/context-guard.sh",
    ],
    "PostToolUse": [
        ".claude/hooks/validate-path.sh",
        ".claude/hooks/code-quality-check.sh",
    ],
    "Stop": [".claude/hooks/session-stop.sh"],
}

REQUIRED_PRACTICAL_SUBCOMMANDS = [
    "start",
    "hash-seal",
    "hash-check",
    "mobile-check",
    "permission-bump",
    "report",
]


def read_text(path: Path, issues: List[str]) -> str:
    if not path.is_file():
        issues.append(f"missing file: {path.relative_to(ROOT)}")
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def read_json(path: Path, issues: List[str]) -> Dict:
    if not path.is_file():
        issues.append(f"missing file: {path.relative_to(ROOT)}")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            issues.append(f"invalid json object: {path.relative_to(ROOT)}")
            return {}
        return data
    except Exception as exc:  # noqa: BLE001
        issues.append(f"invalid json: {path.relative_to(ROOT)} ({exc})")
        return {}


def parse_python_list_constant(text: str, const_name: str, issues: List[str], source: str) -> Set[str]:
    pattern = re.compile(rf"{re.escape(const_name)}\s*=\s*(\[[\s\S]*?\])", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        issues.append(f"missing constant: {const_name} in {source}")
        return set()
    try:
        value = ast.literal_eval(match.group(1))
        if not isinstance(value, list):
            issues.append(f"constant is not list: {const_name} in {source}")
            return set()
        return {str(item) for item in value}
    except Exception as exc:  # noqa: BLE001
        issues.append(f"failed to parse {const_name} in {source} ({exc})")
        return set()


def parse_validate_path_allowlist(text: str, issues: List[str], guard_allowed: Set[str]) -> Set[str]:
    # Dynamic single-source mode: validate-path reads guard_rules.json.
    if "guard_rules.json" in text and "LOADED_ROOT_FILES" in text:
        return set(guard_allowed)

    match = re.search(r'^ALLOWED_ROOT_FILES="([^"]+)"', text, flags=re.MULTILINE)
    if not match:
        issues.append("missing ALLOWED_ROOT_FILES in .claude/hooks/validate-path.sh")
        return set()
    raw = match.group(1).strip()
    if not raw:
        return set()
    return {token.strip() for token in raw.split() if token.strip()}


def parse_validator_allowlist(text: str, issues: List[str], guard_allowed: Set[str]) -> Set[str]:
    # Dynamic single-source mode: filesystem_validator reads guard_rules.json.
    if "GUARD_RULES" in text and "_load_root_allowed" in text and "allowed_root_files" in text:
        return set(guard_allowed)

    return parse_python_list_constant(
        text, "ROOT_ALLOWED", issues, "core/system/filesystem_validator.py"
    )


def collect_hook_commands(settings: Dict) -> Dict[str, Set[str]]:
    collected: Dict[str, Set[str]] = {}
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        return collected

    for event_name, groups in hooks.items():
        cmds: Set[str] = set()
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, dict):
                continue
            for hook in group.get("hooks", []):
                if not isinstance(hook, dict):
                    continue
                command = str(hook.get("command", "")).strip()
                if command:
                    cmds.add(command)
        collected[event_name] = cmds
    return collected


def run_checks() -> Dict:
    issues: List[str] = []
    checks: List[Dict[str, object]] = []

    agents_text = read_text(AGENTS_MD, issues)
    proactive_text = read_text(PROACTIVE_TOOLS_MD, issues)
    plan_cmd_text = read_text(PLAN_CMD_MD, issues)
    plan_council_cmd_text = read_text(PLAN_COUNCIL_CMD_MD, issues)
    validator_text = read_text(VALIDATOR_PY, issues)
    validate_path_text = read_text(VALIDATE_PATH_SH, issues)
    practical_text = read_text(PRACTICAL_HOOKS_PY, issues)
    web_lock_text = read_text(WEB_LOCK_PY, issues)
    settings = read_json(SETTINGS_JSON, issues)
    guard_rules = read_json(GUARD_RULES_JSON, issues)

    # AGENTS.md markers
    missing_agents = [m for m in REQUIRED_AGENTS_MARKERS if m not in agents_text]
    checks.append(
        {
            "name": "agents_markers",
            "ok": not missing_agents,
            "detail": "all required markers present" if not missing_agents else f"missing: {missing_agents}",
        }
    )
    for marker in missing_agents:
        issues.append(f"missing AGENTS marker: {marker}")

    # Proactive tools markers
    missing_tools = [t for t in REQUIRED_PROACTIVE_TOOLS if t not in proactive_text]
    checks.append(
        {
            "name": "proactive_tools_markers",
            "ok": not missing_tools,
            "detail": "all required tool triggers present" if not missing_tools else f"missing: {missing_tools}",
        }
    )
    for tool in missing_tools:
        issues.append(f"missing proactive tool trigger: {tool}")

    # /plan and /plan-council alias contracts
    plan_ok = "plan_dispatch.sh" in plan_cmd_text and "--manual" in plan_cmd_text
    council_ok = "core/system/plan_council.py --task" in plan_council_cmd_text
    checks.append({"name": "plan_alias_contract", "ok": plan_ok, "detail": "manual dispatch alias wired" if plan_ok else "plan alias missing dispatch/manual marker"})
    checks.append({"name": "plan_council_contract", "ok": council_ok, "detail": "plan-council command wired" if council_ok else "plan-council command marker missing"})
    if not plan_ok:
        issues.append("plan alias contract drift (.claude/commands/plan.md)")
    if not council_ok:
        issues.append("plan-council command drift (.claude/commands/plan-council.md)")

    # Hook registration in settings.json
    hook_commands = collect_hook_commands(settings)
    for event, required_cmds in REQUIRED_HOOK_COMMANDS.items():
        present = hook_commands.get(event, set())
        missing = [cmd for cmd in required_cmds if cmd not in present]
        checks.append(
            {
                "name": f"hook_{event}",
                "ok": not missing,
                "detail": "required hooks registered" if not missing else f"missing: {missing}",
            }
        )
        for cmd in missing:
            issues.append(f"missing hook command in settings.json ({event}): {cmd}")

    # Root allowlist consistency: guard_rules / validator / validate-path
    guard_allowed = set()
    if isinstance(guard_rules.get("allowed_root_files"), list):
        guard_allowed = {str(item) for item in guard_rules["allowed_root_files"]}
    else:
        issues.append("missing allowed_root_files list in knowledge/system/guard_rules.json")

    validator_allowed = parse_validator_allowlist(validator_text, issues, guard_allowed)
    validate_path_allowed = parse_validate_path_allowlist(validate_path_text, issues, guard_allowed)

    missing_guard = sorted(REQUIRED_ROOT_FILES - guard_allowed)
    missing_validator = sorted(REQUIRED_ROOT_FILES - validator_allowed)
    missing_validate_path = sorted(REQUIRED_ROOT_FILES - validate_path_allowed)

    checks.append(
        {
            "name": "root_allowlist_guard_rules",
            "ok": not missing_guard,
            "detail": "required root files allowed" if not missing_guard else f"missing: {missing_guard}",
        }
    )
    checks.append(
        {
            "name": "root_allowlist_validator",
            "ok": not missing_validator,
            "detail": "required root files allowed" if not missing_validator else f"missing: {missing_validator}",
        }
    )
    checks.append(
        {
            "name": "root_allowlist_validate_path",
            "ok": not missing_validate_path,
            "detail": "required root files allowed" if not missing_validate_path else f"missing: {missing_validate_path}",
        }
    )

    for name in missing_guard:
        issues.append(f"guard_rules missing root allowlist entry: {name}")
    for name in missing_validator:
        issues.append(f"filesystem_validator missing ROOT_ALLOWED entry: {name}")
    for name in missing_validate_path:
        issues.append(f"validate-path missing ALLOWED_ROOT_FILES entry: {name}")

    # Practical hooks subcommands
    missing_subcommands = [
        cmd for cmd in REQUIRED_PRACTICAL_SUBCOMMANDS if f'sub.add_parser("{cmd}"' not in practical_text
    ]
    checks.append(
        {
            "name": "practical_hooks_subcommands",
            "ok": not missing_subcommands,
            "detail": "all required practical hook subcommands present"
            if not missing_subcommands
            else f"missing: {missing_subcommands}",
        }
    )
    for cmd in missing_subcommands:
        issues.append(f"practical_hooks.py missing subcommand: {cmd}")

    # Web lock protocol markers
    lock_markers = ["--acquire", "--validate", "--release"]
    missing_lock_markers = [m for m in lock_markers if m not in web_lock_text]
    checks.append(
        {
            "name": "web_lock_markers",
            "ok": not missing_lock_markers,
            "detail": "acquire/validate/release markers present"
            if not missing_lock_markers
            else f"missing: {missing_lock_markers}",
        }
    )
    for marker in missing_lock_markers:
        issues.append(f"web_consistency_lock missing marker: {marker}")

    status = "ready" if not issues else "blocked"
    return {
        "status": status,
        "checks": checks,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Trace AGENTS guardrail wiring")
    parser.add_argument("--check", action="store_true", help="run guardrail linkage checks")
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    args = parser.parse_args()

    if not args.check and not args.json:
        args.check = True

    result = run_checks()

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["status"] == "ready" else 1

    if result["status"] == "ready":
        print("READY")
        return 0

    for issue in result["issues"]:
        print(f"BLOCKED {issue}")
    print("BLOCKED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
