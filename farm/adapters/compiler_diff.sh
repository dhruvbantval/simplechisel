#!/usr/bin/env bash
# Compile+run one C program at -O0 and -O2 with the same compiler, and print both
# outputs for the adapter to compare. If the two optimization levels disagree, the
# compiler miscompiled the program (or the program has undefined behaviour) -- the
# classic high-value differential-testing case.
set -uo pipefail
prog="$1"
cc="${CC:-clang}"

# A case can outlive its input, e.g. a generated program deleted from the build
# tree. Say so plainly rather than letting the compiler report "no input files",
# which reads as a compiler failure.
if [[ ! -f "$prog" ]]; then
    echo "MISSING_INPUT $prog"
    exit 4
fi

d="$(mktemp -d)"
trap 'rm -rf "$d"' EXIT

# An extensionless PE is only intermittently runnable from MSYS bash.
EXE=""
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) EXE=".exe" ;;
esac

# Build one optimization level and run it.
#
# On Windows a freshly written .exe intermittently fails to launch with 126 while
# an on-access scan holds it. Waiting does not clear this reliably; building to a
# fresh path does, so a failed launch is retried by recompiling.
#
# Sets BUILD_OUT and BUILD_RC. Returns non-zero only if compilation failed.
build_and_run() {
    local level="$1" tag="$2" attempt bin err delay
    for attempt in 1 2 3 4 5; do
        bin="$d/${tag}_${attempt}${EXE}"
        err="$d/err_${tag}_${attempt}"
        if ! "$cc" "$level" -o "$bin" "$prog" 2>"$err"; then
            BUILD_ERR="$(cat "$err")"
            return 1
        fi
        BUILD_OUT="$("$bin" 2>/dev/null)"; BUILD_RC=$?
        [[ $BUILD_RC -ne 126 && $BUILD_RC -ne 127 ]] && return 0
        # back off before rebuilding; the scan clears sooner when the machine is idle
        delay="0.$((attempt * 3))"
        sleep "$delay"
    done
    return 0    # the adapter reports exec_failed rather than a divergence
}

if ! build_and_run -O0 a0; then
    echo "COMPILE_FAIL O0"; printf '%s\n' "$BUILD_ERR" | sed 's/^/  /'; exit 3
fi
out0="$BUILD_OUT"; r0="$BUILD_RC"

if ! build_and_run -O2 a2; then
    echo "COMPILE_FAIL O2"; printf '%s\n' "$BUILD_ERR" | sed 's/^/  /'; exit 3
fi
out2="$BUILD_OUT"; r2="$BUILD_RC"

printf '===O0=== rc=%s\n%s\n===O2=== rc=%s\n%s\n===END===\n' "$r0" "$out0" "$r2" "$out2"
