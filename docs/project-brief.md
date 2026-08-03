# Prove It Universal: One Farm, Four Sciences

**Goal:** close the loop on the AutoExperiment Farm by making its core promise *literal* — each one of you plugs a real experiment **from field of your interest** into the same farm, and we run one big **cross‑domain
campaign**: logged, dashboarded.

---

## What "closing the loop" means (skip the AI part)

Today the farm runs **one** experiment type (CPU cosim). Closing the loop = many *different* experiments
flow through **one** pipeline, and results feed back so a bad new commit *shows up*.

```
   many experiment TYPES            ONE farm                       dashboard + AI
   (each = a tiny adapter)          run → collect                  aggregate → summarize
   ┌ CPU cosim ┐                                                   ┌────────────────────┐
   │ control   │ ──adapter──►  batch runner ──► artifacts +   ──►  │ pass/fail by domain │
   │ ECG       │              (parallel,        metadata           │ regression trend    │──┐
   │ SPICE     │               retry/resume)                       │                     │  │
   └ + new…     ┘                                                   └────────────────────┘  │
        ▲                                                                                   │
        └──────────────  fix / rerun on regression   ◄── THE LOOP ──────────────────────────┘
```

The **regression trend** (pass‑rate / metric over each commit) *is* the closed loop: any experiment,
any domain, that regresses lands on a line you can see.

## The one idea underneath all of it

Every experiment is the **same shape** you already built:
> **design‑under‑test vs a golden reference → pass/fail + artifacts.**

Four domains, one concept.

---

## The experiments 

| Owner | Experiment | Tool | DUT vs golden reference |
|---|---|---|---|
| **Team** ✅ done | RISC‑V DINO cosim (Chisel & Pryope) | Verilator + Spike | DINO vs Spike, per‑instruction | — |
| **Intern 1** — EE / robotics | **PID control‑loop cosim** → *stretch:* **Cortex‑M firmware on QEMU/Renode** | `python-control` + SciPy → `qemu-system-arm` / Renode | their controller vs `step_response()`; firmware self‑test exit code | 
| **Intern 2** — EE / biomed | **ECG R‑peak detection** → *stretch:* Hodgkin‑Huxley neuron | NeuroKit2 + `wfdb` (MIT‑BIH DB) → Brian2 / NEURON | detector vs cardiologist `.atr` beats (sensitivity / PPV) | 
| **Intern 3** — mech / EE | **SPICE circuit** (electrical) *or* **pendulum ODE** (mechanical) | `ngspice` / SciPy `solve_ivp` | V(out,t) or state(t) vs closed‑form, L∞ error < 1% | 

<details><summary>More options per domain (from research — pick per interest)</summary>

- **Robotics/EE:** robot‑arm forward↔inverse‑dynamics round‑trip (Robotics Toolbox); FreeRTOS POSIX‑port task‑trace test.
- **Biomed:** WFDB `bxb` QRS comparator (native golden comparator, like Spike); NEURON multi‑compartment regression; OpenSim inverse‑kinematics vs reference `.mot`.
- **Mech/EE:** control step‑response vs 2nd‑order spec (overshoot/settling); heat‑equation FEM vs Method‑of‑Manufactured‑Solutions; lid‑driven‑cavity CFD vs Ghia benchmark.
</details>

---

## The one other interesting thing to do — programming languages

**Differential compiler testing** is the *exact same idea* as our CPU cosim — two implementations of one
spec, same input, flag where they disagree — just pointed at **software** instead of hardware. And it's no
toy: this is literally how real compiler bugs get found (the **CSmith** fuzzer found *hundreds* of GCC/LLVM
bugs exactly this way).

| Owner | Experiment | Tool | DUT vs golden reference |
|---|---|---|---|
| **Bonus / anyone** — CS / compilers | **Differential compiler testing** → *stretch:* **CSmith** random‑program fuzzing | `csmith` + `gcc` / `clang` (or CPython vs PyPy) | same program, two implementations → outputs **must agree**; a divergence **is a compiler bug** |

- **Easy:** run a corpus of programs on **CPython vs PyPy** (or **gcc vs clang** at `-O0`), compare stdout → any mismatch = an implementation bug.
- **Optimizer bugs:** compile the same C at **`-O0` vs `-O2`** on both compilers → catches *miscompiles* (the classic, high‑value case).
- **Novel campaign:** **CSmith** generates thousands of random valid C programs → compile on gcc + clang at several `-O` levels → the farm runs them all, flags any output divergence, and saves the culprit program (+ an AI root‑cause line) as the artifact.

**Why it makes the farm special:** it turns *"run hundreds of tests across different programming languages"*
— literally the project's own words — into a real **bug‑finding platform**: the same machinery that catches
CPU bugs now catches **compiler** bugs. *One farm, hardware bugs **and** software bugs.* And it reuses skills
you already have — **CSmith ≈ your riscv‑dv generator**, **gcc‑vs‑clang ≈ your DINO‑vs‑Spike**.

---

## The mechanism that makes it universal: a 2‑function adapter

Adding a new experiment type = writing a tiny **adapter**, not touching the core:

```python
build_command(config) -> argv                              # how to launch it
parse_result(exit_code, stdout, artifacts_dir)             # what the outcome means
    -> { status, primary_metric{name,value,unit},
         reason_code, detail, metrics{}, artifacts[] }
```

The **core never knows what a "mismatch" is** — the adapter fills the meaning. Every adapter emits a
canonical `primary_metric` (cosim → `instructions_matched`, ECG → `sensitivity`, SPICE → `Linf_error`,
control → `overshoot`) so the dashboard charts **compare across domains for free**. New science = new
adapter, **zero schema change** — that's each one's core deliverable.

*(Under the hood: content‑addressed `run_id = hash(type + config + inputs + source_sha)` makes campaigns
idempotent + crash‑resumable — DVC/snakemake style. That's your "large pipelines, failure recovery.")*

---

## Who owns what (Please divide as per your interest)

| Intern | Domain adapter |
|---|---|
| **1** (robotics/EE) | control / embedded | the  (parallel + retry/resume) |
| **2** (biomed/EE) | ECG / neuron | the **AI failure summarizer** |
| **3** (mech/EE) | SPICE / physics |  |
| **all** | the shared **universal record + adapter interface** -- **batch runner**, **dashboard cross‑domain aggregation** |


## The final demo (Aug 8)

Hit **"run campaign"** → the farm launches hundreds of experiments across **four domains at once**
(a CPU, a control loop, an ECG, a circuit) → the dashboard fills with pass/fail **by domain** → click
any failure → its artifact (waveform / ECG strip / voltage trace) + a one‑line summary → finish with
*"…and here's a brand‑new experiment type, added in 30 lines."*

**One screen, four sciences** — the project's thesis, made undeniable, with each of us owning a piece.

---

## Notes

- **AI assistant / no API access:** the deterministic part (normalize failures into a `reason_code`,
  cluster by `(type, reason_code)`) already does ~80% of the value with **no model**. Scope the LLM
  summary as *optional* (template/heuristic now; a key later). Don't let it gate the universality story.
- **Reuse, don't rebuild:** the existing cosim runner becomes the **cosim adapter**; the dashboard reads
  the unified store instead of a cosim‑specific log. Prior art to borrow: MLflow (flat run schema),
  Sacred (config/source fingerprint), DVC + snakemake (content‑addressed resume/retry).
