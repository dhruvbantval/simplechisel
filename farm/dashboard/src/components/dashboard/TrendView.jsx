/*
 * Pass rate per version of the thing under test, one small multiple per
 * experiment type, read from the universal record store.
 *
 * Metric names come from farm.yaml; cosim's injected-bug column appears only for
 * domains that record one. Expanding a card shows the per-version table.
 */
import { useEffect, useMemo, useState } from 'react'
import Section from '../primitives/Section'
import EmptyState from '../primitives/EmptyState'
import DataTable from '../primitives/DataTable'
import Icon from '../primitives/Icon'
import { getRecords } from '../../data/api'
import { buildTrend } from '../../data/trend'
import { formatMetric } from '../../data/records'
import styles from './TrendView.module.css'

export default function TrendView({ live, experiments }) {
  const [records, setRecords] = useState([])
  const [status, setStatus] = useState('loading')
  const [expanded, setExpanded] = useState(null)

  useEffect(() => {
    if (!live) { setStatus('nolive'); return }
    let alive = true
    getRecords()
      .then((r) => { if (alive) { setRecords(r); setStatus('ready') } })
      .catch(() => { if (alive) setStatus('error') })
    return () => { alive = false }
  }, [live])

  const series = useMemo(() => buildTrend(records), [records])

  // labels and metric names come from farm.yaml
  const metaFor = (type) => {
    const e = experiments?.find((x) => x.type === type)
    return { label: e?.label ?? type, metric: e?.metric ?? '' }
  }

  if (status === 'nolive') {
    return (
      <Section title="Regression trend">
        <EmptyState icon="campaign" title="No backend connected"
          hint="The trend reads the shared record store on the backend. Start it (farm/webapp/serve.sh) and run a few experiments to build up history." />
      </Section>
    )
  }
  if (status === 'ready' && series.length === 0) {
    return (
      <Section title="Regression trend">
        <EmptyState icon="campaign" title="No runs yet"
          hint="Run an experiment, change what is under test, and run it again to build up history." />
      </Section>
    )
  }

  return (
    <Section
      title="Regression trend"
      description="Pass rate per version of the thing under test, oldest to newest. One chart per domain; a drop is a regression."
    >
      <div className={styles.grid}>
        {series.map((s) => {
          const meta = metaFor(s.type)
          const isOpen = expanded === s.type
          return (
            <article key={s.type}
                     className={`${styles.card} ${isOpen ? styles.cardOpen : ''}`}>
              <header className={styles.cardHead}>
                <div>
                  <h3 className={styles.cardTitle}>{meta.label}</h3>
                  <p className={styles.cardSub}>
                    {s.points.length} version{s.points.length === 1 ? '' : 's'}
                    {meta.metric ? ` · ${meta.metric}` : ''}
                  </p>
                </div>
                <span className={`${styles.headline} ${rateTone(s.points)}`}>
                  {s.points.length ? s.points[s.points.length - 1].passRate : 0}%
                </span>
              </header>

              {s.points.length < 2 ? (
                <SinglePoint point={s.points[0]} metric={meta.metric} />
              ) : (
                <Sparkline points={s.points} metric={meta.metric} />
              )}

              <button type="button" className={styles.expand}
                      onClick={() => setExpanded(isOpen ? null : s.type)}
                      aria-expanded={isOpen}>
                {isOpen ? 'Hide versions' : `Show ${s.points.length} version${s.points.length === 1 ? '' : 's'}`}
                <Icon name={isOpen ? 'cross' : 'runs'} size={13} />
              </button>

              {isOpen && <VersionTable points={s.points} metric={meta.metric} />}
            </article>
          )
        })}
      </div>
    </Section>
  )
}

function rateTone(points) {
  if (!points.length) return ''
  const r = points[points.length - 1].passRate
  return r === 100 ? styles.toneOk : r === 0 ? styles.toneBad : styles.toneWarn
}

/* Shown instead of a chart when only one version has been recorded. */
function SinglePoint({ point, metric }) {
  if (!point) return null
  return (
    <div className={styles.single}>
      <div className={styles.singleRow}>
        <span className={styles.singleLabel}>{point.label}</span>
        <span className={styles.singleVal}>{point.passed}/{point.total} passed</span>
      </div>
      {metric && (
        <div className={styles.singleRow}>
          <span className={styles.singleLabel}>avg {metric}</span>
          <span className={styles.singleVal}>{formatMetric(point.avgMetric)}</span>
        </div>
      )}
      <p className={styles.singleHint}>
        One version recorded. Run again after changing what is under test to see a
        trend.
      </p>
    </div>
  )
}

/* Compact multi-version chart; the latest value is direct-labelled. */
function Sparkline({ points, metric }) {
  const [hover, setHover] = useState(null)
  const W = 320, H = 96, padL = 28, padR = 16, padT = 14, padB = 20
  const plotW = W - padL - padR, plotH = H - padT - padB
  const n = points.length
  const x = (i) => padL + (n === 1 ? plotW / 2 : (plotW * i) / (n - 1))
  const y = (v) => padT + plotH * (1 - v / 100)
  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${y(p.passRate)}`).join(' ')

  return (
    <div className={styles.chartWrap}>
      <svg viewBox={`0 0 ${W} ${H}`} className={styles.chart} role="img"
           aria-label={`Pass rate across ${n} versions`}>
        {[0, 100].map((g) => (
          <g key={g}>
            <line x1={padL} x2={W - padR} y1={y(g)} y2={y(g)} className={styles.gridline} />
            <text x={padL - 6} y={y(g) + 3} textAnchor="end" className={styles.axisText}>{g}</text>
          </g>
        ))}
        <path d={linePath} className={styles.line} fill="none" />
        {points.map((p, i) => (
          <g key={`${p.sha}-${p.label}-${i}`}
             onMouseEnter={() => setHover({ i, p })}
             onMouseLeave={() => setHover(null)}>
            <circle cx={x(i)} cy={y(p.passRate)} r="3.5"
                    className={`${styles.marker} ${p.passRate === 100 ? styles.ok : p.passRate === 0 ? styles.bad : ''}`} />
            <circle cx={x(i)} cy={y(p.passRate)} r="11" fill="transparent" />
          </g>
        ))}
        <text x={x(n - 1)} y={y(points[n - 1].passRate) - 8} textAnchor="end"
              className={styles.lastLabel}>{points[n - 1].passRate}%</text>
      </svg>
      {hover && (
        <div className={styles.tip} style={{
          left: `${(x(hover.i) / W) * 100}%`,
          top: `${(y(hover.p.passRate) / H) * 100}%`,
        }}>
          <div className={styles.tipSha}>{hover.p.label}</div>
          <div><strong>{hover.p.passRate}%</strong> · {hover.p.passed}/{hover.p.total} passed</div>
          {metric && (
            <div className={styles.tipMuted}>
              avg {metric} {formatMetric(hover.p.avgMetric)}
            </div>
          )}
          {hover.p.bugs && <div className={styles.tipMuted}>bugs: {hover.p.bugs}</div>}
        </div>
      )}
    </div>
  )
}

function VersionTable({ points, metric }) {
  // injected bugs are cosim-only; omit the column elsewhere
  const hasBugs = points.some((p) => p.bugs)
  const columns = [
    { key: 'label', header: 'Version' },
    { key: 'passRate', header: 'Pass rate', align: 'right', render: (r) => `${r.passRate}%` },
    { key: 'count', header: 'Passed / total', align: 'right', render: (r) => `${r.passed} / ${r.total}` },
    ...(metric
      ? [{ key: 'avgMetric', header: `avg ${metric}`, align: 'right',
           render: (r) => formatMetric(r.avgMetric) }]
      : []),
    ...(hasBugs ? [{ key: 'bugs', header: 'Injected bugs', render: (r) => r.bugs || '—' }] : []),
  ]
  const rows = [...points].reverse().map((p, i) => ({ id: i, ...p }))
  return (
    <div className={styles.tableWrap}>
      <DataTable columns={columns} rows={rows} getRowKey={(r) => r.id} />
    </div>
  )
}
