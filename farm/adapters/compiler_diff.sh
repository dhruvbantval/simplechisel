#!/usr/bin/env bash
# Compile+run one C program at -O0 and -O2 with the same compiler, and print both
# outputs for the adapter to compare. If the two optimization levels disagree, the
# compiler miscompiled the program (or the program has undefined behaviour) -- the
# classic high-value differential-testing case.
set -uo pipefail
prog="$1"
cc="${CC:-clang}"
d="$(mktemp -d)"
trap 'rm -rf "$d"' EXIT

if ! "$cc" -O0 -o "$d/a0" "$prog" 2>"$d/err0"; then
    echo "COMPILE_FAIL O0"; sed 's/^/  /' "$d/err0"; exit 3
fi
if ! "$cc" -O2 -o "$d/a2" "$prog" 2>"$d/err2"; then
    echo "COMPILE_FAIL O2"; sed 's/^/  /' "$d/err2"; exit 3
fi

out0="$("$d/a0" 2>/dev/null)"; r0=$?
out2="$("$d/a2" 2>/dev/null)"; r2=$?
printf '===O0=== rc=%s\n%s\n===O2=== rc=%s\n%s\n===END===\n' "$r0" "$out0" "$r2" "$out2"
