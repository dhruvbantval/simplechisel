"""The cosim adapter — CPU cosim as the farm's first experiment type.

We don't rebuild the cosim pipeline; we wrap its output. `run_cosim.sh` already
writes a campaign JSON (one entry per test program, with pass/fail and the
divergence detail). This adapter turns each of those tests into one universal
ExperimentRecord, so the farm/store/dashboard can treat CPU cosim exactly like
any other science.

Mapping (campaign test -> record):
    status            <- test.passed
    primary_metric    <- instructions_matched (matched before divergence)
    reason_code       <- kind of the first mismatch (pc/register/trace_length/match)
    detail            <- one human line describing the divergence
    artifacts         <- the DINO trace file for that test
    config            <- {test, cpu, bugs}   (folds into the content-addressed id)
    source_sha        <- the CPU's version (passed in by the caller)
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from ..adapter import Adapter
from ..record import Metric


class CosimAdapter(Adapter):
    type = "cosim"

    def build_command(self, config: dict) -> list:
        """Cosim runs a whole folder at once (build the CPU once, run every test),
        so the batch entry point is run_cosim.sh over a folder. The env carries
        steps / CPU / bugs; the caller sets those. `records_from_campaign` is the
        real workhorse — this exists to satisfy the adapter contract."""
        return ["bash", "cosim/run_cosim.sh", config["folder"]]

    def parse_result(self, exit_code, stdout, artifacts_dir, config):
        """Single-record path: not used by the batch flow, which calls
        records_from_campaign. Provided for contract completeness."""
        raise NotImplementedError("cosim is batch; use records_from_campaign()")

    # --- the real wrapper: campaign JSON -> universal records ----------------
    def records_from_campaign(self, campaign: dict, *, source_sha: str = "",
                              cpu: str = "built-in", results_dir: str = "cosim/build/results",
                              tests_dir: str | None = None):
        """Yield one ExperimentRecord per test in a cosim campaign JSON. If
        `tests_dir` is given, each test's .S program is hashed into the run_id so
        two different programs never collide (content addressing on real content,
        not filename)."""
        bugs = campaign.get("mutationLabel") or None
        for test in campaign.get("tests", []):
            yield self._record_for_test(test, source_sha=source_sha, cpu=cpu,
                                        bugs=bugs, results_dir=results_dir,
                                        tests_dir=tests_dir)

    def _program_fingerprint(self, name, tests_dir):
        """A content hash of the test program, so different programs with the same
        filename get different run_ids. Falls back to the name if the file is gone."""
        if tests_dir:
            f = Path(tests_dir) / f"{name}.S"
            if f.is_file():
                return hashlib.sha256(f.read_bytes()).hexdigest()[:16]
        return name

    def _record_for_test(self, test, *, source_sha, cpu, bugs, results_dir, tests_dir=None):
        name = test["testName"]
        total = test.get("totalInstructions", 0)
        first_mismatch = test.get("firstMismatchInstr")
        passed = test.get("passed", False)
        matched = total if passed else max(0, (first_mismatch or 1) - 1)

        if passed:
            reason, detail = "match", f"{matched}/{total} instructions matched Spike"
        else:
            bad = next((i for i in test.get("instructions", [])
                        if i.get("instrNumber") == first_mismatch), None)
            mm = (bad or {}).get("mismatch") or {}
            reg = mm.get("register", "")
            if reg == "PC":
                reason = "pc_mismatch"
            elif reg == "trace_length":
                reason = "trace_length"
            else:
                reason = "register_mismatch"
            if reason == "trace_length":
                detail = f"trace length differs: DINO {mm.get('got')} vs Spike {mm.get('expected')}"
            else:
                mnem = (bad or {}).get("mnemonic", "?")
                detail = (f"diverged at #{first_mismatch} ({mnem}): "
                          f"{reg} expected {mm.get('expected')} got {mm.get('got')}")

        config = {"test": name, "cpu": cpu, "bugs": bugs}
        return self.record(
            status="pass" if passed else "fail",
            metric=Metric("instructions_matched", matched, "instructions"),
            reason_code=reason,
            detail=detail,
            metrics={"total_instructions": total, "first_mismatch": first_mismatch},
            artifacts=[f"{results_dir}/{name}/dino.trace"],
            config=config,
            source_sha=source_sha,
            inputs=self._program_fingerprint(name, tests_dir),  # content, not just name
        )
