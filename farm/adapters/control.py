"""Control-loop adapter — Intern 1's domain.

Runs a PID controller (yours, or the reference) around a plant and checks its
closed-loop response against a validated reference PID through the same harness —
differential testing, like DINO-vs-Spike. The headline number is overshoot (how
far past the target it swings); pass/fail is whether the response matches.

    DUT     the controller named in the case (config: controller=<your.py>)
    golden  a validated reference PID driving the same plant
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..adapter import Adapter
from ..record import Metric
from ._common import last_json, python_bin, script

ROOT = Path(__file__).resolve().parents[2]


class ControlAdapter(Adapter):
    type = "control"

    def build_command(self, config: dict) -> list:
        case = {k: v for k, v in config.items() if k != "source_sha"}
        return [python_bin(), script("control_loop.py"), json.dumps(case)]

    def parse_result(self, exit_code, stdout, artifacts_dir, config):
        name = config.get("name", "case")
        source_sha = config.get("source_sha", "")
        controller = config.get("controller")
        cfg = {"name": name, "kp": config.get("kp"), "ki": config.get("ki"),
               "kd": config.get("kd"), "controller": controller}
        # fingerprint the controller file so different controllers get distinct ids
        fp = name
        if controller:
            f = (ROOT / controller) if not Path(controller).is_absolute() else Path(controller)
            if f.is_file():
                fp = f"{name}:{hashlib.sha256(f.read_bytes()).hexdigest()[:12]}"
        data = last_json(stdout)

        if data is None or ("overshoot_pct" not in data and "error" not in (data or {})):
            return self.record(
                status="error", metric=Metric("overshoot", 0, "%"),
                reason_code="no_result", detail=f"{name}: experiment produced no result",
                config=cfg, source_sha=source_sha, inputs=fp)
        if "error" in data:  # couldn't load/run the controller
            return self.record(
                status="error", metric=Metric("overshoot", 0, "%"),
                reason_code="load_error", detail=f"{name}: {data['error']}",
                config=cfg, source_sha=source_sha, inputs=fp)

        ok = bool(data.get("ok"))
        overshoot = float(data.get("overshoot_pct", 0.0))
        reason = data.get("reason", "")
        which = data.get("controller", "controller")
        os_txt = "∞" if overshoot == float("inf") else f"{overshoot:.1f}%"
        return self.record(
            status="pass" if ok else "fail",
            metric=Metric("overshoot", 0 if overshoot == float("inf") else round(overshoot, 3), "%"),
            reason_code="within_spec" if ok else "out_of_spec",
            detail=(f"{name} [{which}]: {reason} (overshoot {os_txt}, "
                    f"steady-state error {float(data.get('ss_error', 0)):.3f})"),
            metrics={"ss_error": data.get("ss_error"), "settling_s": data.get("settling_s"),
                     "points": data.get("points")},
            config=cfg, source_sha=source_sha, inputs=fp)
