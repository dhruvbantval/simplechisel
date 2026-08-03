#!/usr/bin/env python3
"""Generate PID gain sets for the control experiment. Prints a JSON list of cases.

Candidate gains are sampled at random, then screened against the reference
controller: only gains the reference already satisfies are emitted. Random gains
are not all good tuning — plenty overshoot or never settle — and a case the
reference itself cannot meet says nothing about the controller under test.
Screening keeps the same contract as the other generators: every emitted case is
one a correct controller passes, so a later failure is a regression.

    python control_gen.py 5
"""
import json
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from farm.experiments.control_loop import evaluate, simulate  # noqa: E402
from farm.experiments.controllers.loader import build_adapter  # noqa: E402

REF = "farm/experiments/controllers/pid_reference.py"

# Must match control_loop.py's defaults, or screening judges a different problem
# than the experiment does.
PLANT_NUM = [1.0]
PLANT_DEN = [1.0, 2.0, 1.0]
T_END = 12.0
POINTS = 4000
SPEC = {"ss_tol": 0.05, "overshoot_max": 0.6,
        "settle_max": 0.9 * T_END, "settle_band": 0.02}

MAX_ATTEMPTS_PER_CASE = 40


def meets_spec(kp, ki, kd, t, dt):
    """True when the reference controller satisfies the spec at these gains."""
    try:
        adapter = build_adapter(str(ROOT / REF), kp, ki, kd, dt)
        y = simulate(adapter, PLANT_NUM, PLANT_DEN, t)
    except Exception:  # noqa: BLE001 - a crash means these gains are unusable
        return False
    return bool(evaluate(y, t, 1.0, SPEC)["ok"])


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    t = np.linspace(0, T_END, POINTS)
    dt = float(t[1] - t[0])

    cases = []
    attempts = 0
    while len(cases) < n and attempts < n * MAX_ATTEMPTS_PER_CASE:
        attempts += 1
        kp = round(random.uniform(0.5, 6.0), 2)
        ki = round(random.uniform(0.2, 3.0), 2)
        kd = round(random.uniform(0.0, 1.5), 2)
        if not meets_spec(kp, ki, kd, t, dt):
            continue
        cases.append({"name": f"gen kp={kp} ki={ki} kd={kd}",
                      "controller": REF, "kp": kp, "ki": ki, "kd": kd})

    print(json.dumps(cases))


if __name__ == "__main__":
    main()
