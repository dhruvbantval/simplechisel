# Experiment Farm

One pipeline that runs **many kinds of experiment** and puts them all on one
dashboard — a CPU, a compiler, a control loop, a heartbeat detector, a circuit.

Every experiment here is the same shape:

> **a design-under-test vs a golden reference → pass/fail + one headline number**

Nothing else is shared. The CPU experiment runs Verilator and Spike; the ECG
experiment runs a detector against cardiologists' annotations; the circuit
experiment runs SPICE against a textbook formula. They have no idea the others
exist. What makes them one "farm" is that each one fills in the **same record**,
so a single store, a single dashboard and a single regression trend work for all
of them.

```
   experiment types              one farm                 one dashboard
   (each = a small adapter)      run → record             aggregate → trend
   ┌ cosim         ┐                                      ┌─────────────────────┐
   │ compiler-diff │ ──adapter──►  runner ──► record ──►  │ pass/fail by domain │
   │ control       │               store                  │ regression trend    │──┐
   │ ecg           │                                      └─────────────────────┘  │
   └ physics       ┘                                                               │
        ▲                                                                          │
        └────────────── fix / rerun on regression ◄──── THE LOOP ──────────────────┘
```

The **regression trend** is the loop: pass-rate per version, per domain. A change
that makes something worse shows up as a line dropping.

---

## Quick start

```bash
# 1. core (reads farm.yaml) + whichever experiments you want
python3.11 -m venv farm/.venv
farm/.venv/bin/pip install -r farm/requirements/core.txt
farm/.venv/bin/pip install -r farm/requirements/all.txt   # or just one experiment

# 2. see what's configured
farm/.venv/bin/python farm/run_experiment.py --list

# 3. run one, or run them all at once
farm/.venv/bin/python farm/run_experiment.py control
farm/.venv/bin/python farm/run_experiment.py --all   # every config-driven experiment

# 4. open the dashboard (builds the UI, serves it + the API on :8000)
farm/webapp/serve.sh
```

Then open <http://127.0.0.1:8000> → **Run** to launch experiments, **Trend** to see
every domain's pass-rate over time.

## The experiments

| Type | Design under test | Golden reference | Headline metric | Extra setup |
|---|---|---|---|---|
| `cosim` | DINO RISC-V CPU (Chisel → Verilator) | Spike, per instruction | `instructions_matched` | sbt, verilator, spike, riscv gcc |
| `compiler-diff` | `clang -O2` | `clang -O0` (same program must agree) | `outputs_agree` | a C compiler |
| `control` | a PID controller (Python or C) | a 2nd-order step-response spec | `overshoot` | `requirements/control.txt` |
| `ecg` | NeuroKit2 R-peak detector | cardiologists' MIT-BIH annotations | `sensitivity` | `requirements/ecg.txt` + fetch data |
| `physics` | ngspice transient analysis | closed-form RC step response | `linf_error` | `requirements/physics.txt` + ngspice |

Install only what you need — each experiment has its own requirements file.
`cosim` is the largest and has its own toolchain; see [../cosim/README.md](../cosim/README.md).

For `ecg`, fetch the dataset once (it is not committed — it isn't ours to
redistribute):

```bash
farm/.venv/bin/python farm/experiments/ecg_fetch.py
```

## How it fits together

```
farm/
  farm.yaml         ← THE config: what experiments exist and how to run them
  record.py         ← the universal record every experiment fills in
  adapter.py        ← the 2-function contract an experiment implements
  store.py          ← content-addressed record store (idempotent, resumable)
  runner.py         ← generic batch runner (build_command → run → parse_result)
  config.py         ← reads farm.yaml
  run_experiment.py ← CLI: run any experiment's campaign
  adapters/         ← the farm-side glue, one module per experiment
  experiments/      ← the actual science scripts (kept apart so an adapter never
                      shadows a library the script imports)
  requirements/     ← per-experiment dependencies
  webapp/           ← backend that drives everything from the browser
  dashboard/        ← the React UI
```

### The universal record

Every experiment, in any field, produces this:

```jsonc
{
  "type": "ecg",
  "run_id": "ecg-3f9c…",                 // content hash: same inputs → same id
  "status": "pass",
  "primary_metric": { "name": "sensitivity", "value": 0.986, "unit": "fraction" },
  "reason_code": "match",                // short tag, for clustering failures
  "detail": "record 100: found 73/74 expert-marked beats",
  "metrics": { "ppv": 1.0, "tp": 73, "fn": 1 },
  "artifacts": [],
  "config": { "record": "100", "seconds": 60 },
  "source_sha": "cd66de7",               // version of the thing under test
  "created_at": "2026-07-22T…"
}
```

`primary_metric` is what makes cross-domain comparison possible: one canonical
number per run, so the dashboard can chart a CPU next to a heartbeat detector.

### Bringing your own tests

Each experiment's inputs live in a known place; add your own there and they show
up on the site with no code changes.

| Experiment | Your own tests | Where they go |
|---|---|---|
| `cosim` | RISC-V programs (`.S`) | upload on the **Tests** tab, or a folder under `cosim/build/webapp/tests/<name>/` → appears in the **Run** dropdown |
| `compiler-diff` | C programs (`.c`) | upload on the tab, or drop into `farm/adapters/corpus/compiler/` → appear as cases |
| `control` | a PID controller (Python **or** C) | upload it on the Control tab — adapters accept a native `Controller` class, a `simple-pid` `PID` class, or C (`PID.c` + `PID.h`). Judged on a step-response spec. |
| `physics` | R/C values | the "Run your own RC circuit" box on the tab, or entries under `physics`'s `cases:` in `farm.yaml` |
| `ecg` | ECG recordings (WFDB `.dat`/`.hea`/`.atr`) | upload the three files on the ECG tab (the `.atr` is your golden), or fetch into `farm/data/mitdb/` and add `cases:` |

Every one of these also has a **Generate tests** button (see below) if you'd
rather have inputs synthesized than supply your own.

### Generating tests

You don't have to supply inputs by hand. Every `campaign` experiment can
**synthesize** its own test cases: on the experiment's tab there's a
**Generate tests** box — pick how many, click **Generate**, and the new cases
appear in the Cases list. Hit **Run** to score them. Each generator produces
inputs with a *known* correct answer, so a failure means a real regression, not a
bad test.

| Experiment | What "Generate" makes |
|---|---|
| `compiler-diff` | random integer C programs (a tiny CSmith) — well-defined arithmetic, so any `-O0` vs `-O2` divergence is a real miscompile |
| `control` | random PID gain sets swept through the reference controller — a stress test of the step-response judge |
| `ecg` | synthetic ECGs with QRS spikes at known sample positions, written as WFDB records whose `.atr` **is** the ground truth |
| `physics` | random R/C values across the low-pass family, all covered by the closed-form golden |

Under the hood a generator is just a script that prints a JSON list of cases (and
may write input files); it's wired in by a `generate:` block in `farm.yaml`
(`script`, `default` count, `label`) — no server, runner, or UI changes. Generated
cases and any files they write live under `farm/build/generated/` (git-ignored)
and run alongside the configured `cases:`.

Example — run your own CPU programs:

```bash
mkdir -p cosim/build/webapp/tests/my-tests
cp ~/Downloads/*.S cosim/build/webapp/tests/my-tests/    # your bare-metal RV64I programs
# now pick "my-tests" in the Run tab, or:
STEPS=80 cosim/run_cosim.sh cosim/build/webapp/tests/my-tests/
```

(A cosim program is bare-metal RV64I linked at `0x80000000`: a `.globl _start`,
your instructions, then `loop: j loop`. See `cosim/asm_tests/` for examples.)

Example — test your own PID controller:

Upload it on the **Control** tab (the "Test your own PID controller" box). The
adapter layer (`farm/experiments/controllers/loader.py`) recognizes several shapes,
so you don't have to rewrite your controller to our interface:

| Your controller | Recognized as |
|---|---|
| a `Controller` class with `step(error, dt)` | native (our template) |
| a `simple-pid` `PID` class (`pid(measurement)`) | simple-pid |
| C with `PIDController_Update` (`PID.c` + `PID.h`) | C via ctypes |

It's judged on a **step-response spec** (small steady-state error, bounded
overshoot, settles in time) — how a control engineer actually grades a controller
— so a real PID with filtered derivative / anti-windup / limits passes, while a
genuinely broken one (no integral, wrong sign) fails.

### Adding a new experiment

Two steps, and nothing in the runner, server or dashboard changes:

**1. Write an adapter** (`farm/adapters/yours.py`) — two functions:

```python
class YoursAdapter(Adapter):
    type = "yours"

    def build_command(self, config):           # how to run one case
        return [python_bin(), script("yours_experiment.py"), json.dumps(config)]

    def parse_result(self, exit_code, stdout, artifacts_dir, config):
        data = last_json(stdout)                # what the outcome means
        ok = data["ok"]
        return self.record(
            status="pass" if ok else "fail",
            metric=Metric("your_number", data["value"], "unit"),
            reason_code="match" if ok else "mismatch",
            detail="...", config=config,
            source_sha=config.get("source_sha", ""), inputs=config["name"],
        )
```

Register it in `farm/adapters/__init__.py`.

**2. Declare it in `farm.yaml`:**

```yaml
  - type: yours
    label: Your experiment
    dut: the thing you built
    golden: what it's checked against
    metric: your_number
    ui: campaign
    requirements: farm/requirements/yours.txt
    cases:
      - { name: case1, ... }
```

It now appears as a tab in the dashboard, runs from the UI, stores records, and
gets its own line on the regression trend.

## Design notes

- **The core knows nothing about any domain.** It never learns what a "mismatch"
  means — the adapter decides. That's what keeps five unrelated sciences in one
  pipeline without special cases.
- **Content-addressed run ids.** `run_id = hash(type + config + inputs + source_sha)`,
  so re-running identical work overwrites in place instead of piling up, and a
  campaign can resume after a crash.
- **Experiment scripts are separate processes.** They need heavy third-party
  packages; the farm core stays stdlib-only (plus PyYAML) so it's cheap to import
  and hard to break.
- **Adapters and scripts live in different folders.** `adapters/control.py` would
  otherwise shadow the `control` library when the script runs.
- **Datasets are never committed.** `farm/data/` is git-ignored and fetched on
  demand.

## License

See [../LICENSE](../LICENSE).
