#!/usr/bin/env python3
"""Run a complete cosim demo and feed the dashboard.

This is the small "full loop" demo:

1. Inject one selected DINO bug.
2. Run DINO-vs-Spike cosim on a targeted test.
3. Restore the CPU source.
4. Copy the generated mutation JSON into the dashboard examples folder.

After this script finishes, open the CPU dashboard and click "Load sample data"
to view the same result the cosim just produced.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
COSIM = ROOT / "cosim"
CAMPAIGN_INDEX = COSIM / "build" / "campaigns" / "mutation_campaign_index.json"
DASHBOARD_EXAMPLES = COSIM / "CPU-Dashboard" / "examples"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run mutation cosim and refresh dashboard sample JSON.")
    parser.add_argument("--function", default="and", help="Bug target, e.g. and, addi, sub, branch.")
    parser.add_argument("--tests", default=str(COSIM / "mutation" / "smoke_tests"))
    parser.add_argument("--steps", default=os.environ.get("STEPS", "12"))
    parser.add_argument("--jobs", default=os.environ.get("JOBS", "4"))
    args = parser.parse_args()

    env = os.environ.copy()
    env["STEPS"] = str(args.steps)
    env["JOBS"] = str(args.jobs)

    command = [
        sys.executable,
        str(COSIM / "mutation" / "run_mutation_campaign.py"),
        args.tests,
        "--function",
        args.function,
    ]
    result = subprocess.run(command, cwd=ROOT, env=env)
    if result.returncode not in (0, 1):
        return result.returncode

    with CAMPAIGN_INDEX.open(encoding="utf-8") as f:
        index = json.load(f)
    runs = index.get("runs", [])
    if not runs:
        raise SystemExit(f"No runs found in {CAMPAIGN_INDEX}")

    run_json = Path(runs[-1]["jsonPath"])
    if not run_json.exists():
        raise SystemExit(f"Generated run JSON not found: {run_json}")

    DASHBOARD_EXAMPLES.mkdir(parents=True, exist_ok=True)
    dashboard_json = DASHBOARD_EXAMPLES / "run_mutation.json"
    shutil.copyfile(run_json, dashboard_json)

    print("[full-loop] mutation JSON:", run_json)
    print("[full-loop] dashboard sample:", dashboard_json)
    print("[full-loop] next: cd cosim/CPU-Dashboard && npm install && npm run dev")
    print("[full-loop] then click Load sample data in the dashboard")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
