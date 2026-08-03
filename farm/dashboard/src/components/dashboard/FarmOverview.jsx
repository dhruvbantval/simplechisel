/*
 * Landing page: results for every experiment, read from /api/records.
 *
 * The per-instruction cosim drill-down lives in the CPU runs view, which reads
 * the richer cosim campaign JSON.
 */
import { useEffect, useMemo, useState } from 'react'
import Section from '../primitives/Section'
import EmptyState from '../primitives/EmptyState'
import Icon from '../primitives/Icon'
import Badge from '../primitives/Badge'
import { Stat, StatRow } from '../primitives/StatRow'
import { getRecords } from '../../data/api'
import { domainStats, farmSummary, recentRecords, timeAgo, formatMetric } from '../../data/records'
import styles from './FarmOverview.module.css'

export default function FarmOverview({ live, experiments, onNavigate }) {
  const [records, setRecords] = useState([])
  const [status, setStatus] = useState('loading')

  useEffect(() => {
    if (!live) { setStatus('nolive'); return }
    let alive = true
    getRecords()
      .then((r) => { if (alive) { setRecords(r); setStatus('ready') } })
      .catch(() => { if (alive) setStatus('error') })
    return () => { alive = false }
  }, [live])

  const summary = useMemo(() => farmSummary(records), [records])
  const domains = useMemo(() => domainStats(records), [records])
  const recent = useMemo(() => recentRecords(records, 10), [records])

  // labels come from farm.yaml; fall back to the raw type
  const labelFor = (type) =>
    experiments?.find((e) => e.type === type)?.label ?? type

  if (status === 'nolive') {
    return (
      <Section title="Overview">
        <EmptyState icon="overview" title="No backend connected"
          hint="The overview reads the farm's record store. Start the backend (farm/webapp/serve.sh) to see every domain's results here." />
      </Section>
    )
  }
  if (status === 'loading') {
    return <Section title="Overview"><p className={styles.muted}>Loading records…</p></Section>
  }
  if (status === 'error') {
    return (
      <Section title="Overview">
        <EmptyState icon="alert" title="Could not read the record store"
          hint="The backend is up but /api/records failed." />
      </Section>
    )
  }
  if (summary.total === 0) {
    return (
      <Section title="Overview">
        <EmptyState
          icon="campaign"
          title="No experiments have run yet"
          hint="Generate a batch of tests, then run it. Results appear here."
          action={
            <button type="button" className={styles.primary} onClick={() => onNavigate?.('tests')}>
              <Icon name="generate" size={16} /> Generate tests
            </button>
          }
        />
      </Section>
    )
  }

  return (
    <div className={styles.wrap}>
      <Section
        title="The farm"
        description="Results across every experiment, from the shared record store."
      >
        <StatRow>
          <Stat value={summary.total} label="Records" hint="One per experiment case run" />
          <Stat value={`${summary.passRate}%`} label="Pass rate"
                tone={summary.passRate >= 80 ? 'success' : summary.passRate >= 50 ? 'warning' : 'danger'}
                hint="Across every domain" />
          <Stat value={summary.failed} label="Failed"
                tone={summary.failed > 0 ? 'danger' : 'default'}
                hint="Ran, but disagreed with the golden reference" />
          <Stat value={summary.errored} label="Errored"
                tone={summary.errored > 0 ? 'warning' : 'default'}
                hint="Could not run — usually a missing tool" />
          <Stat value={summary.domains} label="Domains" hint="Experiment types with results" />
        </StatRow>
      </Section>

      <Section
        title="By domain"
        description="Pass rate and headline metric per experiment."
      >
        <div className={styles.domains}>
          {domains.map((d) => (
            <article key={d.type} className={styles.card}>
              <header className={styles.cardHead}>
                <button type="button" className={styles.cardTitle}
                        onClick={() => onNavigate?.('run')}>
                  {labelFor(d.type)}
                </button>
                <Badge variant={d.passRate === 100 ? 'pass' : d.passed === 0 ? 'fail' : 'warning'}>
                  {d.passRate}%
                </Badge>
              </header>

              <div className={styles.bar} aria-hidden="true">
                <span className={styles.barPass} style={{ flex: d.passed || 0 }} />
                <span className={styles.barFail} style={{ flex: d.failed || 0 }} />
                <span className={styles.barErr} style={{ flex: d.errored || 0 }} />
              </div>

              <dl className={styles.meta}>
                <div><dt>Cases</dt><dd>{d.passed}/{d.total} passed</dd></div>
                {d.metricName && (
                  <div>
                    <dt>{d.metricName}</dt>
                    <dd>
                      {formatMetric(d.latestMetric)}
                      {d.metricUnit ? <span className={styles.unit}> {d.metricUnit}</span> : null}
                      {d.metricCount > 1 && (
                        <span className={styles.muted}> · avg {formatMetric(d.avgMetric)}</span>
                      )}
                    </dd>
                  </div>
                )}
                {d.errored > 0 && <div><dt>Errored</dt><dd className={styles.warn}>{d.errored}</dd></div>}
                <div><dt>Last run</dt><dd>{timeAgo(d.lastRun) || '—'}</dd></div>
              </dl>

              {d.reasons.length > 0 && (
                <p className={styles.reasons}>
                  {d.reasons.map((r) => (
                    <span key={r.code} className={styles.reason}>
                      {r.code}<span className={styles.reasonN}>×{r.count}</span>
                    </span>
                  ))}
                </p>
              )}
            </article>
          ))}
        </div>
      </Section>

      <Section title="Recent" description="The newest records across every domain.">
        <ul className={styles.feed}>
          {recent.map((r) => (
            <li key={r.run_id} className={styles.feedRow}>
              <Badge variant={r.status === 'pass' ? 'pass' : r.status === 'fail' ? 'fail' : 'warning'} withIcon>
                {r.status}
              </Badge>
              <span className={styles.feedType}>{labelFor(r.type)}</span>
              <span className={styles.feedDetail} title={r.detail}>{r.detail}</span>
              <span className={styles.feedTime}>{timeAgo(r.created_at)}</span>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  )
}
