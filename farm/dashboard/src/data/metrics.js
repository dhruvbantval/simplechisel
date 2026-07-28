/*
 * Pure derivation functions over run data. No React, no side effects — safe to
 * call inside useMemo. Every number the dashboard shows is computed here so the
 * UI stays declarative and the logic is testable in isolation.
 */

/* Format a signed 32-bit integer as zero-padded two's-complement hex, matching
 * the hexExpected/hexGot fields in the schema (e.g. -3 -> "0xFFFFFFFD"). */
export function formatHex(value) {
  if (value == null) return null
  const unsigned = value >>> 0
  return '0x' + unsigned.toString(16).toUpperCase().padStart(8, '0')
}

export function isMutation(run) {
  return Boolean(run?.mutationLabel)
}

/* KPIs for a single active run. */
export function runKpis(run) {
  if (!run) return null
  const tests = run.tests ?? []
  const passed = tests.filter((t) => t.passed).length
  const failed = tests.length - passed
  const totalInstructions = tests.reduce((sum, t) => sum + (t.instructions?.length ?? 0), 0)
  const mismatches = tests.reduce(
    (sum, t) => sum + (t.instructions?.filter((i) => !i.passed).length ?? 0),
    0,
  )
  const firstFailing = tests.find((t) => !t.passed) ?? null
  const passRate = tests.length === 0 ? 0 : Math.round((passed / tests.length) * 100)

  return {
    totalTests: tests.length,
    passed,
    failed,
    passRate,
    totalInstructions,
    mismatches,
    firstFailingTest: firstFailing ? firstFailing.testName : null,
  }
}

/* The first diverging instruction of a test, resolved from firstMismatchInstr
 * with a fallback to the first instruction whose passed === false. */
export function firstDivergence(test) {
  if (!test || test.passed) return null
  const byNumber = test.instructions?.find((i) => i.instrNumber === test.firstMismatchInstr)
  return byNumber ?? test.instructions?.find((i) => !i.passed) ?? null
}

/* Roll-up across the whole history, for the sidebar/global summary. */
export function globalSummary(runs) {
  const total = runs.length
  const mutationRuns = runs.filter(isMutation)
  const bugsCaught = mutationRuns.filter((r) => r.tests?.some((t) => !t.passed)).length
  const failingRuns = runs.filter((r) => r.tests?.some((t) => !t.passed)).length
  return {
    totalRuns: total,
    mutationRuns: mutationRuns.length,
    bugsCaught,
    failingRuns,
  }
}

/*
 * Catch-rate matrix across all mutation runs.
 *   rows  = one per mutation run (a "bug")
 *   cols  = the union of test names across those runs (programs)
 *   cell  = 'caught' (test failed under the bug), 'slipped' (test passed),
 *           or 'absent' (program wasn't run for this bug)
 * Plus per-bug catchCount / programCount for the catch-rate readout.
 */
export function campaignMatrix(runs) {
  const mutationRuns = runs.filter(isMutation)

  const programs = []
  for (const run of mutationRuns) {
    for (const t of run.tests ?? []) {
      if (!programs.includes(t.testName)) programs.push(t.testName)
    }
  }

  const rows = mutationRuns.map((run) => {
    const byName = new Map((run.tests ?? []).map((t) => [t.testName, t]))
    let caughtCount = 0
    let programCount = 0
    const cells = programs.map((name) => {
      const test = byName.get(name)
      if (!test) return { program: name, state: 'absent', test: null }
      programCount += 1
      const caught = !test.passed
      if (caught) caughtCount += 1
      return { program: name, state: caught ? 'caught' : 'slipped', test }
    })
    return {
      runId: run.runId,
      mutationLabel: run.mutationLabel,
      rtlDir: run.rtlDir,
      cells,
      caughtCount,
      programCount,
      catchRate: programCount === 0 ? 0 : Math.round((caughtCount / programCount) * 100),
    }
  })

  return { programs, rows }
}
