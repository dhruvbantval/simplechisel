#!/usr/bin/env python3
"""One circuit experiment: a real SPICE simulation vs the closed-form answer.

Intern 3's domain. An RC low-pass charging from a step input has an exact textbook
solution, so a simulator's output can be checked against maths rather than against
another simulator:

    DUT     ngspice transient analysis of the netlist
    golden  v(t) = Vin * (1 - exp(-t / RC))

Pass when the worst deviation anywhere (L-infinity) is under 1% of Vin. Prints one
JSON object for the adapter to read.

    python physics_experiment.py '{"name":"rc_1k_1u","r":1000,"c":1e-6}'
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

NETLIST = """RC low-pass step response
V1 in 0 PWL(0 0 1n {vin})
R1 in out {r}
C1 out 0 {c}
.tran {step} {tstop} 0 {step}
.print tran v(out)
.end
"""


def ngspice_bin() -> str:
    """The ngspice executable that writes to stdout.

    The Windows build ships ngspice.exe (windowed, produces no piped output) and
    ngspice_con.exe (console). Prefer the console build. NGSPICE overrides.
    """
    override = os.environ.get("NGSPICE")
    if override:
        return override
    for name in ("ngspice_con", "ngspice"):
        if shutil.which(name):
            return name
    return "ngspice"


def run_ngspice(r, c, vin, tstop, step):
    with tempfile.TemporaryDirectory() as d:
        cir = Path(d) / "rc.cir"
        cir.write_text(NETLIST.format(r=r, c=c, vin=vin, tstop=tstop, step=step))
        proc = subprocess.run([ngspice_bin(), "-b", str(cir)],
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        return proc.stdout + proc.stderr


def parse_table(out):
    """ngspice batch prints an index/time/value table; pull (t, v) pairs."""
    ts, vs = [], []
    row = re.compile(r"^\s*\d+\s+([0-9eE+\-.]+)\s+([0-9eE+\-.]+)\s*$")
    for line in out.splitlines():
        m = row.match(line)
        if m:
            try:
                ts.append(float(m.group(1)))
                vs.append(float(m.group(2)))
            except ValueError:
                continue
    return np.array(ts), np.array(vs)


def main() -> int:
    cfg = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    r = float(cfg.get("r", 1000.0))
    c = float(cfg.get("c", 1e-6))
    vin = float(cfg.get("vin", 1.0))
    tau = r * c
    tstop = float(cfg.get("tstop", 5 * tau))
    step = float(cfg.get("step", tau / 200.0))
    tol = float(cfg.get("tolerance", 0.01))  # 1% of Vin

    out = run_ngspice(r, c, vin, tstop, step)
    t, v = parse_table(out)
    if t.size < 10:
        print(json.dumps({"error": "could not parse ngspice output",
                          "head": out[:400]}))
        return 3

    golden = vin * (1.0 - np.exp(-t / tau))
    linf = float(np.max(np.abs(v - golden)))
    print(json.dumps({
        "linf_error": linf,
        "tolerance": tol * vin,
        "ok": bool(linf < tol * vin),
        "tau_s": tau,
        "samples": int(t.size),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
