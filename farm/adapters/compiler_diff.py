"""The compiler-diff adapter — the farm's SECOND experiment type, and the proof
that a totally different science plugs in as just two functions.

Differential compiler testing is the exact same shape as the CPU cosim: two
implementations of one spec, same input, flag where they disagree. Here the two
"implementations" are the same compiler at -O0 and -O2 (the classic miscompile
catcher). For a well-defined program the two builds must produce identical output;
a divergence is a compiler bug (or undefined behaviour in the program).

    DUT             clang -O2
    golden ref      clang -O0
    one experiment  compile+run one C program at both, outputs must agree
    primary_metric  outputs_agree (1 = agree, 0 = diverge)

Nothing in the farm core changed to add this — it just writes ExperimentRecords to
the same store, so it shows up as a second line on the same regression trend.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from ..adapter import Adapter
from ..record import Metric

_HELPER = Path(__file__).parent / "compiler_diff.sh"
_SECTION = re.compile(
    r"===O0=== rc=(-?\d+)\n(.*?)\n===O2=== rc=(-?\d+)\n(.*?)\n===END===", re.S)


class CompilerDiffAdapter(Adapter):
    type = "compiler-diff"

    def build_command(self, config: dict) -> list:
        """Run the same C program through -O0 and -O2 and print both outputs."""
        return ["bash", str(_HELPER), config["program"]]

    def parse_result(self, exit_code, stdout, artifacts_dir, config):
        program = config["program"]
        source_sha = config.get("source_sha", "")
        name = Path(program).name
        inputs = self._program_fingerprint(program)

        if "COMPILE_FAIL" in stdout:
            first = (stdout.strip().splitlines() or ["compile failed"])[0]
            return self.record(
                status="error", metric=Metric("outputs_agree", 0),
                reason_code="compile_fail", detail=f"{name}: {first}",
                config={"program": name, "cc": config.get("cc", "clang")},
                source_sha=source_sha, inputs=inputs)

        m = _SECTION.search(stdout)
        if not m:
            return self.record(
                status="error", metric=Metric("outputs_agree", 0),
                reason_code="unparseable", detail=f"{name}: could not read both outputs",
                config={"program": name, "cc": config.get("cc", "clang")},
                source_sha=source_sha, inputs=inputs)

        rc0, out0, rc2, out2 = m.group(1), m.group(2), m.group(3), m.group(4)
        agree = (out0 == out2) and (rc0 == rc2)
        return self.record(
            status="pass" if agree else "fail",
            metric=Metric("outputs_agree", 1 if agree else 0),
            reason_code="match" if agree else "output_divergence",
            detail=(f"{name}: -O0 and -O2 agree" if agree
                    else f"{name}: -O0 vs -O2 DIVERGE (miscompile or UB)"),
            metrics={"exit_o0": int(rc0), "exit_o2": int(rc2)},
            config={"program": name, "cc": config.get("cc", "clang")},
            source_sha=source_sha, inputs=inputs)

    def _program_fingerprint(self, program):
        f = Path(program)
        if f.is_file():
            return hashlib.sha256(f.read_bytes()).hexdigest()[:16]
        return f.name
