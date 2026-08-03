/*
 * Generate and browse saved test batches for a campaign experiment.
 *
 * Driven by the experiment's `generate:` block in farm.yaml. Re-using a batch
 * name appends to it.
 */
import { useCallback, useEffect, useState } from 'react'
import Section from '../primitives/Section'
import EmptyState from '../primitives/EmptyState'
import Icon from '../primitives/Icon'
import { deleteBatch, generateCases, getBatches, getCampaignCases } from '../../data/api'
import { useToast } from '../primitives/Toast'
import styles from './TestsView.module.css'

export default function BatchLibrary({ experiment, onNavigate }) {
  const { pushToast } = useToast()
  const type = experiment?.type
  const generate = experiment?.generate

  const [name, setName] = useState('')
  const [count, setCount] = useState(generate?.default ?? 5)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [note, setNote] = useState(null)
  const [batches, setBatches] = useState([])
  const [open, setOpen] = useState(null) // { name, cases: [] }

  const refresh = useCallback(() => {
    if (!type) return
    getBatches(type).then((d) => setBatches(d.batches ?? [])).catch(() => setBatches([]))
  }, [type])

  useEffect(() => {
    setName(''); setError(null); setNote(null); setOpen(null)
    setCount(generate?.default ?? 5)
    refresh()
  }, [type, generate, refresh])

  // Generation is a single synchronous request with no job id to poll, so it is
  // not tracked in the job store; the toast covers completion off-screen.
  async function onGenerate() {
    setBusy(true); setError(null); setNote(null)
    const label = experiment?.label ?? type
    try {
      const n = Math.max(1, Math.min(50, Number(count) || generate?.default || 5))
      const res = await generateCases(type, n, name.trim())
      setName('')
      setNote(`batch “${res.batch}”: +${res.count} case(s), ${res.total} total`)
      refresh()
      pushToast({
        tone: 'success',
        title: `${label}: tests generated`,
        body: `batch “${res.batch}” — +${res.count} case(s), ${res.total} total`,
        onClick: onNavigate ? () => onNavigate('tests') : undefined,
      })
    } catch (e) {
      const msg = e.message ?? String(e)
      setError(msg)
      pushToast({ tone: 'error', title: `${label}: generation failed`, body: msg })
    } finally {
      setBusy(false)
    }
  }

  async function onDelete(batchName) {
    setError(null)
    try {
      await deleteBatch(type, batchName)
      if (open?.name === batchName) setOpen(null)
      refresh()
    } catch (e) {
      setError(e.message ?? String(e))
    }
  }

  async function toggle(batchName) {
    if (open?.name === batchName) return setOpen(null)
    try {
      const d = await getCampaignCases(type, batchName)
      setOpen({ name: batchName, cases: d.cases ?? [] })
    } catch (e) {
      setError(e.message ?? String(e))
    }
  }

  if (!generate) {
    return (
      <Section title="Generate tests">
        <EmptyState
          icon="folder"
          title={`${experiment?.label ?? type} has no generator`}
          hint="Add a `generate:` block for this experiment in farm/farm.yaml to enable test generation."
        />
      </Section>
    )
  }

  return (
    <>
      <Section
        title="Generate a test batch"
        description={`Synthesizes ${generate.label}. Each batch is saved and can be run on its own from the Experiments view.`}
      >
        <div className={styles.form}>
          <label className={styles.field} style={{ gridColumn: '1 / -1' }}>
            <span className={styles.fieldLabel}>Batch name</span>
            <input
              type="text" placeholder="e.g. gain-sweep"
              value={name} onChange={(e) => setName(e.target.value)} disabled={busy}
            />
            <span className={styles.fieldHint}>
              Blank auto-names the batch. An existing name appends to it.
            </span>
          </label>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>Number of cases</span>
            <input type="number" min="1" max="50" value={count}
              onChange={(e) => setCount(e.target.value)} disabled={busy} />
          </label>
        </div>
        <div className={styles.genRow}>
          <button type="button" className={styles.primary} onClick={onGenerate} disabled={busy || !type}>
            <Icon name="generate" size={16} />
            {busy ? 'Generating…' : 'Generate tests'}
          </button>
        </div>
        {error && <p className={styles.error}><Icon name="alert" size={15} /> {error}</p>}
        {note && <p className={styles.note}>{note}</p>}
      </Section>

      <Section
        title="Test library"
        description="Saved batches. Open one to see its cases; run them from the Experiments view."
      >
        {batches.length === 0 ? (
          <EmptyState icon="folder" title="No batches yet"
            hint="Generate a batch above. Cases configured in farm.yaml run without one." />
        ) : (
          <ul className={styles.folders}>
            {batches.map((b) => (
              <li key={b.name} className={styles.folder}>
                <div className={styles.folderRow}>
                  <button type="button" className={styles.folderHead} onClick={() => toggle(b.name)}>
                    <Icon name="folder" size={16} />
                    <span className={styles.folderName}>{b.name}</span>
                    <span className={styles.folderCount}>
                      {b.count} case{b.count === 1 ? '' : 's'}
                    </span>
                  </button>
                  <button type="button" className={styles.del} onClick={() => onDelete(b.name)}
                          aria-label={`Delete batch ${b.name}`}>
                    <Icon name="trash" size={15} />
                  </button>
                </div>
                {open?.name === b.name && (
                  <ul className={styles.testList}>
                    {open.cases.map((c, i) => (
                      <li key={c.name ?? i} className={styles.testRow}>
                        <span className={styles.testName}>{c.name ?? `case ${i + 1}`}</span>
                        <span className={styles.testInstr}>
                          {Object.entries(c)
                            .filter(([k]) => k !== 'name' && k !== 'batch')
                            .map(([k, v]) => `${k}=${String(v).split('/').pop()}`)
                            .join('  ')}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </>
  )
}
