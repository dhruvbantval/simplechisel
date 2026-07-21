/*
 * App shell. Owns top-level UI state (current view, mobile menu) and wires the
 * useRuns data hook into the layout. View switching is state-based (no router yet);
 * each view reads from the same run store so toggling the active run updates
 * everything consistently.
 */
import { useEffect, useMemo, useState } from 'react'
import Sidebar from './components/layout/Sidebar'
import TopBar from './components/layout/TopBar'
import EmptyState from './components/primitives/EmptyState'
import Section from './components/primitives/Section'
import StateView from './components/primitives/StateView'
import OverviewView from './components/dashboard/OverviewView'
import RunsView from './components/dashboard/RunsView'
import CampaignView from './components/dashboard/CampaignView'
import TestsView from './components/dashboard/TestsView'
import RunView from './components/dashboard/RunView'
import UploadControl from './components/dashboard/UploadControl'
import { useRuns } from './data/useRuns'
import { globalSummary } from './data/metrics'
import { sampleRuns } from './data/sampleData'
import { getStaticRuns, probeLive } from './data/api'
import styles from './App.module.css'

export default function App() {
  const {
    status,
    loadError,
    records,
    runs,
    activeId,
    activeRun,
    selectRun,
    addRun,
    addRunFromFile,
    loadSamples,
    removeRun,
  } = useRuns()

  const [view, setView] = useState('overview')
  const [menuOpen, setMenuOpen] = useState(false)
  const [backend, setBackend] = useState({ live: false, health: null })

  useEffect(() => {
    probeLive().then(async (b) => {
      setBackend(b)
      // Backend-less deploy (e.g. Vercel static): seed the bundled real runs so
      // the site isn't empty. Only when nothing is stored yet, so we never
      // duplicate on reload (IndexedDB persists across visits).
      if (!b.live && status === 'ready' && records.length === 0) {
        const staticRuns = await getStaticRuns()
        for (const run of staticRuns) await addRun(run)
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once when load settles
  }, [status])

  // A fresh run from the backend: store it and make it active. Stay on Generate
  // so the success-rate card for the run just triggered remains visible; the run
  // is now the active one, so Overview shows its full KPIs when opened.
  const onRunReady = async (run) => {
    await addRun(run)
  }

  const summary = useMemo(() => globalSummary(runs), [runs])

  const navigate = (next) => {
    setView(next)
    setMenuOpen(false)
  }

  const selectAndShow = (id) => {
    selectRun(id)
    setView('overview')
  }

  const isEmpty = records.length === 0

  const emptyState = (
    <Section>
      <EmptyState
        icon={backend.live ? 'folder' : 'upload'}
        title={backend.live ? 'Generate your first tests' : 'Upload a verification run to begin'}
        hint={
          backend.live
            ? 'A backend is connected. Generate a folder of tests, then run it against the CPU — the success rate loads here, no JSON file needed. You can still upload a run if you have one.'
            : "Drop a run JSON exported by the comparison harness. It's stored in your browser, becomes the active run, and is kept in history so you can switch between runs later."
        }
        action={
          <div className={styles.emptyActions}>
            {backend.live && (
              <button type="button" className={styles.primaryCta} onClick={() => navigate('tests')}>
                Generate tests
              </button>
            )}
            <UploadControl onUpload={addRunFromFile} variant="dropzone" />
            <button type="button" className={styles.sampleLink} onClick={() => loadSamples(sampleRuns)}>
              or load sample data
            </button>
          </div>
        }
      />
    </Section>
  )

  return (
    <div className={styles.app}>
      <Sidebar
        view={view}
        onNavigate={navigate}
        onUpload={addRunFromFile}
        summary={summary}
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
      />

      <div className={styles.main}>
        <TopBar view={view} activeRun={view === 'overview' ? activeRun : null} onOpenMenu={() => setMenuOpen(true)} />

        <div className={styles.scrollArea}>
          <main className={styles.content}>
            {view === 'tests' ? (
              <TestsView live={backend.live} health={backend.health} />
            ) : view === 'run' ? (
              <RunView live={backend.live} onRunReady={onRunReady} onNavigate={navigate} />
            ) : (
            <StateView status={status} error={loadError} isEmpty={isEmpty} empty={emptyState}>
            {view === 'overview' &&
              (activeRun ? (
                <OverviewView key={activeId} run={activeRun} />
              ) : (
                <Section title="Overview">
                  <EmptyState
                    icon="overview"
                    title="No run selected"
                    hint="Pick a run from the Runs view to see its results here."
                  />
                </Section>
              ))}

            {view === 'runs' && (
              <RunsView
                records={records}
                activeId={activeId}
                onSelect={selectAndShow}
                onRemove={removeRun}
                onUpload={addRunFromFile}
              />
            )}

            {view === 'campaign' && <CampaignView runs={runs} />}
            </StateView>
            )}
          </main>
        </div>
      </div>
    </div>
  )
}
