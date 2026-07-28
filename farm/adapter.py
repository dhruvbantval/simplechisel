"""The adapter contract — how a new science plugs into the farm.

Adding an experiment type is writing ONE of these, not touching the core. The
farm calls two methods and never learns what a "mismatch" means in your domain:

    build_command(config)                 -> argv         # how to launch the run
    parse_result(exit_code, stdout, ...)  -> ExperimentRecord   # what it meant

The farm handles everything generic around them: running the command, capturing
output, content-addressing the run_id, stamping created_at, storing the record,
and charting it next to every other domain. So the adapter's whole job is:
"here's how to run my thing, and here's how to read pass/fail + one number out of
its output."

A minimal adapter:

    class CompilerDiffAdapter(Adapter):
        type = "compiler-diff"

        def build_command(self, config):
            return ["bash", "run_diff.sh", config["program"]]

        def parse_result(self, exit_code, stdout, artifacts_dir, config):
            agree = "MATCH" in stdout
            return self.record(
                status="pass" if agree else "fail",
                metric=Metric("outputs_agree", 1 if agree else 0),
                reason_code="match" if agree else "output_divergence",
                detail=stdout.strip().splitlines()[-1] if stdout else "",
                config=config,
            )

The cosim runner we already have becomes the first adapter (a thin wrapper that
turns a campaign JSON into these records) — see farm/README.md.
"""
from __future__ import annotations

from .record import ExperimentRecord, Metric, content_run_id, validate


class Adapter:
    """Base class for a domain adapter. Subclasses set `type` and implement the two
    methods below. `record(...)` is a helper so adapters don't hand-build dicts."""

    type: str = "unknown"

    # --- the two functions the farm calls -----------------------------------
    def build_command(self, config: dict) -> list:
        """Return the argv the farm should run for this experiment config."""
        raise NotImplementedError

    def parse_result(self, exit_code: int, stdout: str, artifacts_dir: str,
                     config: dict) -> ExperimentRecord:
        """Turn a finished run's output into one ExperimentRecord."""
        raise NotImplementedError

    # --- helper for building a well-formed record ---------------------------
    def record(self, *, status: str, metric: Metric, config: dict,
               reason_code: str = "", detail: str = "", metrics: dict | None = None,
               artifacts: list | None = None, source_sha: str = "",
               inputs=None) -> ExperimentRecord:
        """Assemble an ExperimentRecord for this adapter's type, with a
        content-addressed run_id. `created_at` is left for the farm to stamp."""
        rec = ExperimentRecord(
            type=self.type,
            status=status,
            primary_metric=metric,
            config=config,
            reason_code=reason_code,
            detail=detail,
            metrics=metrics or {},
            artifacts=artifacts or [],
            source_sha=source_sha,
            run_id=content_run_id(self.type, config, source_sha, inputs),
        )
        ok, errors = validate(rec.to_dict())
        if not ok:
            raise ValueError(f"{self.type} produced an invalid record: {errors}")
        return rec
