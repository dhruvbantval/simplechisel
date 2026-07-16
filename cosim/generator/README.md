# Test generator

Generates random RV64I programs for the DINO/Spike cosimulation, using
[riscv-dv](https://github.com/chipsalliance/riscv-dv).

riscv-dv is **not** vendored here. This folder holds only the DINO-specific
pieces; `gen_tests.sh` clones riscv-dv on first run, pins it to a known commit,
and patches it. That's why there are 8 files here instead of a 60-file fork.

---

## Step 1 — Check prerequisites

```bash
python3.11 --version
git --version
```

If `python3.11` says "command not found":

```bash
brew install python@3.11
```

**Why 3.11:** the generator needs `pyvsc`, which fails to install on Python
3.13+. Your default `python3` may be newer — that's fine, the script finds a
3.11 on its own. If yours lives somewhere unusual, pass
`PYTHON=/path/to/python3.11`.

## Step 2 — Make the script executable (first time only)

```bash
chmod +x cosim/generator/gen_tests.sh
```

## Step 3 — Generate the tests

Run from the repository root:

```bash
cosim/generator/gen_tests.sh
```

The first run clones riscv-dv and builds a virtualenv, so it takes a couple of
minutes and needs network access. Later runs are offline and take seconds.

This writes 10 programs into `cosim/asm_tests/`, named
`riscv_rv64i_dino_test_0.S` … `_9.S`.

## Step 4 — Run them against DINO and Spike

```bash
STEPS=80 JOBS=4 cosim/run_cosim.sh
```

No path needed — `run_cosim.sh` already reads `cosim/asm_tests/`. Results land
in `cosim/build/results/<test_name>/result.json` as usual.

---

## Common variations

Generate a different number of programs:

```bash
TESTS=50 cosim/generator/gen_tests.sh
```

Reproduce an exact program — the same seed always gives the same program, and
every run prints the seeds it used:

```bash
SEED=14674157 TESTS=1 cosim/generator/gen_tests.sh
```

Write somewhere else instead of `cosim/asm_tests/`:

```bash
DEST=/tmp/mytests cosim/generator/gen_tests.sh
STEPS=80 JOBS=4 cosim/run_cosim.sh /tmp/mytests/
```

Start over from a clean riscv-dv checkout:

```bash
rm -rf cosim/generator/riscv-dv && cosim/generator/gen_tests.sh
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `TESTS` | `10` | Number of programs |
| `SEED` | random | Fixed seed, for reproducing a program |
| `DEST` | `cosim/asm_tests` | Where converted programs go |
| `PYTHON` | auto-detected | Interpreter used to build the venv |
| `TARGET` | `rv64i` | riscv-dv target |
| `TEST` | `riscv_rv64i_dino_test` | Test name in `config/testlist.yaml` |
| `RISCV_DV_REF` | pinned SHA | riscv-dv commit to check out |
| `RISCV_DV_URL` | chipsalliance/riscv-dv | Clone source |
| `RISCV_DV_DIR` | `cosim/generator/riscv-dv` | Where the clone lives |

## What's in this folder

Everything here is DINO-specific. Nothing upstream is copied in.

| Path | Purpose |
| --- | --- |
| `gen_tests.sh` | Sets up riscv-dv, generates, converts. The entry point. |
| `dino_convert.py` | Rewrites riscv-dv programs into DINO's bare-metal format. |
| `config/testlist.yaml` | The `riscv_rv64i_dino_test` definition — instruction mix. |
| `config/riscv_core_setting.py` | pygen core setting for rv64i (XLEN, supported ISA). |
| `patches/0001-add-rv64i-target.patch` | The riscv-dv source changes we need. |
| `requirements.txt` | Generation-only Python deps. |

`riscv-dv/` and `.venv/` are created by the script and git-ignored. Both are
disposable — delete either and the next run rebuilds it identically.

## How the riscv-dv setup works

`gen_tests.sh` does this before generating:

1. Clones `chipsalliance/riscv-dv` into `cosim/generator/riscv-dv/` (shallow).
2. Checks out the commit pinned in `RISCV_DV_REF` — currently `b7a0b4b`.
3. Runs `git checkout -- .` to reset, then applies `patches/`. Resetting first
   is what makes re-running safe; `git apply` refuses an already-applied patch.
4. Copies `config/` into the checkout (`target/rv64i/` and
   `pygen/pygen_src/target/rv64i/`).

The pin matters: it keeps generation reproducible and keeps the patch
applying. Upstream moving on cannot silently change your test programs.

### Why a patch is needed

Upstream riscv-dv has **no rv64i target** — its RV64 targets all bundle M/C/F/D,
which DINO's single-cycle CPU doesn't implement. The patch adds `rv64i` to
`run.py` (`mabi=lp64`, `isa=rv64i_zicsr_zifencei`), and guards two pygen test
modules with `if __name__ == "__main__"` so importing one doesn't kick off a
spurious generation run. The rv64i testlist and core setting aren't upstream
either, which is why they live in `config/`.

The patch header explains each change in full.

### Updating riscv-dv

```bash
RISCV_DV_REF=<new-sha> cosim/generator/gen_tests.sh
```

If the patch no longer applies, the run fails loudly at the `git apply` step
rather than generating something wrong. To refresh it:

```bash
cd cosim/generator/riscv-dv
# fix up the conflicting hunks by hand, then:
git diff -- run.py pygen/pygen_src/test/ > ../patches/0001-add-rv64i-target.patch
```

Keep the explanatory header at the top of the patch file when you regenerate.

## Generated vs hand-written tests

Both live in `cosim/asm_tests/`, kept apart by filename:

- `06_branches.S`, `07_loop_sum.S`, `08_gcd.S`, `09_fibonacci.S` — hand-written,
  committed to git.
- `riscv_rv64i_dino_test_*.S` — generated, git-ignored.

**Those four are not redundant.** `config/testlist.yaml` sets
`+no_branch_jump=1`, so generated programs contain zero branches and jumps —
they're straight-line arithmetic and load/store only. The four hand-written
tests are the suite's only branch, loop, and jump coverage.

Branches are off because `dino_convert.py` flattens riscv-dv's output and drops
labels, so a branch target would disappear and the program wouldn't assemble.
Generating branch tests means teaching the converter to keep referenced labels
first.

Each run deletes only the previously generated `${TEST}_*.S` files and leaves
the hand-written ones alone. To clear the generated ones by hand:

```bash
rm -f cosim/asm_tests/riscv_rv64i_dino_test_*.S
```

riscv-dv's raw output — the RVTEST boilerplate version, plus sim logs — is
staged in a temp dir and deleted when the script finishes. Only the converted,
DINO-ready programs are kept.

## Changing what gets generated

Edit `config/testlist.yaml`; it's copied into the checkout on every run. It
currently asks for 250 instructions per program with no branches/jumps, no
CSR/fence/privileged, and no compressed instructions — the subset DINO
implements. The knobs are riscv-dv's `gen_opts`, e.g. `+instr_cnt=500`.

## Troubleshooting

**`error: need Python 3.10-3.12 for pyvsc/PyBoolector`** — see Step 1.

**`error: patch does not apply`** — `RISCV_DV_REF` was moved to a commit the
patch doesn't fit. See "Updating riscv-dv" above.

**`ModuleNotFoundError: No module named 'vsc'` or `'pygen_src'`** — the venv is
incomplete or wasn't picked up. Rebuild it:

```bash
rm -rf cosim/generator/.venv && cosim/generator/gen_tests.sh
```

Running riscv-dv's `run.py` by hand usually hits this: it needs both the venv on
`PATH` and `pygen/` on `PYTHONPATH`. `gen_tests.sh` sets both — prefer it.

**`could not find 'init:' start marker`** from `dino_convert.py` — a generated
program didn't have the shape the converter expects, most likely because
`config/testlist.yaml` was edited to enable instructions DINO can't handle.

**Anything odd after editing the checkout by hand** — `riscv-dv/` is disposable:

```bash
rm -rf cosim/generator/riscv-dv && cosim/generator/gen_tests.sh
```

## Verified

Cloning fresh, patching, and generating with `SEED=14674157` reproduces the
output of the original `riscv-dv2` working copy byte-for-byte, raw and
DINO-converted. Re-running is idempotent.
