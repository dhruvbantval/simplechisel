"""The universal experiment record — the one "answer sheet" every domain fills in.

The AutoExperiment Farm runs many *kinds* of experiment (CPU cosim, ECG detection,
SPICE circuits, compiler diffing). They have nothing in common at the surface — a
CPU run talks about instructions and registers, an ECG run about beats and
sensitivity — so the farm core refuses to know any of that. Instead every domain's
adapter boils its result down to this single shape, and the store, the batch
runner, and the dashboard only ever speak this shape.

    {
      "type":       "cosim",                 # which domain produced this
      "run_id":     "cosim-9f3a...",         # content hash: same inputs -> same id
      "status":     "pass" | "fail" | "error",
      "primary_metric": {                    # the ONE number that means "how good"
        "name": "instructions_matched",      # cosim; ECG -> "sensitivity"; SPICE -> "linf_error"
        "value": 250,
        "unit": "instructions"
      },
      "reason_code": "match",                # short machine tag, for clustering failures
      "detail":     "250/250 instructions matched Spike",   # one human-readable line
      "metrics":    { "total": 250, "first_mismatch": null },  # any extra numbers
      "artifacts":  ["results/test0/dino.trace"],  # files to click through to
      "config":     { "test": "...", "cpu": "built-in", "bugs": [] },  # what was run
      "source_sha": "cd66de7",               # commit of the thing under test
      "created_at": "2026-07-21T12:00:00Z"   # stamped by the farm, not the adapter
    }

`primary_metric` is what makes cross-domain comparison possible: every domain emits
one canonical number, so the dashboard charts them side by side and the regression
trend (that number per source_sha over commits) is "the loop".
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict

STATUSES = ("pass", "fail", "error")


@dataclass
class Metric:
    """The one headline number for a run. Every domain picks its own name/unit."""
    name: str
    value: float
    unit: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "value": self.value, "unit": self.unit}


@dataclass
class ExperimentRecord:
    """One experiment = one design-under-test vs its golden reference → this record.

    `type`, `status`, `primary_metric`, and `config` are required from the adapter.
    `run_id` and `created_at` are filled in by the farm if the adapter leaves them
    blank (run_id via content_run_id, so identical inputs collapse to one id).
    """
    type: str
    status: str
    primary_metric: Metric
    config: dict = field(default_factory=dict)
    reason_code: str = ""
    detail: str = ""
    metrics: dict = field(default_factory=dict)
    artifacts: list = field(default_factory=list)
    source_sha: str = ""
    run_id: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["primary_metric"] = self.primary_metric.to_dict()
        return d


def content_run_id(type_: str, config: dict, source_sha: str = "", inputs=None) -> str:
    """Content-addressed id: hash(type + config + inputs + source_sha).

    Same experiment (same type, config, inputs, and source commit) always hashes to
    the same id — so the store can skip re-running unchanged work and resume after a
    crash. `inputs` is any extra fingerprint the adapter wants folded in (e.g. the
    sha of a test file); pass None to ignore it.
    """
    payload = json.dumps(
        {"type": type_, "config": config, "inputs": inputs, "source_sha": source_sha},
        sort_keys=True, separators=(",", ":"), default=str,
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"{type_}-{digest}"


def validate(record: dict) -> tuple[bool, list[str]]:
    """Dependency-free schema check. Returns (ok, errors) with human-readable errors,
    mirroring the dashboard's validateRun.js style so a bad adapter gets a clear
    message instead of a stack trace downstream."""
    errors: list[str] = []

    def is_str(v):
        return isinstance(v, str)

    def is_num(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool)

    if not isinstance(record, dict):
        return False, ["record must be an object."]

    if not is_str(record.get("type")) or not record.get("type"):
        errors.append('"type" must be a non-empty string (the domain, e.g. "cosim").')

    if record.get("status") not in STATUSES:
        errors.append(f'"status" must be one of {STATUSES}.')

    pm = record.get("primary_metric")
    if not isinstance(pm, dict):
        errors.append('"primary_metric" must be an object {name, value, unit}.')
    else:
        if not is_str(pm.get("name")) or not pm.get("name"):
            errors.append('"primary_metric.name" must be a non-empty string.')
        if not is_num(pm.get("value")):
            errors.append('"primary_metric.value" must be a number.')
        if "unit" in pm and not is_str(pm["unit"]):
            errors.append('"primary_metric.unit" must be a string.')

    for key in ("config", "metrics"):
        if key in record and not isinstance(record[key], dict):
            errors.append(f'"{key}" must be an object.')
    if "artifacts" in record and not isinstance(record["artifacts"], list):
        errors.append('"artifacts" must be a list.')
    for key in ("reason_code", "detail", "source_sha", "run_id", "created_at"):
        if key in record and not is_str(record[key]):
            errors.append(f'"{key}" must be a string.')

    # A failing run should say why (so failures can be clustered by reason_code).
    if record.get("status") == "fail" and not record.get("reason_code"):
        errors.append('a "fail" record should set a "reason_code" for clustering.')

    return (len(errors) == 0, errors)
