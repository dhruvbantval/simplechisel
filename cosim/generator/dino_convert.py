#!/usr/bin/env python3
"""Convert riscv-dv generated RV64I assembly tests into DINO's bare-metal
format and pair each program with its Spike golden log.

riscv-dv wraps every generated program in RVTEST-style boilerplate (CSR
setup, trap vector table, mtvec/mepc/mstatus init, tohost/fromhost ecall
exit sequence) that DINO's single-cycle CPU doesn't implement. The real
instruction stream lives between the 'init:' label (GPR seeding) and the
'la x31, test_done' line that kicks off riscv-dv's exit sequence. This
script extracts just that span and re-wraps it in DINO's expected shape:

    .section .text
    .globl _start
    _start:
        <instructions>
    loop:
        j loop

Usage:
    python3 scripts/dino_convert.py out_2026-07-16
"""
import argparse
import pathlib
import re
import sys

START_MARKER = re.compile(r"^init:\s*$")
STOP_MARKER = re.compile(r"^\s*la\s+x\d+,\s*test_done\s*$")
LABEL_RE = re.compile(r"^\s*([A-Za-z_.][\w.]*):\s*(.*)$")
# riscv-dv seeds a stack pointer with `la xN, user_stack_end`; that label
# lives in the boilerplate data section we strip out, so drop the line
# (DINO's bare-metal programs don't set up a stack).
DANGLING_LA = re.compile(r"^\s*la\s+x\d+,\s*\w*stack\w*\s*$")


def extract_body(asm_text, src_name):
    lines = asm_text.splitlines()
    start = next((i for i, l in enumerate(lines) if START_MARKER.match(l)), None)
    if start is None:
        raise ValueError(f"{src_name}: could not find 'init:' start marker")
    stop = next(
        (i for i in range(start, len(lines)) if STOP_MARKER.match(lines[i])), None)
    if stop is None:
        raise ValueError(f"{src_name}: could not find 'la x31, test_done' end marker")

    body = []
    for line in lines[start + 1:stop]:
        if not line.strip():
            continue
        m = LABEL_RE.match(line)
        instr = m.group(2).strip() if m else line.strip()
        if not instr:
            continue  # label-only line, nothing to emit
        if DANGLING_LA.match("  " + instr):
            continue  # stack-pointer setup referencing a stripped-out label
        body.append(instr)
    return body


def to_dino_asm(body, src_name):
    lines = [
        f"# Auto-converted from riscv-dv test {src_name} by dino_convert.py",
        ".section .text",
        ".globl _start",
        "_start:",
    ]
    lines += [f"    {instr}" for instr in body]
    lines += ["loop:", "    j loop", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out_dir",
                    help="riscv-dv run.py output dir (contains asm_test/ and spike_sim/)")
    ap.add_argument("-o", "--dest", default=None,
                    help="destination dir (default: <out_dir>/dino)")
    args = ap.parse_args()

    out_dir = pathlib.Path(args.out_dir)
    asm_dir = out_dir / "asm_test"
    if not asm_dir.is_dir() or not any(asm_dir.glob("*.S")):
        asm_dir = out_dir / "directed_asm_test"
    dest = pathlib.Path(args.dest) if args.dest else out_dir / "dino"
    dest.mkdir(parents=True, exist_ok=True)

    asm_files = sorted(asm_dir.glob("*.S"))
    if not asm_files:
        sys.exit(f"No .S files found in {asm_dir}")

    converted = 0
    for asm_path in asm_files:
        name = asm_path.stem
        body = extract_body(asm_path.read_text(), asm_path.name)
        dino_asm = to_dino_asm(body, asm_path.name)

        (dest / f"{name}.S").write_text(dino_asm)
        converted += 1
        print(f"{asm_path.name}: {len(body)} instructions -> {dest / (name + '.S')}")

    print(f"\nConverted {converted}/{len(asm_files)} programs -> {dest}")


if __name__ == "__main__":
    main()
