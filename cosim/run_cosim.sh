#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COSIM="$ROOT/cosim"
ASM_DIR="$COSIM/asm_tests"
BUILD_DIR="$COSIM/build"
DINO_BUILD="${DINO_BUILD:-$BUILD_DIR/dino_verilator}"
RESULT_DIR="$BUILD_DIR/results"
CAMPAIGN_DIR="$BUILD_DIR/campaigns"

BASE="${BASE:-0x80000000}"
STEPS="${STEPS:-120}"
JOBS="${JOBS:-4}"
SPIKE_MEM="${SPIKE_MEM:-0x10000:0x10000,${BASE}:0x100000}"

# RISC-V bare-metal toolchain prefix. Upstream riscv-dv docs assume
# riscv64-unknown-elf-, but Homebrew's bottled toolchain is riscv64-elf-.
# Auto-detect: honor an explicit RISCV_PREFIX, else whichever gcc is on PATH.
if [[ -z "${RISCV_PREFIX:-}" ]]; then
    if command -v riscv64-unknown-elf-gcc >/dev/null 2>&1; then
        RISCV_PREFIX="riscv64-unknown-elf-"
    elif command -v riscv64-elf-gcc >/dev/null 2>&1; then
        RISCV_PREFIX="riscv64-elf-"
    else
        echo "[cosim] no RISC-V gcc found (riscv64-unknown-elf-gcc or riscv64-elf-gcc)" >&2
        echo "[cosim] install one, e.g. 'brew install riscv64-elf-gcc riscv64-elf-binutils'" >&2
        exit 3
    fi
fi
RISCV_GCC="${RISCV_PREFIX}gcc"
RISCV_OBJDUMP="${RISCV_PREFIX}objdump"
LIVE="${LIVE:-0}"
MUTATION_LABEL="${MUTATION_LABEL:-}"
KEEP_GOING="${KEEP_GOING:-1}"
RECURSIVE="${RECURSIVE:-0}"
RUN_ID="${RUN_ID:-run_$(date -u +%Y%m%dT%H%M%SZ)}"
CAMPAIGN_JSON="${CAMPAIGN_JSON:-$CAMPAIGN_DIR/$RUN_ID.json}"

mkdir -p "$DINO_BUILD" "$RESULT_DIR" "$CAMPAIGN_DIR"

cd "$ROOT"

# Rebuilding the CPU (sbt elaboration + Verilator) takes ~2 min and only matters
# when the RTL changed. Repeated runs over the same CPU (e.g. the web UI firing
# many Generate jobs) can reuse the built simulator. REBUILD=1 forces it;
# REBUILD=0 skips; unset auto-skips when the simulator already exists.
SIM_EXE="$DINO_BUILD/obj_dir/dino_trace"
if [[ "${REBUILD:-auto}" == "1" || ( "${REBUILD:-auto}" == "auto" && ! -x "$SIM_EXE" ) ]]; then
    echo "[cosim] generating debug Verilog"
    sbt "runMain dinocpu.SingleCycleCPUDebug"

    echo "[cosim] building DINO Verilator trace simulator"
    cp build_singlecyclecpu_nd/*.sv "$DINO_BUILD/"
    cp "$COSIM/tb_trace.cpp" "$DINO_BUILD/"
    (
        cd "$DINO_BUILD"
        verilator --cc --exe --build -j "$JOBS" -Wno-fatal \
            --public-flat-rw --top-module SingleCycleCPU \
            ./*.sv tb_trace.cpp -o dino_trace
    )
else
    echo "[cosim] reusing existing DINO simulator ($SIM_EXE); set REBUILD=1 to force"
fi

tests=()
add_test_input() {
    local input="$1"
    local path="$input"
    if [[ "$path" != /* && ! -e "$path" && -e "$ASM_DIR/$path" ]]; then
        path="$ASM_DIR/$path"
    fi

    if [[ -d "$path" ]]; then
        find_args=("$path")
        if [[ "$RECURSIVE" != "1" ]]; then
            find_args+=(-maxdepth 1)
        fi
        while IFS= read -r found; do
            tests+=("$found")
        done < <(find "${find_args[@]}" -type f -iname "*.s" | sort)
    elif [[ -f "$path" ]]; then
        tests+=("$path")
    else
        echo "[cosim] test input not found: $input" >&2
        exit 2
    fi
}

if (($#)); then
    for input in "$@"; do
        add_test_input "$input"
    done
else
    add_test_input "$ASM_DIR"
fi

if ((${#tests[@]} == 0)); then
    echo "[cosim] no assembly tests found in $ASM_DIR" >&2
    exit 2
fi

passes=0
failures=0
result_jsons=()
for test_path in "${tests[@]}"; do
    filename="$(basename "$test_path")"
    name="${filename%.*}"
    out="$RESULT_DIR/$name"
    mkdir -p "$out"

    elf="$out/$name.elf"
    dump="$out/$name.dump"
    imem="$out/$name.imem.hex"
    dino_trace="$out/dino.trace"
    spike_log="$out/spike.log"
    result_json="$out/result.json"

    echo "[cosim] assembling $name"
    "$RISCV_GCC" -march=rv64i -mabi=lp64 \
        -nostdlib -nostartfiles -Wl,-N -Wl,--no-relax -Ttext="$BASE" \
        -o "$elf" "$test_path"
    "$RISCV_OBJDUMP" -d "$elf" > "$dump"
    awk '/^[[:space:]]*[0-9a-fA-F]+:/ {print $2}' "$dump" > "$imem"

    if [[ "$LIVE" == "1" ]]; then
        echo "[cosim] streaming compare of DINO trace and Spike commit log for $name"
        if python3 "$COSIM/live_compare.py" \
            --dino-exe "$DINO_BUILD/obj_dir/dino_trace" \
            --imem "$imem" \
            --elf "$elf" \
            --steps "$STEPS" \
            --base "$BASE" \
            --spike-mem "$SPIKE_MEM" \
            --dino-stderr "$out/dino.stderr" \
            --spike-stderr "$out/spike.stderr"; then
            passes=$((passes + 1))
        else
            failures=$((failures + 1))
            if [[ "$KEEP_GOING" != "1" ]]; then
                exit 1
            fi
        fi
    else
        echo "[cosim] tracing DINO for $name"
        "$DINO_BUILD/obj_dir/dino_trace" "$imem" "$STEPS" "$BASE" > "$dino_trace"

        echo "[cosim] tracing Spike commit log for $name"
        spike --isa=rv64i -m"$SPIKE_MEM" --pc="$BASE" --log-commits \
            --instructions="$STEPS" --log="$spike_log" "$elf" \
            > "$out/spike.stdout" 2> "$out/spike.stderr"

        echo "[cosim] comparing $name"
        compare_args=(--test-name "$name" --json-out "$result_json" --rtl-dir "$DINO_BUILD")
        if [[ -n "$MUTATION_LABEL" ]]; then
            compare_args+=(--mutation-label "$MUTATION_LABEL")
        fi
        if python3 "$COSIM/compare_traces.py" "${compare_args[@]}" "$dino_trace" "$spike_log"; then
            passes=$((passes + 1))
        else
            failures=$((failures + 1))
            if [[ "$KEEP_GOING" != "1" ]]; then
                exit 1
            fi
        fi
        result_jsons+=("$result_json")
    fi
done

if [[ "$LIVE" != "1" && ${#result_jsons[@]} -gt 0 ]]; then
    merge_args=(--out "$CAMPAIGN_JSON" --run-id "$RUN_ID" --rtl-dir "$DINO_BUILD")
    if [[ -n "$MUTATION_LABEL" ]]; then
        merge_args+=(--mutation-label "$MUTATION_LABEL")
    fi
    python3 "$COSIM/merge_results.py" "${merge_args[@]}" "${result_jsons[@]}"
    echo "[cosim] campaign JSON: $CAMPAIGN_JSON"
fi

echo "[cosim] summary: $passes passed, $failures failed, ${#tests[@]} total"
if [[ "$failures" -gt 0 ]]; then
    exit 1
fi
