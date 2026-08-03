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
import { useCallback, useEffect, useState } from 'react'
import Section from '../primitives/Section'
import EmptyState from '../primitives/EmptyState'
import Icon from '../primitives/Icon'
import LogPane from '../primitives/LogPane'
import MutationsPanel from './MutationsPanel'
import CpuPanel from './CpuPanel'
import CampaignPanel from './CampaignPanel'
import ExperimentTabs from './ExperimentTabs'
import InstallNeeded from './InstallNeeded'
import {
  getExperiments, getFolders, getInjected, getMutations, injectBug, resetBugs, startRun,
} from '../../data/api'
import { useJobs } from '../../data/jobs'
import styles from './RunView.module.css'

export default function RunView({ live, health, onRunReady, onNavigate, onCampaignDone }) {
  const [folders, setFolders] = useState([])
  const [folder, setFolder] = useState('')
  const [steps, setSteps] = useState(80)

  const [mutations, setMutations] = useState([])
  const [injected, setInjected] = useState([])
  const [customCpu, setCustomCpu] = useState(null) // active custom CPU name, or null=built-in

  // Which experiment (domain) is selected. The farm can run several; each is its
  // own page here. cosim has the rich CPU/folder/bug UI; others are simpler.
  const [experiments, setExperiments] = useState([])
  const [experiment, setExperiment] = useState('cosim')
  useEffect(() => {
    if (live) getExperiments().then(setExperiments).catch(() => setExperiments([]))
  }, [live])

  // Tracked in the job store so leaving this view does not cancel the run.
  const { startJob, jobFor } = useJobs()
  const job = jobFor('cosim:run')
  const busy = job.busy
  const log = job.log
  const error = job.error
  const result = job.result
    ? { passed: job.result.passed, total: job.result.totalTests,
        runId: job.result.runId, mutationLabel: job.result.mutationLabel }
    : null
  const label = busy ? job.label : null

  const [injectError, setInjectError] = useState(null)

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


  function onRun() {
    if (!folder) return
    startJob({
      key: 'cosim:run',
      kind: 'cosim-run',
      label: `Running “${folder}”${injected.length ? ` with ${injected.length} bug(s)` : ''}`,
      view: 'run',
      start: () => startRun({ folder, steps: Number(steps) }),
      describe: (snap) => snap.run
        ? `${snap.run.passed}/${snap.run.totalTests} tests passed`
        : undefined,
      onComplete: (snap) => { if (snap.run) onRunReady?.(snap.run) },
    })
  }

  const onInject = async (fn) => {
    setInjectError(null)
    try {
      const res = await injectBug(fn)
      if (!res.ok) setInjectError(res.error || 'inject failed')
      setInjected(res.injected ?? injected)
      refreshInjected()
    } catch (err) {
      setInjectError(err.message ?? String(err))
    }
  }

  const onReset = async () => {
    setInjectError(null)
    try {
      await resetBugs()
      setInjected([])
    } catch (err) {
      setInjectError(err.message ?? String(err))
    }
  }

  if (!live) {
    return (
      <Section title="Run">
        <EmptyState
          icon="play"
          title="No backend connected"
          hint="Running tests drives sbt, Verilator, and Spike on a backend (farm/webapp/server.py). Start it, or set VITE_API_BASE to a running instance, to run folders and inject bugs from here."
        />
      </Section>
    )
  }

  const tabs = experiments.length ? experiments
    : [{ type: 'cosim', label: 'CPU cosim' }]
  const toolsByType = health?.experimentTools ?? {}
  const missing = toolsByType[experiment]?.missing ?? []

  return (
    <>
      {/* Not disabled while a run is in flight: jobs are tracked per experiment
          in the job store and keep going across tab switches. */}
      <ExperimentTabs tabs={tabs} active={experiment} onSelect={setExperiment}
                      toolsByType={toolsByType} />

      {missing.length > 0 && (
        <InstallNeeded missing={missing} inWsl={toolsByType[experiment]?.wsl} />
      )}

      {experiment !== 'cosim' ? (
        <CampaignPanel live={live} experiment={tabs.find((e) => e.type === experiment)}
                       missingTools={missing} onDone={onCampaignDone} />
      ) : (
    <div className={styles.layout}>
      <div className={styles.main}>
        <Section title="Run a test folder" description="Pick a folder and run it against the CPU. Any injected bugs apply.">
          <CpuPanel onCpuChange={(name) => { setCustomCpu(name); if (name) setInjected([]) }} />
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
            <LogPane lines={log} label="Run output" />
          </Section>
        )}
      </div>

      <aside className={styles.side}>
        {injectError && (
          <p className={styles.error}><Icon name="alert" size={15} /> {injectError}</p>
        )}
        <MutationsPanel
          mutations={mutations}
          injected={injected}
          onInject={onInject}
          onReset={onReset}
          busy={busy}
          customCpu={customCpu}
        />
      </aside>
    </div>
      )}
    </>
  )
}
