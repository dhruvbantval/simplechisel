/*
 * Run console. Pick a saved test folder and run it against the CPU in its
 * current state — clean, or carrying whatever bugs are injected in the side
 * panel. The success rate loads here and the run becomes active (Overview shows
 * full KPIs). Bugs stack until Reset; the CPU is rebuilt automatically when the
 * bug set changed.
 *
 * If there are no test folders yet, this points the user at the Tests view
 * rather than showing an empty dropdown.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import Section from '../primitives/Section'
import EmptyState from '../primitives/EmptyState'
import Icon from '../primitives/Icon'
import MutationsPanel from './MutationsPanel'
import {
  getFolders, getInjected, getMutations, injectBug, pollJob, resetBugs, startRun,
} from '../../data/api'
import styles from './RunView.module.css'

export default function RunView({ live, onRunReady, onNavigate }) {
  const [folders, setFolders] = useState([])
  const [folder, setFolder] = useState('')
  const [steps, setSteps] = useState(80)

  const [mutations, setMutations] = useState([])
  const [injected, setInjected] = useState([])

  const [busy, setBusy] = useState(false)
  const [label, setLabel] = useState(null)
  const [log, setLog] = useState([])
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const logRef = useRef(null)

  const refreshInjected = useCallback(() => {
    if (live) getInjected().then((s) => setInjected(s.injected ?? [])).catch(() => {})
  }, [live])

  useEffect(() => {
    if (!live) return
    getFolders().then((f) => {
      setFolders(f)
      setFolder((cur) => cur || f[0]?.name || '')
    }).catch(() => setFolders([]))
    getMutations().then(setMutations).catch(() => setMutations([]))
    refreshInjected()
  }, [live, refreshInjected])

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [log])

  async function onRun() {
    if (!folder) return
    setBusy(true)
    setLabel(`Running “${folder}”${injected.length ? ` with ${injected.length} bug(s)` : ''}`)
    setLog([])
    setResult(null)
    setError(null)
    try {
      const { jobId } = await startRun({ folder, steps: Number(steps) })
      const snap = await pollJob(jobId, { onLog: (lines) => setLog((p) => [...p, ...lines]) })
      if (snap.status === 'error') {
        setError(snap.error || 'run failed')
      } else if (snap.run) {
        setResult({
          passed: snap.run.passed, total: snap.run.totalTests,
          runId: snap.run.runId, mutationLabel: snap.run.mutationLabel,
        })
        await onRunReady?.(snap.run)
      }
    } catch (err) {
      setError(err.message ?? String(err))
    } finally {
      setBusy(false)
      setLabel(null)
    }
  }

  const onInject = async (fn) => {
    setError(null)
    try {
      const res = await injectBug(fn)
      if (!res.ok) setError(res.error || 'inject failed')
      setInjected(res.injected ?? injected)
      refreshInjected()
    } catch (err) {
      setError(err.message ?? String(err))
    }
  }

  const onReset = async () => {
    setError(null)
    try {
      await resetBugs()
      setInjected([])
    } catch (err) {
      setError(err.message ?? String(err))
    }
  }

  if (!live) {
    return (
      <Section title="Run">
        <EmptyState
          icon="play"
          title="No backend connected"
          hint="Running tests drives sbt, Verilator, and Spike on a backend (cosim/webapp/server.py). Start it, or set VITE_API_BASE to a running instance, to run folders and inject bugs from here."
        />
      </Section>
    )
  }

  return (
    <div className={styles.layout}>
      <div className={styles.main}>
        <Section title="Run a test folder" description="Pick a folder and run it against the CPU. Any injected bugs apply.">
          {folders.length === 0 ? (
            <EmptyState
              icon="folder"
              title="No test folders yet"
              hint="Generate a batch first — that's where test folders come from."
              action={
                <button type="button" className={styles.primary} onClick={() => onNavigate?.('tests')}>
                  <Icon name="folder" size={16} /> Go to Tests
                </button>
              }
            />
          ) : (
            <div className={styles.runRow}>
              <label className={styles.field}>
                <span className={styles.fieldLabel}>Folder</span>
                <select value={folder} onChange={(e) => setFolder(e.target.value)} disabled={busy}>
                  {folders.map((f) => (
                    <option key={f.name} value={f.name}>{f.name} ({f.count})</option>
                  ))}
                </select>
              </label>
              <label className={styles.field}>
                <span className={styles.fieldLabel}>Steps</span>
                <input type="number" min="5" max="5000" step="5" value={steps}
                  onChange={(e) => setSteps(e.target.value)} disabled={busy} />
              </label>
              <button type="button" className={styles.primary} onClick={onRun} disabled={busy || !folder}>
                <Icon name="play" size={16} />
                {busy ? 'Running…' : 'Run'}
              </button>
            </div>
          )}
        </Section>

        {(busy || log.length > 0 || result || error) && (
          <Section title="Progress">
            {label && <p className={styles.status}><span className={styles.spinner} /> {label}</p>}
            {result && (
              <div className={`${styles.result} ${result.passed === result.total ? styles.ok : styles.bad}`}>
                <span className={styles.rate}>
                  {result.total ? Math.round((result.passed / result.total) * 100) : 0}%
                </span>
                <span className={styles.rateLabel}>
                  {result.passed}/{result.total} passed
                  {result.mutationLabel ? ` · bugs: ${result.mutationLabel}` : ' · clean CPU'}
                  <br />
                  <span className={styles.muted}>loaded as “{result.runId}” — see Overview</span>
                </span>
              </div>
            )}
            {error && <p className={styles.error}><Icon name="alert" size={15} /> {error}</p>}
            {log.length > 0 && <pre className={styles.log} ref={logRef}>{log.join('\n')}</pre>}
          </Section>
        )}
      </div>

      <aside className={styles.side}>
        <MutationsPanel
          mutations={mutations}
          injected={injected}
          onInject={onInject}
          onReset={onReset}
          busy={busy}
        />
      </aside>
    </div>
  )
}
