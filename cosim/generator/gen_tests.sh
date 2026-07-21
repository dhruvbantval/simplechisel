#!/usr/bin/env bash
# Generate random RV64I programs for the DINO/Spike cosimulation.
#
#   cosim/generator/gen_tests.sh
#   TESTS=20 cosim/generator/gen_tests.sh
#   SEED=14674157 TESTS=1 cosim/generator/gen_tests.sh
#
# Then:
#   STEPS=80 JOBS=4 cosim/run_cosim.sh
#
# riscv-dv itself is NOT vendored. On first run this clones it (pinned to
# RISCV_DV_REF), applies patches/, and drops config/ into it. Everything in
# this folder is DINO-specific; everything in riscv-dv/ is upstream and
# disposable -- delete it and it is rebuilt identically.
#
# Converted programs land in cosim/asm_tests/ next to the hand-written tests.
# riscv-dv's raw output is staged in a temp dir and discarded.
set -euo pipefail

GEN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COSIM_DIR="$(cd "$GEN_DIR/.." && pwd)"

TARGET="${TARGET:-rv64i}"
TEST="${TEST:-riscv_rv64i_dino_test}"
TESTS="${TESTS:-10}"
DEST="${DEST:-$COSIM_DIR/asm_tests}"
VENV="${VENV:-$GEN_DIR/.venv}"

# Instruction count per test and the instruction-mix "type". These parameterize
# the generated testlist so the web UI (and CLI) can ask for different programs
# without hand-editing config/testlist.yaml. All presets stay branch/jump-free:
# dino_convert.py flattens the program and drops labels, so a branch target
# would vanish and the program wouldn't assemble.
#   mixed      arithmetic + logic + load/store  (default)
#   arithmetic register ALU ops only, no memory (+no_load_store=1)
INSTR_CNT="${INSTR_CNT:-250}"
TYPE="${TYPE:-mixed}"
case "$TYPE" in
    mixed)      MIX_OPTS="" ;;
    arithmetic) MIX_OPTS="+no_load_store=1" ;;
    *)
        echo "error: unknown TYPE '$TYPE' (want: mixed|arithmetic)" >&2
        exit 2
        ;;
esac

# Pinned so generation stays reproducible and patches/ keeps applying. Bumping
# this may require refreshing the patch.
DV_URL="${RISCV_DV_URL:-https://github.com/chipsalliance/riscv-dv.git}"
DV_REF="${RISCV_DV_REF:-b7a0b4b0b51346a3c64f159f81ea262d867c14a9}"
DV_DIR="${RISCV_DV_DIR:-$GEN_DIR/riscv-dv}"

PATCH="$GEN_DIR/patches/0001-add-rv64i-target.patch"

# ---------------------------------------------------------------- riscv-dv ---
if [[ ! -d "$DV_DIR/.git" ]]; then
    echo "==> Cloning riscv-dv into $DV_DIR"
    rm -rf "$DV_DIR"
    git init -q "$DV_DIR"
    git -C "$DV_DIR" remote add origin "$DV_URL"
fi

if [[ "$(cat "$DV_DIR/.dino-ref" 2>/dev/null || true)" != "$DV_REF" ]]; then
    echo "==> Fetching riscv-dv @ ${DV_REF:0:12}"
    # GitHub serves an exact SHA to a shallow fetch; fall back to a full fetch
    # for branch/tag names or servers that refuse.
    git -C "$DV_DIR" fetch -q --depth 1 origin "$DV_REF" \
        || git -C "$DV_DIR" fetch -q origin
    git -C "$DV_DIR" checkout -q --detach FETCH_HEAD
    echo "$DV_REF" > "$DV_DIR/.dino-ref"
fi

# Reset upstream files first so re-running is idempotent -- `git apply` refuses
# an already-applied patch.
echo "==> Applying DINO patches + config to riscv-dv"
git -C "$DV_DIR" checkout -q -- .
git -C "$DV_DIR" apply "$PATCH"

# rv64i isn't an upstream target, so its testlist and core setting are ours.
mkdir -p "$DV_DIR/target/rv64i" "$DV_DIR/pygen/pygen_src/target/rv64i"
sed "s|+instr_cnt=250|+instr_cnt=$INSTR_CNT $MIX_OPTS|" \
    "$GEN_DIR/config/testlist.yaml" > "$DV_DIR/target/rv64i/testlist.yaml"
cp "$GEN_DIR/config/riscv_core_setting.py" \
   "$DV_DIR/pygen/pygen_src/target/rv64i/riscv_core_setting.py"

# -------------------------------------------------------------------- venv ---
if [[ ! -d "$VENV" ]]; then
    # pyvsc pulls in PyBoolector, which ships no wheel for Python 3.13+ and
    # fails to build from source. Pick an interpreter it actually supports
    # rather than whatever `python3` happens to be.
    PY="${PYTHON:-}"
    if [[ -z "$PY" ]]; then
        for c in python3.11 python3.12 python3.10; do
            if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
        done
    fi
    if [[ -z "$PY" ]]; then
        echo "error: need Python 3.10-3.12 for pyvsc/PyBoolector (found $(python3 --version))." >&2
        echo "       install one (e.g. 'brew install python@3.11') or set PYTHON=/path/to/python3.11" >&2
        exit 1
    fi
    echo "==> Creating venv at $VENV using $PY ($($PY --version))"
    "$PY" -m venv "$VENV"
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet -r "$GEN_DIR/requirements.txt"
fi

# run.py shells out to a bare `python3` (see riscv-dv's yaml/simulator.yaml),
# so the venv has to be on PATH -- calling .venv/bin/python is not enough.
export PATH="$VENV/bin:$PATH"

# pygen's test entry point does a relative `sys.path.append("pygen/")`, so it
# only imports cleanly when cwd happens to be the riscv-dv root. Put pygen on
# the path explicitly instead, so this script works from anywhere.
export PYTHONPATH="$DV_DIR/pygen:${PYTHONPATH:-}"

# ---------------------------------------------------------------- generate ---
RAW="$(mktemp -d "${TMPDIR:-/tmp}/riscv-dv-gen.XXXXXX")"
trap 'rm -rf "$RAW"' EXIT

seed_args=()
[[ -n "${SEED:-}" ]] && seed_args=(--seed "$SEED")

echo "==> Generating $TESTS x $TEST ($TARGET, type=$TYPE, instr_cnt=$INSTR_CNT)"
python3 "$DV_DIR/run.py" \
    --target "$TARGET" \
    --test "$TEST" \
    --simulator pyflow \
    --steps gen \
    --iterations "$TESTS" \
    -o "$RAW" \
    ${seed_args[@]+"${seed_args[@]}"}  # guard: macOS bash 3.2 + `set -u` trips on an empty array

# Clear out only programs from a previous generator run. cosim/asm_tests/ also
# holds hand-written tests (06_branches.S and friends) that are committed to
# git -- never wipe the whole directory.
mkdir -p "$DEST"
rm -f "$DEST/${TEST}"_*.S

echo "==> Converting to DINO bare-metal format -> $DEST"
python3 "$GEN_DIR/dino_convert.py" "$RAW" -o "$DEST"

# The seed record lives in the raw dir, which is about to be deleted. Print it
# so a specific program can be reproduced later with SEED=<n> TESTS=1.
if [[ -f "$RAW/seed.yaml" ]]; then
    echo
    echo "==> Seeds (rerun one with: SEED=<seed> TESTS=1 $0)"
    sed 's/^/    /' "$RAW/seed.yaml"
fi

echo
echo "==> Done. Run them with:"
echo "    STEPS=80 JOBS=4 cosim/run_cosim.sh"
