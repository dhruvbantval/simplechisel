# AutoExperiment Farm

One pipeline that runs many kinds of experiment and puts them all on one
dashboard: a RISC-V CPU, a compiler, a control loop, a heartbeat detector, and a
circuit simulator.

Every experiment has the same shape —

> **a design-under-test vs a golden reference → pass/fail + one headline number**

— so a single record format, a single store and a single regression trend work
for all of them.

| Experiment | Design under test | Golden reference | Metric |
|---|---|---|---|
| `cosim` | DINO RISC-V CPU (Chisel → Verilator) | Spike, per instruction | `instructions_matched` |
| `compiler-diff` | `clang -O2` | the same compiler at `-O0` | `outputs_agree` |
| `control` | a PID controller (Python or C) | a 2nd-order step-response spec | `overshoot` |
| `ecg` | NeuroKit2 R-peak detector | cardiologists' MIT-BIH annotations | `sensitivity` |
| `physics` | ngspice transient analysis | the closed-form RC step response | `linf_error` |

## Quick start

```bash
python3.11 -m venv farm/.venv                                   # 3.10-3.12
farm/.venv/bin/pip install -r farm/requirements/all.txt
farm/.venv/bin/python farm/run_experiment.py --all
farm/webapp/serve.sh                                            # dashboard on :8000
```

On Windows a venv puts its executables in `Scripts\` rather than `bin/`; see
[farm/README.md](farm/README.md#quick-start) for the PowerShell equivalents.

`control` and `ecg` work with no extra tooling. `compiler-diff`, `physics` and
`cosim` each need a system tool —
[farm/README.md](farm/README.md#installing-the-system-tools) has the install
table for macOS, Linux and Windows.

## Documentation

| Where | What |
|---|---|
| [farm/README.md](farm/README.md) | the farm: setup, the experiments, adding your own |
| [farm/webapp/README.md](farm/webapp/README.md) | the backend and its HTTP API |
| [farm/dashboard/README.md](farm/dashboard/README.md) | the React dashboard |
| [cosim/README.md](cosim/README.md) | CPU cosimulation against Spike |
| [cosim/generator/README.md](cosim/generator/README.md) | random RISC-V program generation (riscv-dv) |
| [docs/project-brief.md](docs/project-brief.md) | the original project brief |

## The CPU

This repo is a Chisel fork carrying the DINO CPU that the `cosim` experiment
tests. To elaborate the designs directly:

```
sbt "runMain gcd.GCD"
sbt "runMain dinocpu.SingleCycleCPUNoDebug"
sbt "runMain dinocpu.SingleCycleCPUDebug"
sbt "runMain dinocpu.pipelined.PipelinedDualIssueDebug"
sbt "runMain dinocpu.pipelined.PipelinedDualIssueNoDebug"
```

## License

See [LICENSE](LICENSE); the Chisel bootstrap portions are covered by
[LICENSE.chiselbootstrap](LICENSE.chiselbootstrap).
