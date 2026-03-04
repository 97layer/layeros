#!/usr/bin/env python3
"""
live_ui_monitor.py

Screenshot-free live UI monitor using playwright-cli session eval.
It checks layout contracts and reports only changes or violations.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple


MONITOR_TAG = "MONITOR_JSON:"


def default_pwcli() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    return codex_home / "skills" / "playwright" / "scripts" / "playwright_cli.sh"


def run_cmd(cmd: List[str], timeout: float = 45.0) -> str:
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    if proc.returncode != 0:
        raise RuntimeError(out.strip()[-500:] or f"command failed: {' '.join(cmd)}")
    return out


def run_pw(pwcli: Path, args: List[str], timeout: float = 45.0) -> str:
    if not pwcli.exists():
        raise RuntimeError(f"pwcli not found: {pwcli}")
    return run_cmd([str(pwcli), *args], timeout=timeout)


def extract_payload(text: str) -> Dict:
    for line in text.splitlines():
        if MONITOR_TAG not in line:
            continue

        raw = line.strip()
        if raw.startswith('"') and raw.endswith('"'):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                pass

        idx = raw.find(MONITOR_TAG)
        if idx < 0:
            continue
        payload_text = raw[idx + len(MONITOR_TAG) :].strip()
        try:
            return json.loads(payload_text)
        except json.JSONDecodeError:
            continue

    tail = text.strip()[-500:]
    raise RuntimeError(f"monitor payload not found in output: {tail}")


def monitor_eval_script() -> str:
    return """
() => {
  const px = (v) => {
    const n = parseFloat(v || "0");
    return Number.isFinite(n) ? n : 0;
  };
  const style = (el) => (el ? getComputedStyle(el) : null);
  const html = document.documentElement;
  const nav = document.getElementById("site-nav");
  const footer = document.querySelector(".site-footer");
  const filter = document.getElementById("archive-type-filter");
  const row = document.querySelector(".archive-filter__item");
  const firstBtn = document.querySelector(".archive-filter__item .archive-filter__btn");
  const search = document.getElementById("archive-search");

  const fs = style(filter);
  const rs = style(row);
  const bs = style(firstBtn);
  const ss = style(search);

  const payload = {
    route: location.pathname + location.search,
    innerWidth: window.innerWidth,
    scrollWidth: html.scrollWidth,
    overflowX: html.scrollWidth > window.innerWidth,
    markers: {
      nav: !!nav,
      footer: !!footer,
      hasArchiveFilter: !!filter,
      hasArchiveSearch: !!search,
    },
    archive: filter ? {
      container: {
        marginTop: px(fs.marginTop),
        paddingTop: px(fs.paddingTop),
        paddingBottom: px(fs.paddingBottom),
        minHeight: px(fs.minHeight),
        textTransform: fs.textTransform,
        letterSpacing: fs.letterSpacing,
      },
      row: row ? {
        justifyContent: rs.justifyContent,
        borderBottomWidth: px(rs.borderBottomWidth),
      } : null,
      firstButton: firstBtn ? {
        width: px(bs.width),
        borderBottomWidth: px(bs.borderBottomWidth),
      } : null,
      search: search ? {
        width: px(ss.width),
        borderBottomWidth: px(ss.borderBottomWidth),
        fontSize: px(ss.fontSize),
        letterSpacing: ss.letterSpacing,
      } : null,
    } : null,
  };

  return "%s" + JSON.stringify(payload);
}
""" % MONITOR_TAG


def parse_csv_ints(raw: str) -> List[int]:
    values = []
    for token in raw.split(","):
        token = token.strip()
        if token:
            values.append(int(token))
    return values


def parse_csv_urls(raw: str) -> List[str]:
    urls = []
    for token in raw.split(","):
        token = token.strip()
        if token:
            urls.append(token)
    return urls


def build_violations(payload: Dict) -> List[str]:
    issues: List[str] = []

    if payload.get("overflowX"):
        issues.append("overflow-x")

    markers = payload.get("markers", {})
    if not markers.get("nav"):
        issues.append("missing-nav")
    if not markers.get("footer"):
        issues.append("missing-footer")

    archive = payload.get("archive")
    if archive:
        c = archive.get("container") or {}
        r = archive.get("row") or {}
        b = archive.get("firstButton") or {}
        s = archive.get("search") or {}

        if c.get("marginTop", 0) > 0.5:
            issues.append(f"archive.marginTop={c.get('marginTop')}")
        if c.get("paddingTop", 0) > 0.5 or c.get("paddingBottom", 0) > 0.5:
            issues.append("archive.padding-not-zero")
        if c.get("minHeight", 0) > 0.5:
            issues.append(f"archive.minHeight={c.get('minHeight')}")
        if str(c.get("textTransform", "")).lower() != "none":
            issues.append("archive.textTransform!=none")
        if r and r.get("justifyContent") != "space-between":
            issues.append(f"archive.row.justify={r.get('justifyContent')}")
        if b and b.get("borderBottomWidth", 0) > 0.5:
            issues.append("archive.btn.borderBottom")
        if s and s.get("borderBottomWidth", 0) > 0.5:
            issues.append("archive.search.borderBottom")

    return issues


def digest(payload: Dict, issues: List[str]) -> str:
    compact = {
        "route": payload.get("route"),
        "innerWidth": payload.get("innerWidth"),
        "scrollWidth": payload.get("scrollWidth"),
        "overflowX": payload.get("overflowX"),
        "markers": payload.get("markers"),
        "archive": payload.get("archive"),
        "issues": issues,
    }
    return json.dumps(compact, sort_keys=True, ensure_ascii=True)


def line_for_payload(payload: Dict, issues: List[str]) -> str:
    status = "FAIL" if issues else "OK"
    route = payload.get("route", "?")
    vw = payload.get("innerWidth", "?")
    sw = payload.get("scrollWidth", "?")
    markers = payload.get("markers", {})
    head = (
        f"[{status}] vw={vw} sw={sw} route={route} "
        f"nav={'Y' if markers.get('nav') else 'N'} "
        f"footer={'Y' if markers.get('footer') else 'N'}"
    )
    if issues:
        return f"{head} issues={','.join(issues)}"
    return head


def cycle_monitor(
    pwcli: Path,
    session: str,
    urls: List[str],
    widths: List[int],
    height: int,
) -> Dict[Tuple[str, int], Tuple[Dict, List[str]]]:
    results: Dict[Tuple[str, int], Tuple[Dict, List[str]]] = {}
    script = monitor_eval_script()

    for url in urls:
        run_pw(pwcli, ["--session", session, "goto", url], timeout=60.0)
        for width in widths:
            run_pw(pwcli, ["--session", session, "resize", str(width), str(height)])
            output = run_pw(pwcli, ["--session", session, "eval", script], timeout=60.0)
            payload = extract_payload(output)
            issues = build_violations(payload)
            results[(url, width)] = (payload, issues)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Screenshot-free live UI monitor")
    parser.add_argument("--session", default="uiwatch", help="playwright-cli session name")
    parser.add_argument(
        "--urls",
        default="http://localhost:9700/archive/",
        help="comma-separated URLs to monitor",
    )
    parser.add_argument(
        "--widths",
        default="390,768,1440",
        help="comma-separated viewport widths",
    )
    parser.add_argument("--height", type=int, default=900, help="viewport height")
    parser.add_argument("--interval", type=float, default=2.0, help="poll interval seconds")
    parser.add_argument("--once", action="store_true", help="run one cycle and exit")
    parser.add_argument("--headed", action="store_true", help="open headed browser")
    parser.add_argument(
        "--always-print",
        action="store_true",
        help="print every cycle, not only changes/failures",
    )
    parser.add_argument(
        "--close-on-exit",
        action="store_true",
        help="close playwright session when monitor exits",
    )
    parser.add_argument(
        "--pwcli",
        default=str(default_pwcli()),
        help="path to playwright_cli.sh wrapper",
    )
    args = parser.parse_args()

    pwcli = Path(args.pwcli).expanduser().resolve()
    urls = parse_csv_urls(args.urls)
    widths = parse_csv_ints(args.widths)
    if not urls:
        raise RuntimeError("at least one URL is required")
    if not widths:
        raise RuntimeError("at least one viewport width is required")

    # Prereq from playwright skill.
    run_cmd(["/bin/zsh", "-lc", "command -v npx >/dev/null 2>&1"])

    open_args = ["open", urls[0], "--session", args.session]
    if args.headed:
        open_args.append("--headed")
    run_pw(pwcli, open_args, timeout=60.0)

    previous: Dict[Tuple[str, int], str] = {}
    print(
        f"[MONITOR] session={args.session} urls={len(urls)} widths={widths} interval={args.interval}s",
        flush=True,
    )
    print("[MONITOR] stop with Ctrl+C", flush=True)

    try:
        while True:
            cycle = cycle_monitor(
                pwcli=pwcli,
                session=args.session,
                urls=urls,
                widths=widths,
                height=args.height,
            )
            for key, (payload, issues) in cycle.items():
                sig = digest(payload, issues)
                changed = previous.get(key) != sig
                if changed or issues or args.always_print:
                    print(line_for_payload(payload, issues), flush=True)
                previous[key] = sig

            if args.once:
                break
            time.sleep(max(0.3, args.interval))
    finally:
        if args.close_on_exit:
            try:
                run_pw(pwcli, ["--session", args.session, "close"], timeout=30.0)
            except Exception:
                pass

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"[MONITOR:ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
