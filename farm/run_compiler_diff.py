#!/usr/bin/env python3
"""Run the compiler-diff experiment over the C corpus and store the records.

This is the second domain's "run campaign". It writes to the same record store the
cosim runs use, so the dashboard's regression trend picks it up as a second line
with no changes:

    python3 farm/run_compiler_diff.py
    CC=clang python3 farm/run_compiler_diff.py

The CPU cosim proved a domain can plug in; this proves a *different* domain
(software, not hardware) plugs into the identical machinery.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # so `import farm` works from anywhere

from farm.adapters import CompilerDiffAdapter  # noqa: E402
from farm.store import RecordStore             # noqa: E402

CORPUS = HERE / "adapters" / "corpus" / "compiler"
STORE = RecordStore(HERE / "build" / "records")


def compiler_version(cc: str) -> str:
    """A version fingerprint for the compiler under test — the trend keys on it, so
    a different compiler version would be a different point on the line."""
    try:
        out = subprocess.run([cc, "--version"], capture_output=True, text=True)
        m = re.search(r"version (\d+\.\d+\.\d+)", out.stdout)
        ver = m.group(1) if m else "unknown"
    except OSError:
        ver = "unknown"
    base = "clang" if "clang" in (out.stdout.lower() if 'out' in dir() else cc) else cc
    return f"{base}-{ver}"


def main() -> int:
    cc = os.environ.get("CC", "clang")
    programs = sorted(CORPUS.glob("*.c"))
    if not programs:
        print(f"no C programs in {CORPUS}", file=sys.stderr)
        return 2

    adapter = CompilerDiffAdapter()
    source_sha = compiler_version(cc)
    configs = [{"program": str(p), "cc": cc} for p in programs]

    print(f"[compiler-diff] {len(configs)} program(s) at -O0 vs -O2 on {source_sha}")
    from farm.runner import run_experiments
    records = run_experiments(adapter, configs, STORE, source_sha=source_sha,
                              on_log=lambda line: print("  " + line))

    passed = sum(1 for r in records if r.status == "pass")
    print(f"[compiler-diff] {passed}/{len(records)} programs agree between -O0 and -O2")
    print(f"[compiler-diff] records stored -> shows as a '{adapter.type}' line on the Trend view")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
