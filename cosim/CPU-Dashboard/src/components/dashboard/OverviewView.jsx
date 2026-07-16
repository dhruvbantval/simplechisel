/*
 * Overview = the active run in focus. KPI strip up top, then the program results
 * table that drills into the divergence drawer. This is what the user sees when
 * they toggle a run "on" from the history.
 */
import { useState } from 'react'
import Section from '../primitives/Section'
import RunKpis from './RunKpis'
import TestsTable from './TestsTable'
import TestDetailDrawer from './TestDetailDrawer'

export default function OverviewView({ run }) {
  const [selectedTest, setSelectedTest] = useState(null)
  const test = run?.tests?.find((t) => t.testName === selectedTest) ?? null

  return (
    <>
      <Section
        title="Active run"
        description={
          run.mutationLabel
            ? `Mutation run · ${run.mutationLabel}`
            : 'Baseline run · no injected bug'
        }
      >
        <RunKpis run={run} />
      </Section>

      <Section
        title="Program results"
        description="Click a failing program to see the diverging instruction and both values."
      >
        <TestsTable run={run} onSelectTest={setSelectedTest} />
      </Section>

      <TestDetailDrawer open={Boolean(test)} onClose={() => setSelectedTest(null)} test={test} run={run} />
    </>
  )
}
