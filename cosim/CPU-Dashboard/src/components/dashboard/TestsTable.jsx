/*
 * Tests within the active run. One row per program; status as a chip, counts
 * right-aligned, the first failing instruction surfaced inline so the user knows
 * where to look before opening the drawer. Failing rows are clickable into the
 * drill-down; passing rows are de-emphasized (nothing to investigate).
 */
import Badge from '../primitives/Badge'
import DataTable from '../primitives/DataTable'
import Icon from '../primitives/Icon'
import { firstDivergence } from '../../data/metrics'
import styles from './TestsTable.module.css'

export default function TestsTable({ run, onSelectTest }) {
  const columns = [
    {
      key: 'testName',
      header: 'Program',
      sortable: true,
      render: (t) => <span className="u-mono">{t.testName}</span>,
    },
    {
      key: 'status',
      header: 'Status',
      sortable: true,
      sortValue: (t) => (t.passed ? 1 : 0),
      render: (t) => (
        <Badge variant={t.passed ? 'pass' : 'fail'} withIcon>
          {t.passed ? 'Pass' : 'Fail'}
        </Badge>
      ),
    },
    {
      key: 'totalInstructions',
      header: 'Instr.',
      align: 'right',
      sortable: true,
      hint: 'Instructions compared in this program',
    },
    {
      key: 'divergence',
      header: 'First divergence',
      render: (t) => {
        const d = firstDivergence(t)
        if (!d) return <span className="u-faint">—</span>
        return (
          <span className={styles.diverge}>
            <span className="u-faint">#{d.instrNumber}</span>
            <span className="u-mono u-strong">{d.mnemonic}</span>
            <span className="u-faint">→</span>
            <span className="u-mono">{d.mismatch?.register}</span>
          </span>
        )
      },
    },
    {
      key: 'action',
      header: '',
      align: 'right',
      render: (t) =>
        t.passed ? null : (
          <span className={styles.go}>
            Inspect <Icon name="arrowRight" size={14} />
          </span>
        ),
    },
  ]

  return (
    <DataTable
      columns={columns}
      rows={run.tests}
      getRowKey={(t) => t.testName}
      initialSort={{ key: 'status', dir: 'asc' }}
      onRowClick={(t) => (t.passed ? null : onSelectTest(t.testName))}
      rowClassName={(t) => (t.passed ? 'u-dim' : '')}
      emptyText="This run has no tests."
    />
  )
}
