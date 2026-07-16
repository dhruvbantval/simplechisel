/*
 * Validates an uploaded object against the run JSON schema (docs/json-schema.md).
 * Returns { ok, errors } where errors is a list of human-readable strings keyed to
 * the schema. Kept dependency-free and forgiving about optional/nullable fields so
 * a hand-written run file (the original jsonFormat.txt was malformed) gets a clear,
 * actionable message rather than a stack trace.
 */

const isInt = (v) => typeof v === 'number' && Number.isFinite(v)
const isStr = (v) => typeof v === 'string'
const isBool = (v) => typeof v === 'boolean'
const isNullOr = (check) => (v) => v === null || check(v)

function validateInstruction(instr, testName, idx, errors) {
  const where = `test "${testName}" instruction[${idx}]`
  if (typeof instr !== 'object' || instr === null) {
    errors.push(`${where} must be an object.`)
    return
  }
  if (!isInt(instr.instrNumber)) errors.push(`${where}: "instrNumber" must be an integer.`)
  if (!isStr(instr.mnemonic)) errors.push(`${where}: "mnemonic" must be a string.`)
  if (!isBool(instr.passed)) errors.push(`${where}: "passed" must be true/false.`)

  if (typeof instr.registers !== 'object' || instr.registers === null) {
    errors.push(`${where}: "registers" must be an object with rd/rs1/rs2.`)
  }

  if (!isNullOr(isInt)(instr.imm)) errors.push(`${where}: "imm" must be an integer or null.`)
  if (!isNullOr(isInt)(instr.goldenValue)) errors.push(`${where}: "goldenValue" must be an integer or null.`)
  if (!isNullOr(isInt)(instr.dutValue)) errors.push(`${where}: "dutValue" must be an integer or null.`)

  if (instr.passed === false && (instr.mismatch === null || instr.mismatch === undefined)) {
    errors.push(`${where}: a failing instruction must include a "mismatch" object.`)
  }
  if (instr.mismatch != null) {
    const m = instr.mismatch
    if (!isStr(m.register)) errors.push(`${where}.mismatch: "register" must be a string (e.g. "x3" or "PC").`)
    if (!isInt(m.expected)) errors.push(`${where}.mismatch: "expected" must be an integer.`)
    if (!isInt(m.got)) errors.push(`${where}.mismatch: "got" must be an integer.`)
  }
}

function validateTest(test, idx, errors) {
  const where = `tests[${idx}]`
  if (typeof test !== 'object' || test === null) {
    errors.push(`${where} must be an object.`)
    return
  }
  const name = isStr(test.testName) ? test.testName : `#${idx}`
  if (!isStr(test.testName)) errors.push(`${where}: "testName" must be a string.`)
  if (!isBool(test.passed)) errors.push(`${where}: "passed" must be true/false.`)
  if (!isInt(test.totalInstructions)) errors.push(`${where}: "totalInstructions" must be an integer.`)
  if (!isNullOr(isInt)(test.firstMismatchInstr)) {
    errors.push(`${where}: "firstMismatchInstr" must be an integer or null.`)
  }
  if (!Array.isArray(test.instructions)) {
    errors.push(`${where}: "instructions" must be an array.`)
    return
  }
  test.instructions.forEach((instr, i) => validateInstruction(instr, name, i, errors))
}

export function validateRun(data) {
  const errors = []

  if (typeof data !== 'object' || data === null || Array.isArray(data)) {
    return { ok: false, errors: ['Top level must be a single run object (see docs/json-schema.md).'] }
  }

  if (!isStr(data.runId)) errors.push('"runId" must be a string.')
  if (!isStr(data.timestamp)) errors.push('"timestamp" must be an ISO-8601 string.')
  if (!isStr(data.rtlDir)) errors.push('"rtlDir" must be a string.')
  // mutationLabel is optional: a baseline run may omit it entirely (treated as null).
  if (data.mutationLabel !== undefined && !isNullOr(isStr)(data.mutationLabel)) {
    errors.push('"mutationLabel" must be a string or null.')
  }

  if (!Array.isArray(data.tests)) {
    errors.push('"tests" must be an array.')
  } else if (data.tests.length === 0) {
    errors.push('"tests" must contain at least one test.')
  } else {
    data.tests.forEach((test, i) => validateTest(test, i, errors))
  }

  return { ok: errors.length === 0, errors }
}

/* Parse + validate a raw file string in one step, distinguishing JSON syntax
 * errors from schema errors so the upload UI can show the right message. */
export function parseAndValidate(text) {
  let data
  try {
    data = JSON.parse(text)
  } catch (err) {
    return { ok: false, errors: [`Not valid JSON: ${err.message}`], run: null }
  }
  const { ok, errors } = validateRun(data)
  return { ok, errors, run: ok ? data : null }
}
