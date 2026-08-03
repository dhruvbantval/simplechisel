/*
 * Derivations over the universal record store (/api/records).
 *
 * Reads only fields the record contract guarantees, so every experiment type
 * rolls up the same way; metrics.js covers the cosim-only run JSON. Pure
 * functions, safe inside useMemo.
 */

const STATUSES = ['pass', 'fail', 'error']

/* Newest first, by created_at. */
function newestFirst(records) {
  return [...records].sort((a, b) =>
    String(b.created_at ?? '').localeCompare(String(a.created_at ?? '')))
}

/*
 * One roll-up per experiment type:
 *   { type, total, passed, failed, errored, passRate,
 *     metricName, metricUnit, latestMetric, avgMetric,
 *     lastRun, lastDetail, reasons }
 * `reasons` clusters failures by reason_code — the record contract's whole
 * purpose for that field.
 */
export function domainStats(records) {
  const byType = new Map()

  for (const rec of records ?? []) {
    const type = rec?.type
    if (!type) continue
    if (!byType.has(type)) {
      byType.set(type, {
        type, total: 0, passed: 0, failed: 0, errored: 0,
        metricName: rec?.primary_metric?.name ?? '',
        metricUnit: rec?.primary_metric?.unit ?? '',
        metricSum: 0, metricCount: 0,
        latestMetric: null, lastRun: '', lastDetail: '',
        reasons: new Map(),
      })
    }
    const d = byType.get(type)

    d.total += 1
    if (rec.status === 'pass') d.passed += 1
    else if (rec.status === 'fail') d.failed += 1
    else if (rec.status === 'error') d.errored += 1

    const value = rec?.primary_metric?.value
    if (typeof value === 'number' && Number.isFinite(value)) {
      d.metricSum += value
      d.metricCount += 1
    }

    // cluster non-passes by reason_code
    if (rec.status !== 'pass' && rec.reason_code) {
      d.reasons.set(rec.reason_code, (d.reasons.get(rec.reason_code) ?? 0) + 1)
    }

    const at = String(rec.created_at ?? '')
    if (at > d.lastRun) {
      d.lastRun = at
      d.lastDetail = rec.detail ?? ''
      d.latestMetric = typeof value === 'number' ? value : null
      if (rec?.primary_metric?.name) {
        d.metricName = rec.primary_metric.name
        d.metricUnit = rec.primary_metric.unit ?? ''
      }
    }
  }

  return [...byType.values()]
    .map((d) => ({
      ...d,
      passRate: d.total ? Math.round((d.passed / d.total) * 100) : 0,
      avgMetric: d.metricCount ? d.metricSum / d.metricCount : null,
      reasons: [...d.reasons.entries()]
        .map(([code, count]) => ({ code, count }))
        .sort((a, b) => b.count - a.count),
    }))
    .sort((a, b) => a.type.localeCompare(b.type))
}

/* Farm-wide totals for the sidebar and the overview header. */
export function farmSummary(records) {
  const list = records ?? []
  const counts = Object.fromEntries(STATUSES.map((s) => [s, 0]))
  for (const r of list) {
    if (counts[r?.status] !== undefined) counts[r.status] += 1
  }
  const domains = new Set(list.map((r) => r?.type).filter(Boolean))
  const total = list.length
  return {
    total,
    passed: counts.pass,
    failed: counts.fail,
    errored: counts.error,
    domains: domains.size,
    passRate: total ? Math.round((counts.pass / total) * 100) : 0,
  }
}

/* The N most recent records across every domain. */
export function recentRecords(records, n = 12) {
  return newestFirst(records ?? []).slice(0, n)
}

/* Human "3m ago" from an ISO timestamp. */
export function timeAgo(iso) {
  if (!iso) return ''
  const then = Date.parse(iso)
  if (Number.isNaN(then)) return ''
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000))
  if (secs < 60) return `${secs}s ago`
  const mins = Math.round(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

/* Format by magnitude: metrics range from instruction counts to microvolts. */
export function formatMetric(value) {
  if (value == null || !Number.isFinite(value)) return '—'
  const abs = Math.abs(value)
  if (abs === 0) return '0'
  if (abs < 0.001 || abs >= 1e6) return value.toExponential(2)
  if (abs < 1) return value.toFixed(3)
  if (abs < 100) return value.toFixed(2)
  return Math.round(value).toLocaleString()
}
