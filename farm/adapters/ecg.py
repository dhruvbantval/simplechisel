"""ECG adapter — Intern 2's domain.

A heartbeat detector scored against cardiologists' beat annotations from the
MIT-BIH Arrhythmia Database. The headline number is sensitivity: of the beats the
experts marked, what fraction did the detector find.

    DUT     NeuroKit2's R-peak detector
    golden  the cardiologists' .atr annotations

The dataset is not committed; fetch it once with adapters/ecg_fetch.py.
"""
from __future__ import annotations

import json

from ..adapter import Adapter
from ..record import Metric
from ._common import last_json, python_bin, script


class EcgAdapter(Adapter):
    type = "ecg"

    def build_command(self, config: dict) -> list:
        case = {k: v for k, v in config.items() if k != "source_sha"}
        return [python_bin(), script("ecg_detect.py"), json.dumps(case)]

    def parse_result(self, exit_code, stdout, artifacts_dir, config):
        record_id = str(config.get("record", "?"))
        name = config.get("name", f"record {record_id}")
        source_sha = config.get("source_sha", "")
        cfg = {"name": name, "record": record_id, "seconds": config.get("seconds")}
        data = last_json(stdout)

        if data is None or "sensitivity" not in data:
            err = (data or {}).get("error", "experiment produced no result")
            return self.record(
                status="error", metric=Metric("sensitivity", 0, "fraction"),
                reason_code="no_data" if "not found" in str(err) else "no_result",
                detail=f"{name}: {err}",
                config=cfg, source_sha=source_sha, inputs=name)

        ok = bool(data.get("ok"))
        sens = float(data["sensitivity"])
        ppv = float(data.get("ppv", 0.0))
        return self.record(
            status="pass" if ok else "fail",
            metric=Metric("sensitivity", round(sens, 4), "fraction"),
            reason_code="match" if ok else "low_sensitivity",
            detail=(f"{name}: found {data.get('tp')}/{data.get('true_beats')} "
                    f"expert-marked beats (sensitivity {sens:.1%}, PPV {ppv:.1%})"),
            metrics={"ppv": ppv, "tp": data.get("tp"), "fp": data.get("fp"),
                     "fn": data.get("fn"), "true_beats": data.get("true_beats"),
                     "min_sensitivity": data.get("min_sensitivity")},
            config=cfg, source_sha=source_sha, inputs=name)
