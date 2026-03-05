#!/usr/bin/env python3
"""
LAYER OS Session Handoff Engine
세션 연속성 보장 + Container-First 원칙 준수 + 멀티에이전트 병렬 지원

Author: LAYER OS Technical Director
"""

import json
import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import hashlib
import subprocess
import re
from contextlib import contextmanager

try:
    import fcntl  # POSIX file lock
except ImportError:  # pragma: no cover
    fcntl = None

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Knowledge paths (formerly from system.libs.core_config)
KNOWLEDGE_PATHS = {
    'signals': PROJECT_ROOT / 'knowledge' / 'signals',
    'insights': PROJECT_ROOT / 'knowledge' / 'insights',
    'content': PROJECT_ROOT / 'knowledge' / 'content',
    'system': PROJECT_ROOT / 'knowledge' / 'system',
    'archive': PROJECT_ROOT / 'knowledge' / 'archive',
}

CURRENT_STATE_HEADER = "## 📍 현재 상태 (CURRENT STATE)"


def _is_current_state_header(line: str) -> bool:
    return line.strip() == CURRENT_STATE_HEADER


def replace_current_state_section(content: str, section: str) -> str:
    """
    Keep exactly one CURRENT STATE section in state.md.
    Existing CURRENT STATE blocks are removed and the new section is appended.
    """
    lines = content.splitlines()
    kept: List[str] = []
    idx = 0

    while idx < len(lines):
        line = lines[idx]
        if _is_current_state_header(line):
            idx += 1
            while idx < len(lines):
                next_line = lines[idx]
                if next_line.startswith("## ") and not _is_current_state_header(next_line):
                    break
                idx += 1
            continue
        kept.append(line)
        idx += 1

    base = "\n".join(kept).rstrip()
    section_text = section.strip()

    if not section_text:
        return f"{base}\n" if base else ""
    if not base:
        return f"{section_text}\n"
    if base.endswith("---"):
        return f"{base}\n\n{section_text}\n"
    return f"{base}\n\n---\n\n{section_text}\n"


class HandoffEngine:
    """
    세션 연속성 엔진

    Features:
    - Context Restoration: state.md 읽기/쓰기
    - Work Locking: 멀티에이전트 충돌 방지
    - Filesystem Cache: 중복 생성 방지
    - Asset Registry 통합
    - Container-Aware Paths
    """

    def __init__(self):
        # Container-aware paths
        self.project_root = PROJECT_ROOT

        # 로컬 핵심 파일 (버전 관리)
        self.quanta_path = self.project_root / "knowledge" / "agent_hub" / "state.md"

        # Container 내부 파일 (작업 상태)
        self.work_lock_path = KNOWLEDGE_PATHS["system"] / "work_lock.json"
        self.fs_cache_path = KNOWLEDGE_PATHS["system"] / "filesystem_cache.json"
        self.asset_registry_path = KNOWLEDGE_PATHS["system"] / "asset_registry.json"
        self.asset_registry_lock_path = KNOWLEDGE_PATHS["system"] / "asset_registry.lock"

        # 디렉토리 생성 (Container 내부)
        self.work_lock_path.parent.mkdir(parents=True, exist_ok=True)

    # ─────────────────────────────────────────────────────────────
    # 1. Context Restoration (세션 시작/종료)
    # ─────────────────────────────────────────────────────────────

    def onboard(self) -> Dict[str, Any]:
        """
        세션 시작 시 맥락 복구

        Returns:
            Dict with current state, next tasks, warnings
        """
        print("\n" + "="*70)
        print("🔄 Session Handoff - Onboarding")
        print("="*70)

        if not self.quanta_path.exists():
            print("⚠️  state.md not found. Creating initial state...")
            return self._create_initial_quanta()

        # Read current state
        with open(self.quanta_path, 'r', encoding='utf-8') as f:
            quanta_content = f.read()

        print("\n✅ Context Restored from state.md")
        print(f"📍 File: {self.quanta_path}")
        print(f"📏 Size: {len(quanta_content)} characters")

        # Parse quanta (simple extraction)
        state = self._parse_quanta(quanta_content)

        # Check work lock
        lock_status = self.check_work_lock()
        if lock_status['locked']:
            print(f"\n⚠️  Work Lock Active: {lock_status['agent']} - {lock_status['task']}")
            print(f"   Started: {lock_status['started_at']}")
            print(f"   Expires: {lock_status['expires_at']}")

        # Update filesystem cache
        self.update_filesystem_cache()

        print("\n" + "="*70)
        print("🎯 Ready to work. Current mission loaded.")
        print("="*70 + "\n")

        return state

    def handoff(self, agent_id: str, summary: str, next_steps: List[str]) -> bool:
        """
        세션 종료 시 상태 저장

        Args:
            agent_id: 현재 에이전트 ID
            summary: 완료한 작업 요약
            next_steps: 다음 단계 목록
        """
        print("\n" + "="*70)
        print(f"💾 Session Handoff - Saving State ({agent_id})")
        print("="*70)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Update state.md
        completed_items = '\n'.join(['- ✅ ' + item for item in summary.split('\n') if item.strip()])
        next_items = '\n'.join(['- ⏳ ' + step for step in next_steps])

        update_section = (
            f"{CURRENT_STATE_HEADER}\n\n"
            f"### [{timestamp}] Session Update - {agent_id}\n\n"
            f"**완료한 작업**:\n{completed_items}\n\n"
            f"**다음 단계**:\n{next_items}\n\n"
            f"**업데이트 시간**: {datetime.now().isoformat()}"
        )

        if self.quanta_path.exists():
            current = self.quanta_path.read_text(encoding="utf-8")
            updated = replace_current_state_section(current, update_section)
            self.quanta_path.write_text(updated, encoding="utf-8")
        else:
            self.quanta_path.write_text(f"{update_section.strip()}\n", encoding="utf-8")

        # Release work lock (if held)
        self.release_work_lock(agent_id)

        print(f"✅ State saved to state.md")
        print(f"✅ Work lock released (if held by {agent_id})")

        # Generate compact report (완료/개선/다음) for every handoff call
        try:
            report_script = self.project_root / "core" / "system" / "compact_report.py"
            evidence_guard = self.project_root / "core" / "system" / "evidence_guard.py"
            if report_script.exists():
                cmd = ["python3", str(report_script), "--agent-id", agent_id, "--summary", summary, "--improvement-from-next"]
                for step in next_steps:
                    cmd.extend(["--next-step", step])
                # subprocess.run is already imported above
                out = subprocess.check_output(cmd + ["--quiet"], text=True).strip()
                if out:
                    print(f"✅ Compact report generated: {out}")
                    if evidence_guard.exists():
                        subprocess.run(
                            [
                                "python3",
                                str(evidence_guard),
                                "--append",
                                "--claim",
                                "Compact report generated (handoff)",
                                "--evidence-type",
                                "file",
                                "--source",
                                out,
                                "--detail",
                                f"agent={agent_id}",
                            ],
                            check=False,
                        )
            else:
                print("⚠️  compact_report.py not found; skipped compact report generation")
        except Exception as exc:  # non-blocking
            print(f"⚠️  Compact report generation failed: {exc}")

        print("="*70 + "\n")

        return True

    def _parse_quanta(self, content: str) -> Dict[str, Any]:
        """state.md 내용 파싱"""
        # Simple extraction (나중에 고도화 가능)
        state = {
            "content": content,
            "size": len(content),
            "last_update": "unknown"
        }

        # Extract last timestamp
        import re
        timestamps = re.findall(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]', content)
        if timestamps:
            state["last_update"] = timestamps[-1]

        return state

    def _create_initial_quanta(self) -> Dict:
        """초기 state.md 생성"""
        initial_content = f"""# 🧠 INTELLIGENCE QUANTA - 지능 앵커

> **생성**: {datetime.now().isoformat()}
> **상태**: Initial state created by handoff.py

---

{CURRENT_STATE_HEADER}

### [{datetime.now().strftime("%Y-%m-%d %H:%M")}] System Initialization

**진행률**: Phase 0 / 3 (0%)

**완료한 작업**:
- ✅ 프로젝트 구조 확인
- ✅ handoff.py 초기화

**다음 단계**:
1. Phase 1: 순환 인프라 구축
2. Phase 2: Telegram + Ralph Loop 통합
3. Phase 3: 회사 조직 체계 완성

---

> "첫 번째 기록. 지금부터 모든 세션이 연결된다." — LAYER OS
"""
        with open(self.quanta_path, 'w', encoding='utf-8') as f:
            f.write(initial_content)

        return {"status": "initialized"}

    # ─────────────────────────────────────────────────────────────
    # 2. Work Locking (멀티에이전트 충돌 방지)
    # ─────────────────────────────────────────────────────────────

    def acquire_work_lock(self, agent_id: str, task: str, resources: List[str] = None, timeout_minutes: int = 30) -> bool:
        """
        작업 잠금 획득 (멀티에이전트 충돌 방지)

        Args:
            agent_id: 에이전트 ID (e.g., "SA", "CE", "TD")
            task: 작업 설명
            resources: 잠금할 리소스 목록 (폴더, 파일 등)
            timeout_minutes: 자동 해제 시간

        Returns:
            True if lock acquired, False if locked by another agent
        """
        # Check existing lock
        lock_status = self.check_work_lock()

        if lock_status['locked'] and lock_status['agent'] != agent_id:
            print(f"⚠️  Work lock held by {lock_status['agent']}: {lock_status['task']}")
            return False

        # Acquire lock
        lock_data = {
            "locked": True,
            "agent": agent_id,
            "task": task,
            "resources": resources or [],
            "started_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(minutes=timeout_minutes)).isoformat()
        }

        with open(self.work_lock_path, 'w', encoding='utf-8') as f:
            json.dump(lock_data, f, indent=2, ensure_ascii=False)

        print(f"🔒 Work lock acquired by {agent_id}: {task}")
        return True

    def release_work_lock(self, agent_id: str) -> bool:
        """작업 잠금 해제"""
        if not self.work_lock_path.exists():
            return True

        with open(self.work_lock_path, 'r', encoding='utf-8') as f:
            lock_data = json.load(f)

        if lock_data.get('agent') == agent_id:
            self.work_lock_path.unlink()
            print(f"🔓 Work lock released by {agent_id}")
            return True

        print(f"⚠️  Cannot release lock: held by {lock_data.get('agent')}, not {agent_id}")
        return False

    def check_work_lock(self) -> Dict[str, Any]:
        """작업 잠금 상태 확인"""
        if not self.work_lock_path.exists():
            return {"locked": False}

        with open(self.work_lock_path, 'r', encoding='utf-8') as f:
            lock_data = json.load(f)

        if not lock_data.get('locked', False):
            return {"locked": False}

        # Check expiration (handle None case)
        expires_at_str = lock_data.get('expires_at')
        if not expires_at_str:
            return {"locked": False}

        expires_at = datetime.fromisoformat(expires_at_str)
        if datetime.now() > expires_at:
            print(f"⏰ Work lock expired. Auto-releasing...")
            self.work_lock_path.unlink()
            return {"locked": False}

        return lock_data

    # ─────────────────────────────────────────────────────────────
    # 3. Filesystem Cache (중복 생성 방지)
    # ─────────────────────────────────────────────────────────────

    def update_filesystem_cache(self, force: bool = False) -> Dict[str, List[str]]:
        """
        파일 시스템 캐시 갱신 (5분 주기)

        Args:
            force: 강제 갱신 (주기 무시)
        """
        # Check cache age
        if not force and self.fs_cache_path.exists():
            with open(self.fs_cache_path, 'r', encoding='utf-8') as f:
                cache = json.load(f)

            last_scan_str = cache.get('last_scan', '')
            if last_scan_str:
                # Handle 'Z' timezone format
                last_scan_str = last_scan_str.replace('Z', '+00:00')
                try:
                    last_scan = datetime.fromisoformat(last_scan_str)
                    # Make both timezone-naive for comparison
                    last_scan_naive = last_scan.replace(tzinfo=None)
                    if datetime.now() - last_scan_naive < timedelta(minutes=5):
                        return cache  # Fresh cache
                except (ValueError, AttributeError):
                    pass  # Invalid format, proceed with scan

        # Scan filesystem
        print("🔍 Scanning filesystem...")

        cache = {
            "last_scan": datetime.now().isoformat(),
            "folders": [],
            "files": []
        }

        # Scan important directories
        for pattern in ["directives/**/*", "execution/**/*", "knowledge/**/*", "system/**/*"]:
            for item in self.project_root.glob(pattern):
                try:
                    if not item.exists():  # Skip broken symlinks
                        continue

                    relative_path = str(item.relative_to(self.project_root))

                    if item.is_dir():
                        cache['folders'].append(relative_path)
                    elif item.is_file():
                        cache['files'].append(relative_path)
                except (PermissionError, OSError):
                    continue  # Skip files with permission issues

        # Save cache
        with open(self.fs_cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)

        print(f"✅ Filesystem cache updated: {len(cache['folders'])} folders, {len(cache['files'])} files")

        return cache

    def check_path_exists(self, path: str) -> bool:
        """캐시를 통해 경로 존재 확인 (실제 파일 시스템 체크 없이)"""
        if not self.fs_cache_path.exists():
            self.update_filesystem_cache()

        with open(self.fs_cache_path, 'r', encoding='utf-8') as f:
            cache = json.load(f)

        return path in cache['folders'] or path in cache['files']

    # ─────────────────────────────────────────────────────────────
    # 4. Asset Registry (자산 등록)
    # ─────────────────────────────────────────────────────────────

    @contextmanager
    def _asset_registry_lock(self):
        """Serialize registry writes across concurrent agents/processes."""
        self.asset_registry_lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.asset_registry_lock_path, 'a+', encoding='utf-8') as lock_fp:
            if fcntl is not None:
                fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)

    def _default_asset_registry(self) -> Dict[str, Any]:
        now = datetime.now().isoformat()
        return {
            "version": "2.0",
            "created_at": now,
            "last_updated": now,
            "assets": [],
            "stats": {
                "total": 0,
                "by_type": {},
                "by_status": {},
                "by_source": {},
            },
        }

    def _normalize_asset_registry(self, registry: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(registry, dict):
            registry = {}
        registry.setdefault("version", "2.0")
        registry.setdefault("created_at", datetime.now().isoformat())
        registry.setdefault("last_updated", datetime.now().isoformat())
        assets = registry.get("assets")
        if not isinstance(assets, list):
            assets = []
        registry["assets"] = assets

        stats = registry.get("stats")
        if not isinstance(stats, dict):
            stats = {}
        stats.setdefault("total", len(assets))
        stats.setdefault("by_type", {})
        stats.setdefault("by_status", {})
        stats.setdefault("by_source", {})
        registry["stats"] = stats
        return registry

    def _recompute_asset_stats(self, assets: List[Any]) -> Dict[str, Any]:
        by_type: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        by_source: Dict[str, int] = {}
        total = 0

        for item in assets:
            if not isinstance(item, dict):
                continue
            total += 1
            asset_type = str(item.get("type", "") or "")
            status = str(item.get("status", "") or "")
            source = str(item.get("source", "") or "")
            if asset_type:
                by_type[asset_type] = by_type.get(asset_type, 0) + 1
            if status:
                by_status[status] = by_status.get(status, 0) + 1
            if source:
                by_source[source] = by_source.get(source, 0) + 1

        return {
            "total": total,
            "by_type": by_type,
            "by_status": by_status,
            "by_source": by_source,
        }

    def _load_asset_registry(self) -> tuple[Dict[str, Any], bool]:
        """
        Returns (registry, recovered)
        recovered=True when malformed trailing data was stripped.
        """
        if not self.asset_registry_path.exists():
            return self._default_asset_registry(), False

        text = self.asset_registry_path.read_text(encoding='utf-8', errors='ignore').strip()
        if not text:
            return self._default_asset_registry(), False

        try:
            payload = json.loads(text)
            return self._normalize_asset_registry(payload), False
        except json.JSONDecodeError:
            # Recover first JSON object when file has trailing garbage/partial writes.
            decoder = json.JSONDecoder()
            payload, _ = decoder.raw_decode(text)
            if not isinstance(payload, dict):
                return self._default_asset_registry(), True
            return self._normalize_asset_registry(payload), True

    def _save_asset_registry(self, registry: Dict[str, Any]) -> None:
        registry = self._normalize_asset_registry(registry)
        registry["last_updated"] = datetime.now().isoformat(timespec="seconds")
        tmp_path = self.asset_registry_path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(self.asset_registry_path)

    def _next_asset_id(self, registry: Dict[str, Any]) -> str:
        month = datetime.now().strftime("%Y-%m")
        max_seq = 0
        for asset in registry.get("assets", []):
            if not isinstance(asset, dict):
                continue
            raw_id = str(asset.get("id", ""))
            match = re.match(rf"^AST-{re.escape(month)}-(\d+)$", raw_id)
            if not match:
                continue
            seq = int(match.group(1))
            if seq > max_seq:
                max_seq = seq
        total = int(registry.get("stats", {}).get("total", 0))
        next_seq = max(max_seq, total) + 1
        return f"AST-{month}-{next_seq:03d}"

    def repair_asset_registry(self) -> bool:
        """Repair malformed asset_registry.json by loading and rewriting normalized JSON."""
        with self._asset_registry_lock():
            registry, recovered = self._load_asset_registry()
            registry["stats"] = self._recompute_asset_stats(registry.get("assets", []))
            self._save_asset_registry(registry)
        if recovered:
            print("✅ Asset registry repaired (recovered malformed trailing data)")
        else:
            print("✅ Asset registry validated (no recovery needed)")
        return True

    def register_asset(self, path: str, asset_type: str, source: str, metadata: Dict = None) -> str:
        """
        생성된 자산 등록

        Args:
            path: 파일 경로
            asset_type: insight, content, visual, code, report
            source: telegram, clipboard, file, agent
            metadata: 추가 메타데이터

        Returns:
            asset_id (e.g., AST-2026-02-001)
        """
        with self._asset_registry_lock():
            registry, recovered = self._load_asset_registry()

            asset_id = self._next_asset_id(registry)
            now = datetime.now().isoformat()

            asset = {
                "id": asset_id,
                "type": asset_type,
                "source": source,
                "created_at": now,
                "path": path,
                "status": "captured",
                "metadata": metadata or {},
                "lifecycle": [
                    {
                        "stage": "captured",
                        "at": now,
                        "by": source
                    }
                ]
            }

            registry["assets"].append(asset)
            registry["stats"] = self._recompute_asset_stats(registry.get("assets", []))
            self._save_asset_registry(registry)

        if recovered:
            print("⚠️  Asset registry had malformed trailing data; auto-recovered before append")
        print(f"📦 Asset registered: {asset_id} ({asset_type})")
        return asset_id


# ─────────────────────────────────────────────────────────────────
# CLI Interface
# ─────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="LAYER OS Session Handoff Engine")
    parser.add_argument('--onboard', action='store_true', help='세션 시작 (맥락 복구)')
    parser.add_argument('--handoff', action='store_true', help='세션 종료 (상태 저장)')
    parser.add_argument('--agent-id', type=str, default='Unknown', help='에이전트 ID')
    parser.add_argument('--summary', type=str, help='작업 요약 (handoff 시)')
    parser.add_argument('--next-steps', type=str, nargs='+', help='다음 단계 (handoff 시)')
    parser.add_argument('--update-cache', action='store_true', help='파일 시스템 캐시 갱신')
    parser.add_argument('--register-asset', nargs=3, metavar=('PATH', 'TYPE', 'SOURCE'), help='자산 등록')
    parser.add_argument('--repair-asset-registry', action='store_true', help='asset_registry.json 복구/정규화')
    parser.add_argument('--test', action='store_true', help='테스트 모드')

    args = parser.parse_args()

    engine = HandoffEngine()

    if args.test:
        print("🧪 Running tests...")
        print("\n1. Onboard test:")
        state = engine.onboard()

        print("\n2. Work lock test:")
        engine.acquire_work_lock("TEST_AGENT", "Test task")
        engine.check_work_lock()
        engine.release_work_lock("TEST_AGENT")

        print("\n3. Filesystem cache test:")
        cache = engine.update_filesystem_cache(force=True)
        print(f"   Cached {len(cache['folders'])} folders, {len(cache['files'])} files")

        print("\n4. Asset registration test:")
        asset_id = engine.register_asset("test.md", "insight", "test")
        print(f"   Created: {asset_id}")

        print("\n✅ All tests passed!")

    elif args.onboard:
        engine.onboard()

    elif args.handoff:
        summary = args.summary or "No summary provided"
        next_steps = args.next_steps or ["Continue work"]
        engine.handoff(args.agent_id, summary, next_steps)

    elif args.update_cache:
        engine.update_filesystem_cache(force=True)

    elif args.register_asset:
        path, asset_type, source = args.register_asset
        engine.register_asset(path, asset_type, source)

    elif args.repair_asset_registry:
        engine.repair_asset_registry()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
