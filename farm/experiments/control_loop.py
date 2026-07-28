#!/usr/bin/env python3
"""One PID control-loop experiment: your controller vs a step-response spec.

Intern 1's domain. A PID controller steers a plant toward a setpoint (think cruise
control). We drive the plant with your controller and judge the resulting step
response against a 2nd-order performance spec — the way a control engineer actually
grades a controller:

    DUT     your controller (Python or C, any common interface — see loader.py)
    golden  a step-response spec: small steady-state error, bounded overshoot,
            settles in time

Judging on the response (not on matching one exact ideal curve) is what lets real
controllers with filtered derivatives, anti-windup and limits pass fairly, while a
genuinely broken controller (no integral, wrong sign) fails. The headline number is
overshoot.

    python control_loop.py '{"name":"mine","controller":"path/to/pid.py","kp":2,"ki":1,"kd":0.5}'
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import control

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from farm.experiments.controllers.loader import build_adapter  # noqa: E402

REFERENCE = "farm/experiments/controllers/pid_reference.py"


def simulate(adapter, plant_num, plant_den, t, setpoint=1.0):
    """Closed loop: plant driven by the controller, unit-step setpoint."""
    ss = control.tf2ss(control.tf(plant_num, plant_den))
    A, B, C = np.asarray(ss.A), np.asarray(ss.B), np.asarray(ss.C)
    x = np.zeros((A.shape[0], 1))
    out = np.zeros(len(t))
    dt = float(t[1] - t[0])
    for i in range(len(t)):
        y = float(np.ravel(C @ x)[0])
        out[i] = y
        u = adapter.output(setpoint, y, dt)
        f = lambda xx: A @ xx + B * u  # noqa: E731
        k1 = f(x); k2 = f(x + dt / 2 * k1); k3 = f(x + dt / 2 * k2); k4 = f(x + dt * k3)
        x = x + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
    return out


def evaluate(y, t, setpoint, spec):
    y = np.asarray(y)
    if not np.all(np.isfinite(y)) or float(np.max(np.abs(y))) > 50:
        return {"ok": False, "reason": "unstable (diverged)",
                "overshoot_pct": float("inf"), "ss_error": float("inf"), "settling_s": None}
    tail = y[max(1, int(len(y) * 0.95)):]
    ss_error = float(abs(setpoint - np.mean(tail)))
    overshoot = max(0.0, (float(np.max(y)) - setpoint) / setpoint)
    band = spec["settle_band"] * setpoint
    outside = np.where(np.abs(y - setpoint) > band)[0]
    settling = float(t[outside[-1]]) if len(outside) else 0.0

    checks = []
    if ss_error >= spec["ss_tol"]:
        checks.append("steady-state error")
    if overshoot >= spec["overshoot_max"]:
        checks.append("overshoot too high")
    if settling >= spec["settle_max"]:
        checks.append("doesn't settle in time")
    return {"ok": not checks, "reason": "meets step-response spec" if not checks else ", ".join(checks),
            "overshoot_pct": overshoot * 100, "ss_error": ss_error, "settling_s": settling}


def main() -> int:
    cfg = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    kp = float(cfg.get("kp", 2.0))
    ki = float(cfg.get("ki", 1.0))
    kd = float(cfg.get("kd", 0.5))
    plant_num = cfg.get("plant_num", [1.0])
    plant_den = cfg.get("plant_den", [1.0, 2.0, 1.0])
    t_end = float(cfg.get("t_end", 12.0))
    n = int(cfg.get("points", 4000))
    controller_path = cfg.get("controller") or REFERENCE

    spec = {
        "ss_tol": float(cfg.get("ss_tol", 0.05)),         # within 5% of setpoint
        "overshoot_max": float(cfg.get("overshoot_max", 0.6)),  # under 60%
        "settle_max": float(cfg.get("settle_max", 0.9 * t_end)),
        "settle_band": float(cfg.get("settle_band", 0.02)),      # +/- 2% band
    }

    t = np.linspace(0, t_end, n)
    dt = float(t[1] - t[0])
    try:
        adapter = build_adapter(controller_path, kp, ki, kd, dt)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": f"could not load controller '{controller_path}': {exc}"}))
        return 3

    try:
        y = simulate(adapter, plant_num, plant_den, t)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"error": f"controller crashed while running: {exc}"}))
        return 3

    r = evaluate(y, t, 1.0, spec)
    r.update({"controller": getattr(adapter, "kind", "controller"),
              "points": n, "gains": {"kp": kp, "ki": ki, "kd": kd}})
    print(json.dumps(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
