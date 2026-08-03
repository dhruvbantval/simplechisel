/*
 * Builds the regression trend from the universal record store (/api/records).
 *
 * Records are grouped by type, then by version of the thing under test. A version
 * is (source_sha + injected bugs), so a clean run and a bug-injected run of the
 * same commit remain distinct points.
 *
 * Returns [{ type, points: [{ sha, label, passRate, passed, total, bugs,
 * avgMetric, firstSeen }] }] with points ordered oldest to newest.
 */

/* config.bugs is cosim's injected-mutation list; other domains have none. */
function bugsOf(record) {
  const bugs = record?.config?.bugs
  if (Array.isArray(bugs)) return bugs.join(', ')
  return typeof bugs === 'string' ? bugs : ''
}

function shortSha(sha) {
  return sha ? String(sha).slice(0, 7) : 'unknown'
}

export function buildTrend(records) {
  const byType = new Map()

  for (const rec of records ?? []) {
    const type = rec?.type
    if (!type) continue

    const sha = rec.source_sha || ''
    const bugs = bugsOf(rec)
    // clean and bugged runs of the same commit are distinct versions
    const key = `${sha}::${bugs}`

    if (!byType.has(type)) byType.set(type, new Map())
    const versions = byType.get(type)

    if (!versions.has(key)) {
      versions.set(key, {
        sha, bugs,
        label: bugs ? `${shortSha(sha)} +${bugs}` : shortSha(sha),
        passed: 0, total: 0, metricSum: 0, metricCount: 0,
        firstSeen: rec.created_at || '',
      })
    }
    const v = versions.get(key)

    v.total += 1
    if (rec.status === 'pass') v.passed += 1

    const value = rec?.primary_metric?.value
    if (typeof value === 'number' && Number.isFinite(value)) {
      v.metricSum += value
      v.metricCount += 1
    }

    // the store lists newest first, so keep the earliest timestamp we see
    const at = rec.created_at || ''
    if (at && (!v.firstSeen || at < v.firstSeen)) v.firstSeen = at
  }

  return [...byType.entries()]
    .map(([type, versions]) => ({
      type,
      points: [...versions.values()]
        .sort((a, b) => String(a.firstSeen).localeCompare(String(b.firstSeen)))
        .map((v) => ({
          sha: v.sha,
          label: v.label,
          bugs: v.bugs,
          passed: v.passed,
          total: v.total,
          passRate: v.total ? Math.round((v.passed / v.total) * 100) : 0,
          avgMetric: v.metricCount ? v.metricSum / v.metricCount : 0,
          firstSeen: v.firstSeen,
        })),
    }))
    .sort((a, b) => a.type.localeCompare(b.type))
}

export default buildTrend
