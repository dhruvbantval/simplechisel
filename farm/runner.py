"""The generic batch runner — runs any command-based adapter's experiments.

This is the domain-agnostic loop the doc describes: for each experiment config,
call the adapter's build_command, run it, hand the output to parse_result, and
store the resulting record. It knows nothing about compilers or CPUs — it just
drives the two-function contract. (Single-threaded for now; parallel + retry/resume
is a later step. The cosim domain has its own batch path in run_cosim.sh because it
builds the CPU once for a whole folder.)
"""
from __future__ import annotations

import subprocess
import tempfile


def run_experiments(adapter, configs, store, *, source_sha="", on_log=None):
    """Run each config through `adapter`, storing one record per experiment.
    Returns the list of records. `source_sha` is threaded into each config so the
    adapter can stamp it (the version of the thing under test)."""
    records = []
    for config in configs:
        cfg = {**config, "source_sha": source_sha}
        argv = adapter.build_command(cfg)
        with tempfile.TemporaryDirectory() as artifacts_dir:
            proc = subprocess.run(argv, capture_output=True, text=True)
            output = (proc.stdout or "") + (proc.stderr or "")
            rec = adapter.parse_result(proc.returncode, output, artifacts_dir, cfg)
        store.save(rec.to_dict())
        records.append(rec)
        if on_log:
            on_log(f"[{rec.type}] {rec.detail} -> {rec.status}")
    return records
