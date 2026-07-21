# Spike vs DINO cosimulation

Run from Ubuntu/WSL at the repository root:

```bash
STEPS=80 JOBS=4 cosim/run_cosim.sh
```

To run a folder of generated tests:

```bash
STEPS=80 JOBS=4 cosim/run_cosim.sh path/to/generated_tests/
```

To generate a fresh batch of random RV64I programs, use `cosim/generator/` (see
[generator/README.md](generator/README.md)). It writes them straight into
`cosim/asm_tests/`, so the plain command above then runs them:

```bash
cosim/generator/gen_tests.sh
STEPS=80 JOBS=4 cosim/run_cosim.sh
```

`cosim/asm_tests/` holds both kinds of test: `riscv_rv64i_dino_test_*.S` are
generated and git-ignored, while `06_branches.S`, `07_loop_sum.S`, `08_gcd.S`,
and `09_fibonacci.S` are hand-written and committed. The generator emits no
branches or jumps (`+no_branch_jump=1`), so those four are the suite's only
control-flow coverage.

The runner finds every `.S`/`.s` file in the folder, keeps going across tests, writes per-test
JSON files under `cosim/build/results/<test_name>/result.json`, and writes one campaign JSON under
`cosim/build/campaigns/`.

Folder search is flat by default. If the generated tests are nested in subfolders, add
`RECURSIVE=1`.

To run the automated bug-injection campaign:

```bash
STEPS=80 JOBS=4 python3 cosim/mutation/run_mutation_campaign.py
```

That script edits one CPU bug into the Chisel source, runs the normal cosim flow, writes a
campaign JSON, and restores the original source before trying the next bug. The combined mutation
summary is written to `cosim/build/campaigns/mutation_campaign_index.json`.

To choose one bug target by CPU function:

```bash
STEPS=80 JOBS=4 python3 cosim/mutation/run_mutation_campaign.py --function addi
STEPS=80 JOBS=4 python3 cosim/mutation/run_mutation_campaign.py --function sub
STEPS=80 JOBS=4 python3 cosim/mutation/run_mutation_campaign.py --function branch
```

To choose from a numbered menu:

```bash
python3 cosim/mutation/run_mutation_campaign.py --interactive
```

Supported function names are listed with:

```bash
python3 cosim/mutation/run_mutation_campaign.py --list
```

To check which mutation would run without starting the simulator:

```bash
python3 cosim/mutation/run_mutation_campaign.py --function addi --dry-run
```

To run the full-loop demo:

```bash
STEPS=12 JOBS=4 python3 cosim/full_loop_demo.py --function and
```

That command injects an `AND -> OR` bug, runs DINO and Spike on
`cosim/mutation/smoke_tests/and_bug.S`, writes the mutation JSON under
`cosim/build/campaigns/`, then copies the latest mutation JSON into
`cosim/CPU-Dashboard/examples/run_mutation.json`. Open the dashboard and click
`Load sample data` to see the bug caught in the UI.

For streaming comparison, use:

```bash
LIVE=1 STEPS=80 JOBS=4 cosim/run_cosim.sh
```

The runner:

1. Regenerates `SingleCycleCPUDebug` Verilog.
2. Builds a Verilator simulator with `--public-flat-rw`.
3. Assembles each `cosim/asm_tests/*.S` program for RV64I.
4. Runs DINO and Spike for the same instruction count.
5. Enables Spike's commit log with `--log-commits`.
6. Compares PC, instruction word, and all 32 registers after every instruction.

With `LIVE=1`, DINO and Spike are launched together and the comparator reads one DINO trace line
and one Spike commit-log line at a time. This is still not true paused lockstep: `spike` is an
external process and may run ahead. The comparator stops both processes at the first mismatch it
observes.

Programs are linked at `0x80000000`, and the DINO testbench sets the simulated PC to that same
base before the first instruction. This keeps `auipc`, jumps, and link-register behavior directly
comparable with Spike.
