#!/usr/bin/env python3
"""Run a small DINO mutation campaign.

Each mutation temporarily edits one CPU source file, runs the existing cosim
flow, saves the campaign JSON, then restores the original source bytes before
trying the next mutation.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
COSIM = ROOT / "cosim"
CAMPAIGN_DIR = COSIM / "build" / "campaigns"


class Mutation:
    def __init__(self, name: str, description: str, edits: list[tuple[str, str, str]]):
        self.name = name
        self.description = description
        self.edits = edits


MUTATIONS = [
    Mutation(
        "negative_addi_extra_minus_one",
        "Negative ADDI immediates are one too negative.",
        [
            (
                "src/main/scala/dino.scala",
                """  alu.io.operation := aluControl.io.operation
  alu.io.inputx := Mux(control.io.src1, pc, registers.io.readdata1)
  alu.io.inputy := MuxCase(0.U, Array((control.io.src2 === 0.U) -> registers.io.readdata2,
                                      (control.io.src2 === 1.U) -> immGen.io.sextImm,
                                      (control.io.src2 === 2.U) -> 4.U))
""",
                """  val isNegativeAddi = instruction(6, 0) === "b0010011".U && funct3 === "b000".U && immGen.io.sextImm(63)
  val buggyImmediate = immGen.io.sextImm - Mux(isNegativeAddi, 1.U, 0.U)

  alu.io.operation := aluControl.io.operation
  alu.io.inputx := Mux(control.io.src1, pc, registers.io.readdata1)
  alu.io.inputy := MuxCase(0.U, Array((control.io.src2 === 0.U) -> registers.io.readdata2,
                                      (control.io.src2 === 1.U) -> buggyImmediate,
                                      (control.io.src2 === 2.U) -> 4.U))
""",
            )
        ],
    ),
    Mutation(
        "alu_sub_to_add",
        "SUB uses addition instead of subtraction.",
        [
            (
                "src/main/scala/components/alu.scala",
                """  .elsewhen (aluop === "b0100".U) { // sub
    when (wordinst === true.B) {
      io.result := signExtend32To64(operand1_32 - operand2_32)
    } .otherwise {
      io.result := io.inputx - io.inputy
    }
  }
""",
                """  .elsewhen (aluop === "b0100".U) { // sub
    when (wordinst === true.B) {
      io.result := signExtend32To64(operand1_32 + operand2_32)
    } .otherwise {
      io.result := io.inputx + io.inputy
    }
  }
""",
            )
        ],
    ),
    Mutation(
        "alu_and_to_or",
        "AND uses OR.",
        [
            (
                "src/main/scala/components/alu.scala",
                """  when (aluop === "b0110".U) { // and
    io.result := io.inputx & io.inputy
  }
""",
                """  when (aluop === "b0110".U) { // and
    io.result := io.inputx | io.inputy
  }
""",
            )
        ],
    ),
    Mutation(
        "alu_xor_to_and",
        "XOR uses AND.",
        [
            (
                "src/main/scala/components/alu.scala",
                """  .elsewhen (aluop === "b0000".U) { // xor
    io.result := io.inputx ^ io.inputy
  }
""",
                """  .elsewhen (aluop === "b0000".U) { // xor
    io.result := io.inputx & io.inputy
  }
""",
            )
        ],
    ),
    Mutation(
        "shift_amount_plus_one",
        "Shift operations use shift amount + 1.",
        [
            (
                "src/main/scala/components/alu.scala",
                """      io.result := signExtend32To64((operand1_32.asSInt >> operand2_32(4, 0)).asUInt) // arithmetic (signed)
                                                                                      // sraw takes 5 bits of op2
    } .otherwise { // sra
      io.result := (io.inputx.asSInt >> io.inputy(5, 0)).asUInt // sra takes 6 bits of op2
""",
                """      io.result := signExtend32To64((operand1_32.asSInt >> (operand2_32(4, 0) + 1.U)).asUInt) // arithmetic (signed)
                                                                                      // sraw takes 5 bits of op2
    } .otherwise { // sra
      io.result := (io.inputx.asSInt >> (io.inputy(5, 0) + 1.U)).asUInt // sra takes 6 bits of op2
""",
            ),
            (
                "src/main/scala/components/alu.scala",
                """      io.result := signExtend32To64(operand1_32 >> operand2_32(4, 0)) // srlw takes 5 bits of op2
    } .otherwise {
      io.result := io.inputx >> io.inputy(5, 0) // srl takes 6 bits of op2
""",
                """      io.result := signExtend32To64(operand1_32 >> (operand2_32(4, 0) + 1.U)) // srlw takes 5 bits of op2
    } .otherwise {
      io.result := io.inputx >> (io.inputy(5, 0) + 1.U) // srl takes 6 bits of op2
""",
            ),
            (
                "src/main/scala/components/alu.scala",
                """      io.result := signExtend32To64(operand1_32 << operand2_32(4, 0)) // sllw takes 5 bits of op2
    } .otherwise {
      io.result := io.inputx << io.inputy(5, 0) // sll takes 6 bits of op2
""",
                """      io.result := signExtend32To64(operand1_32 << (operand2_32(4, 0) + 1.U)) // sllw takes 5 bits of op2
    } .otherwise {
      io.result := io.inputx << (io.inputy(5, 0) + 1.U) // sll takes 6 bits of op2
""",
            ),
        ],
    ),
    Mutation(
        "slt_signed_as_unsigned",
        "SLT uses unsigned comparison.",
        [
            (
                "src/main/scala/components/alu.scala",
                """  .elsewhen (aluop === "b1001".U) { // slt
    io.result := (io.inputx.asSInt < io.inputy.asSInt).asUInt // signed
  }
""",
                """  .elsewhen (aluop === "b1001".U) { // slt
    io.result := (io.inputx < io.inputy).asUInt // signed
  }
""",
            )
        ],
    ),
    Mutation(
        "branch_beq_bne_swapped",
        "BEQ and BNE branch conditions are swapped.",
        [
            (
                "src/main/scala/components/nextpc.scala",
                """    when ( (io.funct3 === "b000".U & io.inputx === io.inputy)
         | (io.funct3 === "b001".U & io.inputx =/= io.inputy)
""",
                """    when ( (io.funct3 === "b000".U & io.inputx =/= io.inputy)
         | (io.funct3 === "b001".U & io.inputx === io.inputy)
""",
            )
        ],
    ),
    Mutation(
        "drop_load_write_enable",
        "Load instructions do not write back to rd.",
        [
            (
                "src/main/scala/components/control.scala",
                """      BitPat("b0000011") -> List(false.B, false.B, false.B,  1.U,  false.B,       0.U,      false.B,   2.U,  true.B,   true.B,    true.B,  false.B),
""",
                """      BitPat("b0000011") -> List(false.B, false.B, false.B,  1.U,  false.B,       0.U,      false.B,   2.U,  true.B,  false.B,    true.B,  false.B),
""",
            )
        ],
    ),
    Mutation(
        "wordop_zero_extend_addw_subw",
        "ADDW/SUBW zero-extend instead of sign-extending.",
        [
            (
                "src/main/scala/components/alu.scala",
                """  val signExtend32To64 = (input: UInt) => Cat(Fill(32, input(31)), input(31, 0))
  val operand1_32 = io.inputx(31, 0)
""",
                """  val signExtend32To64 = (input: UInt) => Cat(Fill(32, input(31)), input(31, 0))
  val zeroExtend32To64 = (input: UInt) => Cat(Fill(32, 0.U(1.W)), input(31, 0))
  val operand1_32 = io.inputx(31, 0)
""",
            ),
            (
                "src/main/scala/components/alu.scala",
                """      io.result := signExtend32To64(operand1_32 + operand2_32) // + results in width of max(width(op1), width(op2))
""",
                """      io.result := zeroExtend32To64(operand1_32 + operand2_32) // + results in width of max(width(op1), width(op2))
""",
            ),
            (
                "src/main/scala/components/alu.scala",
                """      io.result := signExtend32To64(operand1_32 - operand2_32)
""",
                """      io.result := zeroExtend32To64(operand1_32 - operand2_32)
""",
            ),
        ],
    ),
]

MUTATION_BY_NAME = {mutation.name: mutation for mutation in MUTATIONS}
FUNCTION_CHOICES = {
    "addi": "negative_addi_extra_minus_one",
    "sub": "alu_sub_to_add",
    "and": "alu_and_to_or",
    "xor": "alu_xor_to_and",
    "shift": "shift_amount_plus_one",
    "slt": "slt_signed_as_unsigned",
    "branch": "branch_beq_bne_swapped",
    "load": "drop_load_write_enable",
    "wordop": "wordop_zero_extend_addw_subw",
    "addw": "wordop_zero_extend_addw_subw",
    "subw": "wordop_zero_extend_addw_subw",
}


def print_choices() -> None:
    print("Available bug targets:")
    for idx, mutation in enumerate(MUTATIONS, 1):
        aliases = [name for name, target in FUNCTION_CHOICES.items() if target == mutation.name]
        alias_text = f" [{', '.join(aliases)}]" if aliases else ""
        print(f"  {idx}. {mutation.name}{alias_text}: {mutation.description}")


def choose_interactively() -> list[Mutation]:
    print_choices()
    print("  all. Run every mutation")
    choice = input("Choose bug target number/name/function: ").strip().lower()
    if choice == "all":
        return MUTATIONS
    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(MUTATIONS):
            return [MUTATIONS[idx - 1]]
    if choice in MUTATION_BY_NAME:
        return [MUTATION_BY_NAME[choice]]
    if choice in FUNCTION_CHOICES:
        return [MUTATION_BY_NAME[FUNCTION_CHOICES[choice]]]
    valid = ", ".join(sorted(set(FUNCTION_CHOICES) | set(MUTATION_BY_NAME) | {"all"}))
    raise SystemExit(f"Unknown choice {choice!r}. Valid choices: {valid}")


def select_mutations(args: argparse.Namespace) -> list[Mutation]:
    if args.interactive:
        return choose_interactively()

    names: list[str] = []
    if args.only:
        names.extend(args.only)
    if args.function:
        names.extend(FUNCTION_CHOICES[function] for function in args.function)
    if not names:
        return MUTATIONS

    selected: list[Mutation] = []
    seen: set[str] = set()
    for name in names:
        if name not in seen:
            selected.append(MUTATION_BY_NAME[name])
            seen.add(name)
    return selected


def apply_mutation(mutation: Mutation) -> dict[Path, bytes]:
    backups: dict[Path, bytes] = {}
    for rel_path, old, new in mutation.edits:
        path = ROOT / rel_path
        if path not in backups:
            backups[path] = path.read_bytes()
        text = path.read_text(encoding="utf-8")
        if text.count(old) != 1:
            raise RuntimeError(f"{mutation.name}: expected one match in {rel_path}")
        path.write_text(text.replace(old, new), encoding="utf-8")
    return backups


def restore(backups: dict[Path, bytes]) -> None:
    for path, original in backups.items():
        path.write_bytes(original)


def load_campaign(run_id: str) -> dict:
    path = CAMPAIGN_DIR / f"{run_id}.json"
    if not path.exists():
        return {"runId": run_id, "missing": True}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    failures = [
        {"testName": test["testName"], "firstMismatchInstr": test["firstMismatchInstr"]}
        for test in data.get("tests", [])
        if not test.get("passed", False)
    ]
    return {
        "runId": run_id,
        "jsonPath": str(path),
        "rtlDir": data.get("rtlDir"),
        "totalTests": data.get("totalTests"),
        "passed": data.get("passed"),
        "failed": data.get("failed"),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inject DINO bugs one at a time and run cosim.")
    parser.add_argument("tests", nargs="?", default=str(COSIM / "asm_tests"))
    parser.add_argument("--steps", default=os.environ.get("STEPS", "80"))
    parser.add_argument("--jobs", default=os.environ.get("JOBS", "4"))
    parser.add_argument("--only", action="append", choices=[m.name for m in MUTATIONS])
    parser.add_argument("--function", action="append", choices=sorted(FUNCTION_CHOICES))
    parser.add_argument("--interactive", action="store_true", help="Pick one mutation from a menu.")
    parser.add_argument("--dry-run", action="store_true", help="Show selected mutations without running cosim.")
    parser.add_argument("--list", action="store_true", help="List available mutations and exit.")
    args = parser.parse_args()

    if args.list:
        print_choices()
        return 0

    selected = select_mutations(args)
    if args.dry_run:
        for mutation in selected:
            print(f"{mutation.name}: {mutation.description}")
        return 0

    CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)

    summary = {"runs": []}
    overall_status = 0
    for mutation in selected:
        run_id = f"bug_{mutation.name}"
        print(f"[mutation] applying {mutation.name}: {mutation.description}", flush=True)
        backups: dict[Path, bytes] = {}
        try:
            backups = apply_mutation(mutation)
            env = os.environ.copy()
            env.update(
                {
                    "RUN_ID": run_id,
                    "MUTATION_LABEL": mutation.name,
                    "DINO_BUILD": str(COSIM / "build" / "bug_designs" / mutation.name),
                    "STEPS": str(args.steps),
                    "JOBS": str(args.jobs),
                    "KEEP_GOING": "1",
                }
            )
            result = subprocess.run([str(COSIM / "run_cosim.sh"), args.tests], cwd=ROOT, env=env)
            if result.returncode not in (0, 1):
                overall_status = result.returncode
        finally:
            restore(backups)
            print(f"[mutation] restored source after {mutation.name}", flush=True)

        run_summary = load_campaign(run_id)
        run_summary["mutationLabel"] = mutation.name
        run_summary["description"] = mutation.description
        summary["runs"].append(run_summary)

    out = CAMPAIGN_DIR / "mutation_campaign_index.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"[mutation] wrote {out}")
    return overall_status


if __name__ == "__main__":
    sys.exit(main())
