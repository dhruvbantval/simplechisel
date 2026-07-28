#!/usr/bin/env python3
"""Run one experiment's campaign, driven entirely by farm.yaml.

    farm/.venv/bin/python farm/run_experiment.py control
    farm/.venv/bin/python farm/run_experiment.py --list

It looks the experiment up in farm.yaml, picks the matching adapter, expands the
case list, runs each case through the adapter, and writes the results into the
shared record store — so every domain lands on the same dashboard and the same
regression trend.

This is deliberately generic: it has no idea what a PID, an ECG or a circuit is.
That knowledge lives in the adapter and the config.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # so `import farm` works from anywhere

from farm.adapters import ADAPTERS          # noqa: E402
from farm.config import cases_for, experiment, experiments, load_config  # noqa: E402
from farm.runner import run_experiments     # noqa: E402
from farm.store import RecordStore          # noqa: E402

STORE = RecordStore(HERE / "build" / "records")


def version_of(exp: dict) -> str:
    """A version fingerprint for the thing under test, so the regression trend has
    something to key on. Domains that name a tool report that tool's version."""
    tool = (exp.get("system") or [None])[0]
    if tool:
        try:
            import re
            out = subprocess.run([tool, "--version"], capture_output=True, text=True)
            text = out.stdout or out.stderr
            # scan all lines: tools print the version on line 1 (clang) or later
            # (ngspice: "** ngspice-46 : ...")
            m = re.search(rf"{re.escape(tool)}[- ]v?(\d+(?:\.\d+)*)", text, re.I) \
                or re.search(r"version (\d+(?:\.\d+)*)", text, re.I) \
                or re.search(r"(\d+\.\d+(?:\.\d+)*)", text)
            return f"{tool}-{m.group(1)}" if m else f"{tool}-unknown"
        except OSError:
            pass
    # otherwise the repo commit (the code under test is ours)
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             cwd=str(HERE.parent), capture_output=True, text=True)
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("type", nargs="?", help="experiment type from farm.yaml")
    ap.add_argument("--list", action="store_true", help="list configured experiments")
    ap.add_argument("--all", action="store_true",
                    help="run every experiment that has cases (skips UI-driven ones like cosim)")
    args = ap.parse_args()

    config = load_config()

    if args.list:
        print("configured experiments (farm.yaml):")
        for e in experiments(config):
            n = len(cases_for(e))
            print(f"  {e['type']:<14} {e.get('label','')}"
                  f"  [{e.get('dut','?')} vs {e.get('golden','?')}]"
                  + (f"  {n} case(s)" if n else "  (own UI)"))
        return 0

    # Which experiments to run: one named, or every config-driven one with --all.
    if args.all:
        targets = [e["type"] for e in experiments(config) if cases_for(e)]
        if not targets:
            print("no experiments with cases in farm.yaml", file=sys.stderr)
            return 2
        print(f"[all] running {len(targets)} experiment(s): {', '.join(targets)}\n")
    elif args.type:
        targets = [args.type]
    else:
        ap.print_help()
        return 0

    overall = []
    for t in targets:
        exp = experiment(t, config)
        adapter = ADAPTERS.get(t)
        if not exp or not adapter:
            print(f"[{t}] no experiment/adapter — skipping", file=sys.stderr)
            continue
        cases = cases_for(exp)
        if not cases:
            print(f"[{t}] no cases (UI-driven, like cosim) — skipping", file=sys.stderr)
            continue

        source_sha = version_of(exp)
        print(f"[{t}] {len(cases)} case(s) — {exp.get('dut')} vs {exp.get('golden')}  @ {source_sha}")
        records = run_experiments(adapter, cases, STORE, source_sha=source_sha,
                                  on_log=lambda line: print("  " + line))
        passed = sum(1 for r in records if r.status == "pass")
        errored = sum(1 for r in records if r.status == "error")
        overall.append((t, passed, len(records), errored))
        print(f"[{t}] {passed}/{len(records)} passed"
              + (f", {errored} errored" if errored else "") + "\n")

    if args.all:
        print("=== campaign summary ===")
        for t, p, n, e in overall:
            print(f"  {t:<14} {p}/{n} passed" + (f"  ({e} errored)" if e else ""))
        tp = sum(p for _, p, _, _ in overall)
        tn = sum(n for _, _, n, _ in overall)
        print(f"  {'TOTAL':<14} {tp}/{tn} passed across {len(overall)} domain(s)")
    print("records stored -> see the Trend view for a line per domain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
