# CPU verification web app

Drive the whole cosim pipeline from the browser. Generation and running are
separate, and bug injection is stateful:

- **Tests** view — generate a named batch of programs, saved as a **folder**.
  Browse the library of folders.
- **Run** view — pick a folder and **Run** it against the CPU. The success rate
  loads in place. A side panel lets you **Inject** known CPU bugs (they stack)
  and **Reset** back to a clean CPU. Run reflects whatever is injected.

No JSON files change hands — the site generates, runs, and loads results for you.

```
Tests:  Generate ─▶ gen_tests.sh ─▶ folder of .S programs (the library)
Run:    [folder] + [injected bugs] ─▶ run_cosim.sh ─▶ campaign JSON ─▶ dashboard
                                       (Verilator + Spike)             (success rate)
Bugs:   Inject ─▶ edit Chisel source (stacks) … Reset ─▶ restore clean CPU
```

Generating a folder never runs anything; running a folder never regenerates it.
Injected bugs persist on the CPU source until Reset, and the CPU is rebuilt
automatically on the next run after the bug set changes.

---

## Run it (one command)

```bash
cosim/webapp/serve.sh
```

Open the printed URL (default <http://127.0.0.1:8000>), go to **Generate**, set
the batch size, and click **Generate tests**. First launch builds the dashboard
and, on the first generate, the CPU simulator (~2 min once); after that each
batch is seconds.

For hot-reload development (Vite on :5173 + backend on :8000):

```bash
cosim/webapp/dev.sh
```

### Prerequisites

The backend shells out to the real toolchain, so it must be installed and on
PATH: `node`, `sbt`, `verilator`, `spike`, and a RISC-V bare-metal gcc
(`riscv64-elf-gcc` + `riscv64-elf-binutils`, or `riscv64-unknown-elf-*`). On
macOS:

```bash
brew install node verilator riscv64-elf-gcc riscv64-elf-binutils dtc
brew tap riscv-software-src/riscv && brew install riscv-isa-sim   # spike
```

`GET /api/health` reports which tools it found.

## What you can do from the site

- **Tests** — generate a named batch (folder name, number of tests, instructions
  per test, mix: `mixed` = arithmetic + logic + memory, `arithmetic` = register
  ops only). Each batch is saved as a folder; browse the library and open a
  folder to see its programs. Generating does not run anything.
- **Run** — pick a folder and run it in lockstep against Spike. The success rate
  loads in place and the run becomes active (full KPIs under **Overview**).
- **Inject a bug** (Run side panel) — inject one or more built-in CPU bugs; they
  **stack** on the Chisel source and an injected bug is disabled until you
  **Reset**. The next Run rebuilds the (buggy) CPU and reports how many programs
  caught it — a good suite drops the pass rate. Reset restores the clean CPU.
- **Live log** — the raw gen/cosim output streams under the controls while a job
  runs.

## Architecture (why it's split)

The pipeline runs `sbt`, `verilator`, and `spike` — minutes of native compute
that **cannot** run in a Vercel serverless function. So the app is split:

- **Frontend** — a static Vite/React build. Deploys to Vercel as-is.
- **Backend** — `server.py`, a stdlib HTTP job server that runs the pipeline on
  a machine that has the toolchain. Long-running, not serverless.

The frontend finds the backend via `VITE_API_BASE`:

| Mode | `VITE_API_BASE` | How /api resolves |
| --- | --- | --- |
| `dev.sh` (Vite) | unset | Vite proxies `/api` → `:8000` |
| `serve.sh` (one origin) | `""` | backend serves the site too |
| Vercel + remote backend | `https://your-backend` | direct calls |
| Vercel, no backend | unset | Tests/Run disabled; browses bundled runs |

### Deploying the frontend to Vercel

Root directory `cosim/CPU-Dashboard`; `vercel.json` sets the Vite build and SPA
rewrites. With no `VITE_API_BASE`, the deployed site auto-loads the real runs
bundled in `public/runs/` so it isn't empty, and the Generate view shows a
"connect a backend" note instead of dead buttons. Point `VITE_API_BASE` at a
reachable `server.py` to enable live generation.

## API

| Method | Path | Body / result |
| --- | --- | --- |
| POST | `/api/generate` | `{name, tests, instrCnt, type}` → `{jobId}` (saves a folder) |
| GET | `/api/folders` / `/api/folders/<name>` | folder list / tests in a folder |
| POST | `/api/run` | `{folder, steps}` → `{jobId}` (runs vs current CPU) |
| POST | `/api/inject` | `{function}` → injects a bug (stacks) |
| POST | `/api/reset` | restore the clean CPU |
| GET | `/api/injected` | `{injected[], rtlDirty}` |
| GET | `/api/jobs/<id>?since=N` | `{status, log, logLen, run, error}` |
| GET | `/api/runs` / `/api/runs/<id>` | run summaries / one full run |
| GET | `/api/mutations` | available bug injections |
| GET | `/api/health` | toolchain + capabilities |

Jobs (generate, run) execute one at a time on a background worker (they share
the Verilator build dir); the UI polls `/api/jobs/<id>` and streams the log.
Inject/reset are synchronous — they only edit source; the rebuild happens on the
next run. Injected bugs are process state: restarting the server with bugs
injected leaves the source mutated, so Reset before stopping it (or `git
checkout -- src/main/scala/`).

## Custom CPU

The **Run** view has a CPU selector. You can run test folders against the
built-in DINO (Chisel, bug-injectable) or against **uploaded SystemVerilog**.

- **Upload .sv** — pick one or more `.sv` files. They're built with Verilator in
  place of the Chisel output and used for subsequent runs.
- **Download sample** — grabs the current DINO as `dino-sample.sv` (all modules
  in one file). Edit it and re-upload to test your own core.
- Bug injection is disabled while a custom CPU is selected (bugs edit the
  built-in Chisel source, which doesn't apply to uploaded Verilog). Switch back
  to built-in to inject.

**Interface contract.** The trace testbench (`tb_trace.cpp`) drives specific
signals, so an uploaded CPU must:

- have its **top module named `SingleCycleCPU`**;
- expose the `io_imem_address` / `io_imem_instruction` / `io_imem_good` /
  `io_imem_ready` and `io_dmem_*` (`valid`, `memread`, `memwrite`, `address`,
  `maskmode`, `sext`, `writedata`, `readdata`, `good`) ports;
- contain a register file reachable as `registers.regs[]` and a `pc` register
  (read each cycle via Verilator `--public-flat-rw`).

In practice this means a DINO-family core or one built to the same interface —
not an arbitrary RISC-V core. Start from the downloaded sample; if the build or
trace can't find those signals, the run fails with the Verilator/compile error
in the log.

API: `GET /api/cpus`, `POST /api/cpu {name, files:[{name,content}]}`,
`POST /api/cpu/select {name}` (`"__builtin__"` for DINO), `GET /api/cpu/sample`.
Uploaded CPUs live under `cosim/build/webapp/cpu/<name>/` and are git-ignored.
