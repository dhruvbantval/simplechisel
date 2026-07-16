#!/usr/bin/env bash
# Generate random RV64I programs with riscv-dv's pyflow generator, convert them
# into DINO's bare-metal format, and drop them straight into cosim/asm_tests/
# alongside the hand-written tests.
#
#   cosim/generator/gen_tests.sh
#   TESTS=20 cosim/generator/gen_tests.sh
#   SEED=14674157 TESTS=1 cosim/generator/gen_tests.sh
#
# Then just:
#   STEPS=80 JOBS=4 cosim/run_cosim.sh
#
# riscv-dv's raw output (RVTEST boilerplate, trap handlers, sim logs) is staged
# in a temp dir and thrown away -- only the converted programs are kept.
set -euo pipefail

GEN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COSIM_DIR="$(cd "$GEN_DIR/.." && pwd)"

TARGET="${TARGET:-rv64i}"
TEST="${TEST:-riscv_rv64i_dino_test}"
TESTS="${TESTS:-10}"
DEST="${DEST:-$COSIM_DIR/asm_tests}"
VENV="${VENV:-$GEN_DIR/.venv}"

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

# run.py shells out to a bare `python3` (see yaml/simulator.yaml), so the venv
# has to be on PATH -- calling .venv/bin/python directly is not enough.
export PATH="$VENV/bin:$PATH"

# pygen's test entry point does a relative `sys.path.append("pygen/")`, so it
# only imports cleanly when cwd happens to be this directory. Put pygen on the
# path explicitly instead, so this script works from anywhere.
export PYTHONPATH="$GEN_DIR/pygen:${PYTHONPATH:-}"

RAW="$(mktemp -d "${TMPDIR:-/tmp}/riscv-dv-gen.XXXXXX")"
trap 'rm -rf "$RAW"' EXIT

seed_args=()
[[ -n "${SEED:-}" ]] && seed_args=(--seed "$SEED")

echo "==> Generating $TESTS x $TEST ($TARGET)"
python3 "$GEN_DIR/run.py" \
    --target "$TARGET" \
    --test "$TEST" \
    --simulator pyflow \
    --steps gen \
    --iterations "$TESTS" \
    -o "$RAW" \
    ${seed_args[@]+"${seed_args[@]}"}  # guard: macOS bash 3.2 + `set -u` trips on an empty array

# Clear out only programs from a previous generator run. cosim/asm_tests/ also
# holds hand-written tests (01_add_sub.S and friends) that are committed to git
# -- never wipe the whole directory.
mkdir -p "$DEST"
rm -f "$DEST/${TEST}"_*.S

echo "==> Converting to DINO bare-metal format -> $DEST"
python3 "$GEN_DIR/scripts/dino_convert.py" "$RAW" -o "$DEST"

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
