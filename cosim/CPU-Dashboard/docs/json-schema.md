# JSON Result File Schema

Every comparison run produces one JSON file. Multiple tests (assembly programs) can live in a single file. All files follow this schema.

## Top-Level Object

| Field | Type | Required | Description |
|---|---|---|---|
| `runId` | string | yes | Unique identifier for this run, e.g. `"run_001"` or `"run_bug_alu_xor_prog_add"` |
| `timestamp` | string (ISO 8601) | yes | When the simulation ran, e.g. `"2026-06-29T14:00:00Z"` |
| `rtlDir` | string | yes | Path to the RTL directory used, e.g. `"rtl/baseline"` or `"rtl/mutant_alu_xor"` |
| `mutationLabel` | string \| null | yes | Human-readable bug tag for mutation runs, e.g. `"alu_op_xor_replaced_with_and"`. `null` for baseline runs. |
| `totalTests` | integer | yes | Total number of tests in this run |
| `passed` | integer | yes | Number of tests that fully passed |
| `failed` | integer | yes | Number of tests that had at least one mismatch |
| `tests` | array of Test | yes | One entry per assembly program |

## Test Object

One test = one assembly program run through both the golden model and the DUT.

| Field | Type | Required | Description |
|---|---|---|---|
| `testName` | string | yes | Program name, e.g. `"add"`, `"branch_eq"` |
| `passed` | boolean | yes | True only if ALL instructions matched |
| `totalInstructions` | integer | yes | How many instructions were compared |
| `firstMismatchInstr` | integer \| null | yes | `instrNumber` of the first diverging instruction. `null` if all passed. 1-indexed. |
| `instructions` | array of Instruction | yes | One entry per compared instruction, in program order |

## Instruction Object

One instruction = one cycle where a register or PC write is compared.

| Field | Type | Required | Description |
|---|---|---|---|
| `instrNumber` | integer | yes | 1-indexed position in the program |
| `mnemonic` | string | yes | Assembly mnemonic: `"ADD"`, `"ADDI"`, `"SUB"`, `"XOR"`, `"AND"`, `"BEQ"`, `"LW"`, `"SW"`, etc. |
| `passed` | boolean | yes | True if golden and DUT agreed on the result |
| `registers` | Registers | yes | Source and destination register names |
| `imm` | integer \| null | yes | Immediate value for I/S/B/U/J-type instructions. `null` for R-type. |
| `goldenValue` | integer \| null | yes | Expected value from the golden model. `null` for store/branch instructions that don't write a register. |
| `dutValue` | integer \| null | yes | Actual value from the DUT. `null` for same reasons as above. |
| `mismatch` | Mismatch \| null | yes | Divergence detail. `null` if `passed` is true. |

### Registers Object

| Field | Type | Description |
|---|---|---|
| `rd` | string \| null | Destination register, e.g. `"x3"`. `null` for stores and branches. |
| `rs1` | string \| null | First source register. `null` if unused. |
| `rs2` | string \| null | Second source register. `null` for I-type (ADDI, LW, etc.). |

### Mismatch Object

Only present when `passed` is false. Describes the first (and usually only) divergence for this instruction.

| Field | Type | Description |
|---|---|---|
| `register` | string | Which register (or `"PC"` for branches) diverged, e.g. `"x3"` |
| `expected` | integer | Golden model's value (decimal) |
| `got` | integer | DUT's value (decimal) |
| `hexExpected` | string | Golden model's value as 32-bit hex, e.g. `"0x0000000C"` |
| `hexGot` | string | DUT's value as 32-bit hex, e.g. `"0x00000000"` |

## Notes

- **PC mismatches** (branches): `goldenValue`/`dutValue` are `null` because the compared entity is the PC, not a register write. The `mismatch.register` field will be `"PC"` and `expected`/`got` are PC values in bytes.
- **`firstMismatchInstr`** is 1-indexed to match `instrNumber`. The dashboard uses this to jump directly to the diverging row without scanning all instructions.
- **Signed integers**: `goldenValue`, `dutValue`, `expected`, `got`, and `imm` are all signed 32-bit integers in decimal.
- **Hex fields**: Always 10 characters (`0x` + 8 hex digits), zero-padded, representing 32-bit two's complement.

## Minimal Valid Example (all passing)

```json
{
  "runId": "run_001",
  "timestamp": "2026-06-29T14:00:00Z",
  "rtlDir": "rtl/baseline",
  "mutationLabel": null,
  "totalTests": 1,
  "passed": 1,
  "failed": 0,
  "tests": [
    {
      "testName": "add",
      "passed": true,
      "totalInstructions": 1,
      "firstMismatchInstr": null,
      "instructions": [
        {
          "instrNumber": 1,
          "mnemonic": "ADD",
          "passed": true,
          "registers": { "rd": "x3", "rs1": "x1", "rs2": "x2" },
          "imm": null,
          "goldenValue": 10,
          "dutValue": 10,
          "mismatch": null
        }
      ]
    }
  ]
}
```

## Minimal Failing Example

```json
{
  "runId": "run_002",
  "timestamp": "2026-06-29T14:05:00Z",
  "rtlDir": "rtl/bug_alu_add",
  "mutationLabel": "alu_add_output_zero",
  "totalTests": 1,
  "passed": 0,
  "failed": 1,
  "tests": [
    {
      "testName": "add",
      "passed": false,
      "totalInstructions": 1,
      "firstMismatchInstr": 1,
      "instructions": [
        {
          "instrNumber": 1,
          "mnemonic": "ADD",
          "passed": false,
          "registers": { "rd": "x3", "rs1": "x1", "rs2": "x2" },
          "imm": null,
          "goldenValue": 10,
          "dutValue": 0,
          "mismatch": {
            "register": "x3",
            "expected": 10,
            "got": 0,
            "hexExpected": "0x0000000A",
            "hexGot": "0x00000000"
          }
        }
      ]
    }
  ]
}
```

## Richer Examples

See `examples/` for complete files covering:
- `run_pass.json` — multiple tests, all passing, mix of ADD/ADDI/SUB
- `run_fail.json` — three tests, two failing, branch PC mismatch included
- `run_mutation.json` — XOR-replaced-with-AND mutation, `mutationLabel` set
