"""Circuit adapter — Intern 3's domain.

An RC low-pass charging from a step has an exact closed-form solution, so a real
SPICE run can be scored against maths instead of another simulator. The headline
number is the worst deviation anywhere (L-infinity error); it passes under 1% of
the input voltage.

    DUT     ngspice transient analysis
    golden  v(t) = Vin * (1 - exp(-t / RC))
"""
from __future__ import annotations

import json

from ..adapter import Adapter
from ..record import Metric
from ._common import last_json, python_bin, script


class PhysicsAdapter(Adapter):
    type = "physics"

    def build_command(self, config: dict) -> list:
        case = {k: v for k, v in config.items() if k != "source_sha"}
        return [python_bin(), script("rc_circuit.py"), json.dumps(case)]

    def parse_result(self, exit_code, stdout, artifacts_dir, config):
        name = config.get("name", "case")
        source_sha = config.get("source_sha", "")
        cfg = {"name": name, "r": config.get("r"), "c": config.get("c")}
        data = last_json(stdout)

        if data is None or "linf_error" not in data:
            err = (data or {}).get("error", "experiment produced no result")
            return self.record(
                status="error", metric=Metric("linf_error", 0, "V"),
                reason_code="no_result", detail=f"{name}: {err}",
                config=cfg, source_sha=source_sha, inputs=name)

        ok = bool(data.get("ok"))
        linf = float(data["linf_error"])
        return self.record(
            status="pass" if ok else "fail",
            metric=Metric("linf_error", linf, "V"),
            reason_code="within_tolerance" if ok else "exceeds_tolerance",
            detail=(f"{name}: SPICE matches the closed-form within {linf:.2e} V "
                    f"over {data.get('samples')} samples" if ok else
                    f"{name}: SPICE deviates from the closed-form by {linf:.2e} V "
                    f"(tolerance {data.get('tolerance')})"),
            metrics={"tolerance": data.get("tolerance"), "tau_s": data.get("tau_s"),
                     "samples": data.get("samples")},
            config=cfg, source_sha=source_sha, inputs=name)
