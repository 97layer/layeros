#!/usr/bin/env python3
"""
Council room issue loop.

Goals:
- Detect new `proposal_id` entries in `knowledge/agent_hub/council_room.md`
- Sync unresolved items into a shared queue for cross-session visibility
- Let an agent claim/resolve an item
- Delete queue item on resolve by default (rotation), while logging events
"""

from __future__ import annotations

import argparse
import os
import json
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[2]

HEADING_RE = re.compile(r"^##\s+\[(?P<ts>[^\]]+)\]\s*(?P<title>.*)$")
PROPOSAL_RE = re.compile(r"\*\*proposal_id\*\*:\s*`([^`]+)`")
DECISION_TOKEN_RE = re.compile(r"\(proposal=([A-Za-z0-9._-]+)\)")
STATUS_RE = re.compile(r"\*\*status\*\*:\s*([^\n]+)")


@dataclass(frozen=True)
class LoopPaths:
    root: Path
    council_room: Path
    decision_log: Path
    queue_root: Path
    locks_dir: Path
    pending_dir: Path
    processing_dir: Path
    completed_dir: Path
    event_log: Path
    snapshot_file: Path


def build_paths(root: Optional[Path] = None) -> LoopPaths:
    base = (root or PROJECT_ROOT).resolve()
    queue_root = base / ".infra" / "queue" / "council_room"
    return LoopPaths(
        root=base,
        council_room=base / "knowledge" / "agent_hub" / "council_room.md",
        decision_log=base / "knowledge" / "system" / "decision_log.jsonl",
        queue_root=queue_root,
        locks_dir=queue_root / "locks",
        pending_dir=queue_root / "pending",
        processing_dir=queue_root / "processing",
        completed_dir=queue_root / "completed",
        event_log=base / "knowledge" / "system" / "council_issue_events.jsonl",
        snapshot_file=base / "knowledge" / "system" / "council_issue_snapshot.json",
    )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs(paths: LoopPaths) -> None:
    paths.locks_dir.mkdir(parents=True, exist_ok=True)
    paths.pending_dir.mkdir(parents=True, exist_ok=True)
    paths.processing_dir.mkdir(parents=True, exist_ok=True)
    paths.completed_dir.mkdir(parents=True, exist_ok=True)
    paths.event_log.parent.mkdir(parents=True, exist_ok=True)
    paths.snapshot_file.parent.mkdir(parents=True, exist_ok=True)


def append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sanitize_issue_id(issue_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", issue_id.strip())
    return safe or "unnamed_issue"


@contextmanager
def issue_lock(paths: LoopPaths, issue_id: str, *, timeout: float = 2.0, poll: float = 0.05) -> Iterator[None]:
    """
    Lightweight per-issue lock using O_EXCL file creation.
    Prevents concurrent claim/resolve races across agent sessions.
    """

    ensure_dirs(paths)
    lock_path = paths.locks_dir / f"{sanitize_issue_id(issue_id)}.lock"
    deadline = time.monotonic() + max(0.01, timeout)
    pid = os.getpid()
    token = f"{pid}:{now_iso()}\n".encode("utf-8")

    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            try:
                os.write(fd, token)
            finally:
                os.close(fd)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"lock timeout: {issue_id}")
            time.sleep(max(0.01, poll))

    try:
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def load_decision_ids(path: Path) -> set[str]:
    resolved: set[str] = set()
    if not path.exists():
        return resolved
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        if str(row.get("type", "")).strip() not in {"council_approve", "council_reject"}:
            continue
        proposal_id = str(row.get("id", "")).strip()
        if proposal_id:
            resolved.add(proposal_id)
    return resolved


def normalize_title(raw_title: str) -> str:
    text = (raw_title or "").strip()
    if "—" in text:
        parts = [part.strip() for part in text.split("—", 1)]
        return parts[-1] or text
    return text


def extract_excerpt(block_text: str) -> str:
    in_code = False
    for raw in block_text.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if not line:
            continue
        if line.startswith("## "):
            continue
        if line.startswith("**proposal_id**"):
            continue
        if line.startswith("**제안자**"):
            continue
        if line.startswith("**status**"):
            continue
        if line.startswith("---"):
            continue
        return line[:280]
    return ""


def parse_council_room(path: Path) -> Tuple[List[Dict[str, Any]], set[str]]:
    if not path.exists():
        return [], set()

    text = path.read_text(encoding="utf-8")
    resolved_in_room = set(DECISION_TOKEN_RE.findall(text))

    blocks: List[Tuple[str, str, List[str]]] = []
    current_ts = ""
    current_title = ""
    current_lines: List[str] = []

    for raw in text.splitlines():
        match = HEADING_RE.match(raw.strip())
        if match:
            if current_lines:
                blocks.append((current_ts, current_title, current_lines))
            current_ts = match.group("ts").strip()
            current_title = match.group("title").strip()
            current_lines = [raw]
            continue
        if current_lines:
            current_lines.append(raw)

    if current_lines:
        blocks.append((current_ts, current_title, current_lines))

    issues: List[Dict[str, Any]] = []
    for ts, heading, lines in blocks:
        block_text = "\n".join(lines)
        proposal_ids = []
        seen: set[str] = set()
        for pid in PROPOSAL_RE.findall(block_text):
            proposal_id = pid.strip()
            if proposal_id and proposal_id not in seen:
                proposal_ids.append(proposal_id)
                seen.add(proposal_id)
        if not proposal_ids:
            continue

        status_match = STATUS_RE.search(block_text)
        status_text = status_match.group(1).strip().lower() if status_match else ""
        status_closed = any(
            token in status_text for token in ("resolved", "approved", "rejected", "done", "complete")
        ) or any(token in status_text for token in ("즉시 발효", "활성"))

        title = normalize_title(heading) or "Council issue"
        excerpt = extract_excerpt(block_text)
        for proposal_id in proposal_ids:
            if status_closed:
                resolved_in_room.add(proposal_id)
            issues.append(
                {
                    "issue_id": proposal_id,
                    "title": title,
                    "created_at": ts or "",
                    "excerpt": excerpt,
                    "source": "council_room",
                }
            )

    return issues, resolved_in_room


def list_queue_items(base_dir: Path) -> Dict[str, Tuple[Path, Dict[str, Any]]]:
    items: Dict[str, Tuple[Path, Dict[str, Any]]] = {}
    if not base_dir.exists():
        return items

    for file_path in sorted(base_dir.glob("*.json")):
        payload: Dict[str, Any]
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        issue_id = str(payload.get("issue_id") or file_path.stem).strip()
        if not issue_id:
            issue_id = file_path.stem
        items[issue_id] = (file_path, payload)
    return items


def queue_state(paths: LoopPaths) -> Dict[str, Dict[str, Tuple[Path, Dict[str, Any]]]]:
    return {
        "pending": list_queue_items(paths.pending_dir),
        "processing": list_queue_items(paths.processing_dir),
        "completed": list_queue_items(paths.completed_dir),
    }


def build_snapshot(paths: LoopPaths, max_items: int = 5) -> Dict[str, Any]:
    state = queue_state(paths)
    snapshot = {
        "timestamp": now_iso(),
        "queue_root": str(paths.queue_root),
        "counts": {
            "pending": len(state["pending"]),
            "processing": len(state["processing"]),
            "completed": len(state["completed"]),
        },
        "pending_items": sorted(list(state["pending"].keys()))[:max_items],
        "processing_items": sorted(list(state["processing"].keys()))[:max_items],
        "completed_items": sorted(list(state["completed"].keys()))[:max_items],
    }
    write_json(paths.snapshot_file, snapshot)
    return snapshot


def sync_from_council_room(paths: LoopPaths) -> Dict[str, Any]:
    ensure_dirs(paths)
    issues, resolved_in_room = parse_council_room(paths.council_room)
    resolved_ids = set(resolved_in_room) | load_decision_ids(paths.decision_log)

    active_issues: Dict[str, Dict[str, Any]] = {}
    for issue in issues:
        issue_id = str(issue.get("issue_id", "")).strip()
        if not issue_id or issue_id in resolved_ids:
            continue
        active_issues[issue_id] = issue

    state = queue_state(paths)
    existing_ids = set(state["pending"].keys()) | set(state["processing"].keys()) | set(state["completed"].keys())

    created: List[str] = []
    for issue_id, issue in sorted(active_issues.items()):
        if issue_id in existing_ids:
            continue
        filename = f"{sanitize_issue_id(issue_id)}.json"
        path = paths.pending_dir / filename
        if path.exists():
            filename = f"{sanitize_issue_id(issue_id)}_{abs(hash(issue_id)) % 10000}.json"
            path = paths.pending_dir / filename
        payload = {
            **issue,
            "status": "pending",
            "detected_at": now_iso(),
            "claimed_by": None,
            "claimed_at": None,
        }
        write_json(path, payload)
        created.append(issue_id)
        append_jsonl(
            paths.event_log,
            {
                "timestamp": now_iso(),
                "event": "synced",
                "issue_id": issue_id,
                "title": issue.get("title", ""),
            },
        )

    pruned: List[str] = []
    if resolved_ids:
        for state_name, rows in queue_state(paths).items():
            for issue_id, (file_path, _payload) in rows.items():
                if issue_id in resolved_ids:
                    try:
                        file_path.unlink()
                    except FileNotFoundError:
                        pass
                    pruned.append(f"{state_name}:{issue_id}")

    snapshot = build_snapshot(paths, max_items=5)
    result = {
        "timestamp": now_iso(),
        "created": created,
        "pruned": pruned,
        "counts": snapshot["counts"],
    }
    return result


def find_issue(paths: LoopPaths, issue_id: str) -> Tuple[Optional[str], Optional[Path], Dict[str, Any]]:
    target = issue_id.strip()
    if not target:
        return None, None, {}
    for state_name, rows in queue_state(paths).items():
        hit = rows.get(target)
        if hit:
            path, payload = hit
            return state_name, path, payload
    return None, None, {}


def claim_issue(paths: LoopPaths, issue_id: str, agent: str, *, lock_timeout: float = 2.0) -> Dict[str, Any]:
    ensure_dirs(paths)
    with issue_lock(paths, issue_id, timeout=lock_timeout):
        sync_from_council_room(paths)

        state_name, src_path, payload = find_issue(paths, issue_id)
        if state_name is None or src_path is None:
            raise FileNotFoundError(f"issue not found: {issue_id}")

        claimed_by = str(payload.get("claimed_by") or "").strip()
        if state_name == "processing":
            if claimed_by and claimed_by != agent:
                raise PermissionError(f"already claimed by {claimed_by}")
            return {
                "issue_id": issue_id,
                "state": state_name,
                "claimed_by": agent,
                "already_claimed": True,
            }

        if state_name == "completed":
            raise PermissionError(f"already completed: {issue_id}")

        payload["issue_id"] = issue_id
        payload["status"] = "processing"
        payload["claimed_by"] = agent
        payload["claimed_at"] = now_iso()
        dst_path = paths.processing_dir / src_path.name
        write_json(dst_path, payload)
        try:
            src_path.unlink()
        except FileNotFoundError:
            pass

        append_jsonl(
            paths.event_log,
            {
                "timestamp": now_iso(),
                "event": "claimed",
                "issue_id": issue_id,
                "agent": agent,
            },
        )
        build_snapshot(paths, max_items=5)
        return {"issue_id": issue_id, "state": "processing", "claimed_by": agent, "already_claimed": False}


def append_resolution_marker(council_room: Path, issue_id: str, agent: str, result: str) -> None:
    council_room.parent.mkdir(parents=True, exist_ok=True)
    local_ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    status_label = {
        "approved": "✅ 승인",
        "rejected": "❌ 거절",
        "done": "✅ 처리 완료",
    }.get(result, "✅ 처리 완료")
    line = f"- [{local_ts}] {status_label} (proposal={issue_id}) by {agent}\n"
    with council_room.open("a", encoding="utf-8") as fp:
        fp.write("\n" + line)


def resolve_issue(
    paths: LoopPaths,
    issue_id: str,
    agent: str,
    result: str,
    *,
    keep_completed: bool = False,
    force: bool = False,
    lock_timeout: float = 2.0,
) -> Dict[str, Any]:
    ensure_dirs(paths)
    with issue_lock(paths, issue_id, timeout=lock_timeout):
        sync_from_council_room(paths)

        state_name, src_path, payload = find_issue(paths, issue_id)
        if state_name is None:
            raise FileNotFoundError(f"issue not found: {issue_id}")
        if state_name == "completed":
            return {"issue_id": issue_id, "state": "completed", "deleted": False, "already_resolved": True}

        claimed_by = str(payload.get("claimed_by") or "").strip()
        if state_name == "pending" and not force:
            raise PermissionError("issue must be claimed before resolve")
        if not claimed_by and state_name == "processing" and not force:
            raise PermissionError("processing issue has no owner; use --force")
        if claimed_by and claimed_by != agent and not force:
            raise PermissionError(f"issue claimed by {claimed_by}")

        payload["issue_id"] = issue_id
        payload["status"] = "completed"
        payload["resolved_at"] = now_iso()
        payload["resolved_by"] = agent
        payload["result"] = result

        append_resolution_marker(paths.council_room, issue_id, agent, result)
        append_jsonl(
            paths.event_log,
            {
                "timestamp": now_iso(),
                "event": "resolved",
                "issue_id": issue_id,
                "agent": agent,
                "result": result,
                "from_state": state_name,
            },
        )

        removed_paths = []
        for _state, rows in queue_state(paths).items():
            hit = rows.get(issue_id)
            if not hit:
                continue
            path, _payload = hit
            try:
                path.unlink()
                removed_paths.append(str(path))
            except FileNotFoundError:
                pass

        completed_path = None
        if keep_completed:
            completed_path = paths.completed_dir / f"{sanitize_issue_id(issue_id)}.json"
            write_json(completed_path, payload)

        snapshot = build_snapshot(paths, max_items=5)
        return {
            "issue_id": issue_id,
            "state": "completed",
            "deleted": not keep_completed,
            "removed_paths": removed_paths,
            "completed_path": str(completed_path) if completed_path else None,
            "counts": snapshot["counts"],
        }


def watch(paths: LoopPaths, max_items: int = 3) -> Dict[str, Any]:
    sync_result = sync_from_council_room(paths)
    snapshot = build_snapshot(paths, max_items=max_items)
    return {
        "timestamp": now_iso(),
        "new_pending": sync_result["created"],
        "pruned": sync_result["pruned"],
        "counts": snapshot["counts"],
        "pending_items": snapshot["pending_items"],
        "processing_items": snapshot["processing_items"],
    }


def print_watch_text(payload: Dict[str, Any], quiet_empty: bool) -> None:
    counts = payload.get("counts", {})
    pending = int(counts.get("pending", 0))
    processing = int(counts.get("processing", 0))
    new_pending = payload.get("new_pending", [])

    if quiet_empty and pending == 0 and processing == 0 and not new_pending:
        return

    print(
        "[council-issue-loop] "
        f"pending={pending} processing={processing} new={len(new_pending)}"
    )
    if payload.get("pending_items"):
        print("[council-issue-loop] pending_ids=" + ",".join(payload["pending_items"]))
    if payload.get("processing_items"):
        print("[council-issue-loop] processing_ids=" + ",".join(payload["processing_items"]))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Council room issue loop")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT, help="project root")

    sub = parser.add_subparsers(dest="command", required=True)

    sync_parser = sub.add_parser("sync", help="sync unresolved council_room issues into queue")
    sync_parser.add_argument("--json", action="store_true", dest="as_json")

    watch_parser = sub.add_parser("watch", help="sync + snapshot summary")
    watch_parser.add_argument("--max-items", type=int, default=3)
    watch_parser.add_argument("--quiet-empty", action="store_true")
    watch_parser.add_argument("--json", action="store_true", dest="as_json")

    status_parser = sub.add_parser("status", help="queue snapshot only")
    status_parser.add_argument("--max-items", type=int, default=5)
    status_parser.add_argument("--json", action="store_true", dest="as_json")

    claim_parser = sub.add_parser("claim", help="claim issue to processing")
    claim_parser.add_argument("--issue-id", required=True)
    claim_parser.add_argument("--agent", required=True)
    claim_parser.add_argument("--json", action="store_true", dest="as_json")

    resolve_parser = sub.add_parser("resolve", help="resolve issue and rotate queue")
    resolve_parser.add_argument("--issue-id", required=True)
    resolve_parser.add_argument("--agent", required=True)
    resolve_parser.add_argument(
        "--result",
        default="done",
        choices=["done", "approved", "rejected"],
    )
    resolve_parser.add_argument("--keep-completed", action="store_true")
    resolve_parser.add_argument("--force", action="store_true")
    resolve_parser.add_argument("--json", action="store_true", dest="as_json")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = build_paths(args.root)

    try:
        if args.command == "sync":
            payload = sync_from_council_room(paths)
            if args.as_json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                counts = payload.get("counts", {})
                print(
                    "created=%d pruned=%d pending=%d processing=%d completed=%d"
                    % (
                        len(payload.get("created", [])),
                        len(payload.get("pruned", [])),
                        int(counts.get("pending", 0)),
                        int(counts.get("processing", 0)),
                        int(counts.get("completed", 0)),
                    )
                )
            return 0

        if args.command == "watch":
            payload = watch(paths, max_items=max(1, int(args.max_items)))
            if args.as_json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print_watch_text(payload, quiet_empty=bool(args.quiet_empty))
            return 0

        if args.command == "status":
            payload = build_snapshot(paths, max_items=max(1, int(args.max_items)))
            if args.as_json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                counts = payload.get("counts", {})
                print(
                    "pending=%d processing=%d completed=%d"
                    % (
                        int(counts.get("pending", 0)),
                        int(counts.get("processing", 0)),
                        int(counts.get("completed", 0)),
                    )
                )
            return 0

        if args.command == "claim":
            payload = claim_issue(paths, args.issue_id, args.agent)
            if args.as_json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(
                    "claimed issue_id=%s by=%s already_claimed=%s"
                    % (payload["issue_id"], payload["claimed_by"], payload["already_claimed"])
                )
            return 0

        if args.command == "resolve":
            payload = resolve_issue(
                paths,
                args.issue_id,
                args.agent,
                args.result,
                keep_completed=bool(args.keep_completed),
                force=bool(args.force),
            )
            if args.as_json:
                print(json.dumps(payload, ensure_ascii=False))
            else:
                print(
                    "resolved issue_id=%s deleted=%s"
                    % (payload["issue_id"], str(payload.get("deleted", False)).lower())
                )
            return 0

    except (FileNotFoundError, PermissionError, TimeoutError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
