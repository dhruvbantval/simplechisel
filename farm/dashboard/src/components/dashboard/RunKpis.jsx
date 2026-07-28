/*
 * KPI strip for the active run. Numbers flow (StatRow) and carry tone only where
 * the value is itself a state — failures go danger, a clean run goes success.
 */
import { useMemo } from 'react'
import { Stat, StatRow } from '../primitives/StatRow'
import { runKpis } from '../../data/metrics'

export default function RunKpis({ run }) {
  const kpis = useMemo(() => runKpis(run), [run])
  if (!kpis) return null

  return (
    <StatRow>
      <Stat
        value={`${kpis.passRate}%`}
        label="Pass rate"
        tone={kpis.failed === 0 ? 'success' : 'danger'}
        hint="Share of programs in this run that fully matched the golden model"
      />
      <Stat value={kpis.totalTests} label="Programs" hint="Assembly programs compared in this run" />
      <Stat value={kpis.passed} label="Passed" tone={kpis.passed > 0 ? 'success' : 'default'} />
      <Stat value={kpis.failed} label="Failed" tone={kpis.failed > 0 ? 'danger' : 'default'} />
      <Stat
        value={kpis.totalInstructions}
        label="Instructions"
        hint="Total instructions compared across all programs"
      />
      <Stat
        value={kpis.mismatches}
        label="Mismatches"
        tone={kpis.mismatches > 0 ? 'danger' : 'default'}
        hint="Instructions where the DUT disagreed with the golden model"
      />
    </StatRow>
  )
}
