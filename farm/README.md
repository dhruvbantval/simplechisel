# AutoExperiment Farm

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

Python 3.10–3.12 is required (`pyvsc`, used by the CPU generator, has no wheels
for 3.13+). Run everything from the repository root.

**macOS / Linux**

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

**Windows** (PowerShell) — a venv puts its executables in `Scripts\`, not `bin/`:

```powershell
# 1.
py -3.12 -m venv farm\.venv
farm\.venv\Scripts\pip install -r farm\requirements\core.txt
farm\.venv\Scripts\pip install -r farm\requirements\all.txt

# 2.
farm\.venv\Scripts\python farm\run_experiment.py --list

# 3.
farm\.venv\Scripts\python farm\run_experiment.py control
farm\.venv\Scripts\python farm\run_experiment.py --all

# 4. serve.sh is a bash script; run it from Git Bash, or start the backend
#    directly after building the dashboard once:
#      cd farm\dashboard; npm install; npm run build
#      Copy-Item -Recurse farm\dashboard\dist farm\webapp\static
farm\.venv\Scripts\python farm\webapp\server.py
```

Then open <http://127.0.0.1:8000> → **Experiments** to launch runs, **Tests** to
generate inputs, **Trend** to see every domain's pass-rate over time.

`control` and `ecg` work out of the box. The other three need a system tool —
see the next section.

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

## Installing the system tools

`control` needs nothing beyond pip. The other four each want a tool on `PATH`.
The dashboard disables the Run button and shows the install command for your
platform; `farm/run_experiment.py` refuses with the same message.

| Tool | Needed by | macOS | Debian / Ubuntu / WSL | Windows |
|---|---|---|---|---|
| `clang` (or any C compiler) | `compiler-diff` | `xcode-select --install` | `sudo apt install -y clang` | `winget install LLVM.LLVM` |
| `ngspice` | `physics` | `brew install ngspice` | `sudo apt install -y ngspice` | `choco install ngspice` |
| `verilator` | `cosim` | `brew install verilator` | `sudo apt install -y verilator` | in WSL — see below |
| `spike` | `cosim` | `cosim/install_spike.sh` | `cosim/install_spike.sh` | in WSL — see below |
| RISC-V gcc | `cosim` | `brew install riscv64-elf-gcc riscv64-elf-binutils` | `sudo apt install -y gcc-riscv64-unknown-elf` | in WSL — see below |
| `sbt` | `cosim` | `brew install sbt` | [scala-sbt.org](https://www.scala-sbt.org/download) | `winget install sbt.sbt` |

After installing anything, **restart the backend** — tool availability is probed
at startup.

Either RISC-V gcc prefix works: `riscv64-elf-gcc` (Homebrew) or
`riscv64-unknown-elf-gcc` (apt). `spike` is not in apt or Homebrew core, so
[`cosim/install_spike.sh`](../cosim/install_spike.sh) builds it from source into
`~/.local` (override with `PREFIX=`).

`compiler-diff` is not fussy about *which* C compiler: the helper honours `CC`,
so `CC=gcc` works as well as clang. The experiment compares one compiler against
itself at two optimisation levels, so any working compiler is a valid subject.

### macOS notes

Install [Homebrew](https://brew.sh) first; every tool above except `spike` comes
from it. Apple Silicon puts binaries in `/opt/homebrew/bin`, which the backend
already adds to the PATH it hands to child processes.

### Windows notes

`clang`, `ngspice` and `sbt` install natively; their installers request UAC, so
run them from an elevated shell.

The cosim toolchain (riscv-dv, verilator, spike, the RISC-V cross-compiler) has
no Windows build, so **the backend runs cosim inside WSL** — both test generation
and runs — against this same checkout over `/mnt/c`. Generated `.S` files and
results still land in your Windows tree. Install the toolchain once inside WSL:

```bash
wsl
sudo apt update
sudo apt install -y verilator gcc-riscv64-unknown-elf sbt
cd /mnt/c/path/to/simplechisel-fork
bash cosim/install_spike.sh          # builds spike, ~5 minutes
```

Tool detection follows suit: for `cosim` on Windows the backend probes WSL rather
than the Windows `PATH`, so a tool installed in WSL is correctly reported as
present.

Two Windows details the code handles, worth knowing if you script around it:

- A bare `bash` resolves to `System32\bash.exe` (the WSL launcher) because
  `CreateProcess` searches System32 before `PATH`. The backend resolves a real
  Git/MSYS bash by path; set `FARM_BASH` to override.
- Shell scripts must keep LF endings. `.gitattributes` enforces this; a CRLF
  checkout breaks every script under WSL with
  `set: pipefail: invalid option name`.

### Fetching the ECG dataset

The MIT-BIH recordings are not committed — they aren't ours to redistribute.
Fetch them once (needs network):

```bash
farm/.venv/bin/python farm/experiments/ecg_fetch.py        # macOS / Linux
farm\.venv\Scripts\python farm/experiments/ecg_fetch.py    # Windows
```

Files land in `farm/data/mitdb/` (git-ignored). "Generate tests" on the ECG tab
downloads more of the 48 records in the database.

**How it is scored.** A detection counts if it lands within 150 ms of an
annotated beat, and only symbols that denote an actual heartbeat count as truth
(rhythm and signal-quality markers are excluded). Scoring skips the first
`warmup_seconds` (default 5): the detector's band-pass filter has not settled at
the start of an excerpt, so the opening beat is missed on nearly every record
regardless of quality, and counting it would charge a constant penalty for a
measurement artifact. A case passes at `min_sensitivity` (default 0.95).

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

You don't have to supply inputs by hand. Every `campaign` experiment can add its
own test cases: on the Tests tab there's a **Generate tests** box — name a batch,
pick how many, click **Generate**. Hit **Run** on the Experiments tab to score
them.

Every generator produces cases a correct implementation passes, so a failure is a
regression rather than a bad test. Where that guarantee cannot be met honestly,
the generator does not fabricate data: `ecg` downloads more real recordings
instead of synthesizing waveforms, because a clean signal with spikes at chosen
positions is found by any detector and would score 100% regardless of quality.

| Experiment | What "Generate" makes |
|---|---|
| `compiler-diff` | random integer C programs (a tiny CSmith) — well-defined arithmetic, so any `-O0` vs `-O2` divergence is a real miscompile |
| `control` | random PID gain sets, screened so the reference controller already meets the spec at them |
| `ecg` | more real MIT-BIH recordings, downloaded from the 48 in the database |
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
