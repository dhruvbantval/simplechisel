/*
 * Runs = the full upload history (the system-wide list). One row per stored run.
 * Selecting a row makes it the active run and jumps to Overview. The active run is
 * marked; deletion is a hover-revealed secondary action gated by an inline confirm
 * (no immediate destructive click — skill rule).
 */
import { useState } from 'react'
import Badge from '../primitives/Badge'
import DataTable from '../primitives/DataTable'
import EmptyState from '../primitives/EmptyState'
import Icon from '../primitives/Icon'
import Section from '../primitives/Section'
import Tooltip from '../primitives/Tooltip'
import UploadControl from './UploadControl'
import styles from './RunsView.module.css'

function formatTime(ms) {
  return new Date(ms).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function RunsView({ records, activeId, onSelect, onRemove, onUpload }) {
  const [confirmId, setConfirmId] = useState(null)

  const stop = (e) => e.stopPropagation()

  const columns = [
    {
      key: 'status',
      header: 'Status',
      sortable: true,
      sortValue: (r) => (r.run.tests.some((t) => !t.passed) ? 0 : 1),
      render: (r) => {
        const failed = r.run.tests.some((t) => !t.passed)
        return (
          <Badge variant={failed ? 'fail' : 'pass'} withIcon>
            {failed ? 'Failing' : 'Passing'}
          </Badge>
        )
      },
    },
    {
      key: 'runId',
      header: 'Run',
      sortable: true,
      sortValue: (r) => r.run.runId,
      render: (r) => (
        <span className={styles.runCell}>
          <span className="u-mono u-strong">{r.run.runId}</span>
          {r.id === activeId && (
            <Tooltip label="Currently shown in Overview" side="bottom">
              <span className={styles.activeDot} />
            </Tooltip>
          )}
        </span>
      ),
    },
    {
      key: 'kind',
      header: 'Kind',
      render: (r) =>
        r.run.mutationLabel ? (
          <Badge variant="mutation">{r.run.mutationLabel}</Badge>
        ) : (
          <Badge variant="baseline">baseline</Badge>
        ),
    },
    {
      key: 'rtlDir',
      header: 'RTL dir',
      truncate: true,
      render: (r) => <span className="u-mono u-muted">{r.run.rtlDir}</span>,
    },
    {
      key: 'passed',
      header: 'Pass / Fail',
      align: 'right',
      render: (r) => {
        const passed = r.run.tests.filter((t) => t.passed).length
        const failed = r.run.tests.length - passed
        return (
          <span className={styles.pf}>
            <span className={styles.pass}>{passed}</span>
            <span className="u-faint">/</span>
            <span className={failed > 0 ? styles.fail : 'u-faint'}>{failed}</span>
          </span>
        )
      },
    },
    {
      key: 'uploadedAt',
      header: 'Uploaded',
      align: 'right',
      sortable: true,
      render: (r) => <span className="u-muted">{formatTime(r.uploadedAt)}</span>,
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      render: (r) =>
        confirmId === r.id ? (
          <span className={styles.confirm} onClick={stop}>
            <span className="u-faint">Delete?</span>
            <button type="button" className={styles.confirmYes} onClick={() => { onRemove(r.id); setConfirmId(null) }}>
              Yes
            </button>
            <button type="button" className={styles.confirmNo} onClick={() => setConfirmId(null)}>
              No
            </button>
          </span>
        ) : (
          <Tooltip label="Delete run" side="left">
            <button
              type="button"
              className={styles.del}
              onClick={(e) => {
                stop(e)
                setConfirmId(r.id)
              }}
              aria-label={`Delete ${r.run.runId}`}
            >
              <Icon name="trash" size={15} />
            </button>
          </Tooltip>
        ),
    },
  ]

  if (records.length === 0) {
    return (
      <Section title="Runs">
        <EmptyState
          icon="runs"
          title="No runs uploaded yet"
          hint="Upload run JSON files to build up a history. Each upload is kept so you can toggle between them."
          action={<UploadControl onUpload={onUpload} variant="dropzone" />}
        />
      </Section>
    )
  }

  return (
    <Section
      title="Runs"
      description="Every uploaded run is kept. Select one to inspect it in Overview; the newest upload is active by default."
      actions={<UploadControl onUpload={onUpload} label="Upload run" />}
    >
      <DataTable
        columns={columns}
        rows={records}
        getRowKey={(r) => r.id}
        initialSort={{ key: 'uploadedAt', dir: 'desc' }}
        onRowClick={(r) => onSelect(r.id)}
        rowClassName={(r) => (r.id === activeId ? styles.activeRow : '')}
      />
    </Section>
  )
}
