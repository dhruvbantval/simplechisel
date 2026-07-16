/*
 * Campaign = mutation-testing roll-up across all runs. KPIs summarize the campaign,
 * then the catch-rate matrix shows, per injected bug, which programs caught it.
 * Needs mutation runs to be meaningful, so it has its own empty state pointing the
 * user at how to produce them.
 */
import { useMemo } from 'react'
import EmptyState from '../primitives/EmptyState'
import Section from '../primitives/Section'
import { Stat, StatRow } from '../primitives/StatRow'
import { campaignMatrix } from '../../data/metrics'
import CatchRateMatrix from './CatchRateMatrix'

export default function CampaignView({ runs }) {
  const matrix = useMemo(() => campaignMatrix(runs), [runs])

  if (matrix.rows.length === 0) {
    return (
      <Section title="Campaign">
        <EmptyState
          icon="campaign"
          title="No mutation runs yet"
          hint="Upload runs whose JSON sets a mutationLabel (an injected bug). The catch-rate matrix shows which programs detect each bug."
        />
      </Section>
    )
  }

  const totalBugs = matrix.rows.length
  const fullyCaught = matrix.rows.filter((r) => r.caughtCount === r.programCount && r.programCount > 0).length
  const missed = matrix.rows.filter((r) => r.caughtCount === 0).length
  const avgRate = Math.round(matrix.rows.reduce((s, r) => s + r.catchRate, 0) / totalBugs)

  return (
    <>
      <Section title="Campaign" description="Mutation testing: how well the test programs detect injected bugs.">
        <StatRow>
          <Stat value={totalBugs} label="Bugs" hint="Distinct mutation runs" />
          <Stat
            value={`${avgRate}%`}
            label="Avg catch rate"
            tone={avgRate >= 50 ? 'success' : 'warning'}
            hint="Average share of programs that catch a bug"
          />
          <Stat
            value={fullyCaught}
            label="Caught by all"
            tone="success"
            hint="Bugs every program detected"
          />
          <Stat
            value={missed}
            label="Missed by all"
            tone={missed > 0 ? 'danger' : 'default'}
            hint="Bugs no program detected — a coverage gap"
          />
        </StatRow>
      </Section>

      <Section
        title="Catch-rate matrix"
        description="Each cell: did this program catch this bug? Green ✓ = caught, red · = slipped through."
      >
        <CatchRateMatrix matrix={matrix} />
      </Section>
    </>
  )
}
