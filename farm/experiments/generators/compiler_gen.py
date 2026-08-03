#!/usr/bin/env python3
"""Generate random C programs for the compiler-diff experiment — a tiny CSmith.

Each program does deterministic integer work and prints a checksum, so -O0 and -O2
must agree. Programs are written into the compiler corpus and echoed as cases.
Kept to well-defined integer arithmetic (no UB), so a divergence is a real
miscompile rather than the program's fault.

    python compiler_gen.py 5
"""
import json
import random
import sys
from pathlib import Path

# Generated programs live outside the curated corpus dir so the corpus glob does
# not double-count them. Files accumulate across runs because each saved batch
# keeps referencing its own; deleting a batch removes the files it owns.
OUT = Path(__file__).resolve().parents[1].parent / "build" / "generated" / "compiler"

OPS = ["+", "-", "*", "^", "&", "|"]


def random_program(seed: int) -> str:
    rng = random.Random(seed)
    n_vars = rng.randint(3, 6)
    lines = ["#include <stdio.h>", "int main(void){", "    unsigned long acc = 1u;"]
    for i in range(n_vars):
        lines.append(f"    unsigned long v{i} = {rng.randint(1, 9999)}u;")
    # a loop doing mixed integer ops into an accumulator
    n_iter = rng.randint(1000, 50000)
    lines.append(f"    for (unsigned i = 0; i < {n_iter}u; i++) {{")
    for _ in range(rng.randint(3, 7)):
        a = rng.randint(0, n_vars - 1)
        op = rng.choice(OPS)
        if op in ("*",):  # keep multiply from growing unboundedly
            lines.append(f"        acc = (acc {op} (v{a} | 1u)) & 0xFFFFFFFFu;")
        else:
            lines.append(f"        acc = (acc {op} v{a}) + i;")
    lines.append("    }")
    lines.append('    printf("%lu\\n", acc & 0xFFFFFFFFu);')
    lines.append("    return 0;")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    OUT.mkdir(parents=True, exist_ok=True)
    cases = []
    # a fresh prefix per run keeps names unique across batches
    base = random.randint(0, 10_000)
    while any(OUT.glob(f"gen_{base}_*.c")):
        base = random.randint(0, 10_000)
    for k in range(n):
        name = f"gen_{base}_{k}.c"
        path = OUT / name
        path.write_text(random_program(base + k))
        cases.append({"name": name, "program": str(path)})
    print(json.dumps(cases))


if __name__ == "__main__":
    main()
