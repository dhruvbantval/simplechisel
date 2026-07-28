/*
 * Regression trend — "the loop" made visible. Pass-rate per CPU version, in the
 * order they were first tested, so a version that regresses drops the line. Reads
 * the universal record store, so it's domain-agnostic: each experiment type is one
 * line (cosim today; ECG/SPICE/compiler would just appear as more lines).
 *
 * The chart is a single-series line per type (change-over-time): 2px accent line,
 * markers on each version, recessive axes/grid, only the latest point value
 * direct-labeled, and a hover tooltip. A table below carries the same numbers for
 * accessibility.
 */
import { useEffect, useMemo, useState } from 'react'
import Section from '../primitives/Section'
import EmptyState from '../primitives/EmptyState'
import DataTable from '../primitives/DataTable'
import { getRecords } from '../../data/api'
import { buildTrend } from '../../data/trend'
import styles from './TrendView.module.css'

export default function TrendView({ live }) {
  const [records, setRecords] = useState([])
  const [status, setStatus] = useState('loading')

  useEffect(() => {
    if (!live) { setStatus('nolive'); return }
    getRecords()
      .then((r) => { setRecords(r); setStatus('ready') })
      .catch(() => setStatus('error'))
  }, [live])

  const series = useMemo(() => buildTrend(records), [records])

  if (status === 'nolive') {
    return (
      <Section title="Regression trend">
        <EmptyState icon="campaign" title="No backend connected"
          hint="The trend reads the run store on the backend. Start it (farm/webapp/server.py) and run a few folders to build up history." />
      </Section>
    )
  }
  if (status === 'ready' && series.length === 0) {
    return (
      <Section title="Regression trend">
        <EmptyState icon="campaign" title="No runs yet"
          hint="Run a folder from the Run view — each run records a point here. Run the same tests on the clean CPU and again with a bug injected to see the line drop." />
      </Section>
    )
  }

  return (
    <div className={styles.wrap}>
      {series.map((s) => (
        <Section
          key={s.type}
          title={`${s.type} — pass rate over versions`}
          description="Each point is a version of the thing under test, oldest to newest. A drop is a regression."
        >
          <TrendChart points={s.points} />
          <VersionTable points={s.points} />
        </Section>
      ))}
    </div>
  )
}

function TrendChart({ points }) {
  const [hover, setHover] = useState(null)
  // Layout in a fixed viewBox; SVG scales responsively to the container width.
  const W = 720, H = 260, padL = 40, padR = 24, padT = 20, padB = 44
  const plotW = W - padL - padR, plotH = H - padT - padB
  const n = points.length
  const x = (i) => padL + (n === 1 ? plotW / 2 : (plotW * i) / (n - 1))
  const y = (v) => padT + plotH * (1 - v / 100)

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${y(p.passRate)}`).join(' ')
  const last = n - 1

  return (
    <div className={styles.chartWrap}>
      <svg viewBox={`0 0 ${W} ${H}`} className={styles.chart} role="img"
           aria-label="Pass rate over CPU versions">
        {/* recessive gridlines + y labels at 0/50/100% */}
        {[0, 50, 100].map((g) => (
          <g key={g}>
            <line x1={padL} x2={W - padR} y1={y(g)} y2={y(g)} className={styles.grid} />
            <text x={padL - 8} y={y(g) + 4} textAnchor="end" className={styles.axisText}>{g}%</text>
          </g>
        ))}
        {/* the single series line */}
        <path d={linePath} className={styles.line} fill="none" />
        {/* markers + x labels */}
        {points.map((p, i) => (
          <g key={p.sha}
             onMouseEnter={() => setHover({ i, p })}
             onMouseLeave={() => setHover(null)}>
            <circle cx={x(i)} cy={y(p.passRate)} r="5"
                    className={`${styles.marker} ${p.passRate === 100 ? styles.ok : p.passRate === 0 ? styles.bad : ''}`} />
            {/* generous invisible hit target */}
            <circle cx={x(i)} cy={y(p.passRate)} r="14" fill="transparent" />
            <text x={x(i)} y={H - padB + 18} textAnchor="middle" className={styles.axisText}>
              {p.label.length > 12 ? p.label.slice(0, 11) + '…' : p.label}
            </text>
          </g>
        ))}
        {/* direct-label only the latest point's value */}
        {n > 0 && (
          <text x={x(last)} y={y(points[last].passRate) - 12} textAnchor="middle"
                className={styles.lastLabel}>{points[last].passRate}%</text>
        )}
      </svg>
      {hover && (
        <div className={styles.tip} style={{
          left: `${(x(hover.i) / W) * 100}%`,
          top: `${(y(hover.p.passRate) / H) * 100}%`,
        }}>
          <div className={styles.tipSha}>{hover.p.label}</div>
          <div><strong>{hover.p.passRate}%</strong> · {hover.p.passed}/{hover.p.total} passed</div>
          <div className={styles.tipMuted}>
            {hover.p.bugs ? `bugs: ${hover.p.bugs}` : 'clean CPU'} · avg {Math.round(hover.p.avgMetric)} instr matched
          </div>
        </div>
      )}
    </div>
  )
}

function VersionTable({ points }) {
  const columns = [
    { key: 'label', header: 'Version' },
    { key: 'passRate', header: 'Pass rate', align: 'right', render: (r) => `${r.passRate}%` },
    { key: 'count', header: 'Passed / total', align: 'right', render: (r) => `${r.passed} / ${r.total}` },
    { key: 'bugs', header: 'Injected bugs', render: (r) => r.bugs || '—' },
  ]
  // newest first in the table
  const rows = [...points].reverse().map((p, i) => ({ id: i, ...p }))
  return <DataTable columns={columns} rows={rows} getRowKey={(r) => r.id} />
}
