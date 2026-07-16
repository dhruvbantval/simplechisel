# Test generator

Generates random RV64I programs for the DINO/Spike cosimulation, using a
trimmed copy of [riscv-dv](https://github.com/google/riscv-dv).

---

## Step 1 — Check you have Python 3.10-3.12

```bash
python3.11 --version
```

If that prints a version, you're set. If it says "command not found":

```bash
brew install python@3.11
```

**Why it matters:** the generator needs `pyvsc`, which fails to install on
Python 3.13+. Your default `python3` may be newer — that's fine, the script
looks for a 3.11 automatically. If your interpreter is somewhere unusual,
point at it directly with `PYTHON=/path/to/python3.11`.

## Step 2 — Make the script executable (first time only)

```bash
chmod +x cosim/generator/gen_tests.sh
```

## Step 3 — Generate the tests

Run from the repository root:

```bash
cosim/generator/gen_tests.sh
```

The first run also creates a virtualenv and installs dependencies, so it takes
a couple of minutes. Later runs take a few seconds.

This writes 10 programs into `cosim/asm_tests/`, named
`riscv_rv64i_dino_test_0.S` … `_9.S`.

## Step 4 — Run them against DINO and Spike

```bash
STEPS=80 JOBS=4 cosim/run_cosim.sh
```

No path needed — `run_cosim.sh` already reads `cosim/asm_tests/`, so it picks
up the generated programs together with the hand-written ones. Results land in
`cosim/build/results/<test_name>/result.json` as usual.

---

## Common variations

Generate a different number of programs:

```bash
TESTS=50 cosim/generator/gen_tests.sh
```

Reproduce an exact program (the same seed always gives the same program). Each
run prints the seed it used:

```bash
SEED=14674157 TESTS=1 cosim/generator/gen_tests.sh
```

Write somewhere else instead of `cosim/asm_tests/`:

```bash
DEST=/tmp/mytests cosim/generator/gen_tests.sh
STEPS=80 JOBS=4 cosim/run_cosim.sh /tmp/mytests/
```

All options: `TESTS` (count, default 10), `SEED` (default random), `DEST`
(default `cosim/asm_tests`), `PYTHON` (interpreter for the venv), `TARGET`
(default `rv64i`), `TEST` (default `riscv_rv64i_dino_test`).

## Generated vs hand-written tests

Both live in `cosim/asm_tests/`, and they're kept apart by filename:

- `06_branches.S`, `07_loop_sum.S`, `08_gcd.S`, `09_fibonacci.S` — hand-written,
  committed to git.
- `riscv_rv64i_dino_test_*.S` — generated, git-ignored.

**Those four hand-written tests are not redundant.** `testlist.yaml` sets
`+no_branch_jump=1`, so generated programs contain zero branches and jumps —
they're straight-line arithmetic and load/store only. The four hand-written
tests are the only branch, loop, and jump coverage in the suite. Don't delete
them expecting the generator to cover that.

The reason branches are off: `dino_convert.py` flattens riscv-dv's output and
drops labels, so a branch target would disappear and the program wouldn't
assemble. Generating branch tests means teaching the converter to keep labels
whose instructions reference them first.

(The earlier `01`–`05`, `10`, `11` tests were removed — random RV64I streams
cover that ground. They're in git history if wanted.)

Each run deletes only the previously generated `${TEST}_*.S` files and leaves
the hand-written ones alone. To drop the generated ones by hand:

```bash
rm -f cosim/asm_tests/riscv_rv64i_dino_test_*.S
```

riscv-dv's raw output — the RVTEST boilerplate version of each program, plus
sim logs — is staged in a temp dir and deleted when the script finishes. Only
the converted, DINO-ready programs are kept. If you need to inspect the raw
form, run `run.py` directly with `-o <dir>` (see Troubleshooting for the env
vars it needs).

## Changing what gets generated

Edit `target/rv64i/testlist.yaml`. It currently asks for 250 instructions per
program with no branches/jumps, no CSR/fence/privileged, and no compressed
instructions — the subset DINO's single-cycle CPU implements. The knobs are
riscv-dv's `gen_opts`, e.g. `+instr_cnt=500` for longer programs.

## Troubleshooting

**`error: need Python 3.10-3.12 for pyvsc/PyBoolector`** — see Step 1.

**`ModuleNotFoundError: No module named 'vsc'` or `'pygen_src'`** — the venv is
incomplete or wasn't picked up. Rebuild it:

```bash
rm -rf cosim/generator/.venv && cosim/generator/gen_tests.sh
```

Note that running `run.py` by hand usually hits this, because it needs both the
venv on `PATH` and `pygen/` on `PYTHONPATH`. `gen_tests.sh` sets both — prefer it.

**`could not find 'init:' start marker`** from `dino_convert.py` — a generated
program didn't have the shape the converter expects, likely because
`testlist.yaml` was edited to enable instructions DINO can't handle.

---

## What this folder is

The upstream riscv-dv checkout is 264M; this is ~1.3M across 73 files — only
what's needed to generate RV64I programs.

riscv-dv has two generators: the SystemVerilog/UVM one (needs VCS or Questa)
and `pygen`, a pure-Python reimplementation used via `--simulator pyflow`. Only
pygen is vendored here, since it's the one that runs without a commercial
simulator.

**Kept:** `run.py`, `pygen/pygen_src/**`, the six `scripts/*.py` modules
`run.py` imports at load time, `scripts/dino_convert.py`, `yaml/simulator.yaml`,
`target/rv64i/testlist.yaml`.

**Dropped:** `.venv` (226M, rebuilt from `requirements.txt`), `docs` (18M),
`.git` (11M), `sample/` (2.1M), `src/` + `test/` + `euvm/` (the SV/UVM flow),
`pygen/experimental/` (unused prototype), `cov.py` and coverage/lint/CI config,
the non-rv64i `target/` dirs, and `yaml/iss.yaml` + `scripts/link.ld` (only used
by `run.py`'s `gcc_compile`/`iss_sim` steps — this flow runs `--steps gen`, and
`run_cosim.sh` does its own linking with `-Ttext=0x80000000`).

`pygen/pygen_src/target/` still has every ISA variant (~64K), so `TARGET=rv32imc`
only needs that target's `testlist.yaml`, copied from upstream riscv-dv.

**Verified:** regenerating with `SEED=14674157` reproduced the original
`riscv-dv2/out_2026-07-16/` output byte-for-byte, both raw and DINO-converted,
before that checkout was removed.

**Local change vs upstream:** `scripts/dino_convert.py` is not an upstream file.
Nothing else was modified, so re-vendoring from a newer riscv-dv means
re-copying the "kept" list.
