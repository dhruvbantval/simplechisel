/*
 * App shell. Owns top-level UI state (current view, mobile menu) and the two data
 * sources the dashboard reads:
 *
 *   /api/records  — the universal store every experiment writes to. Drives the
 *                   Overview, the Trend and the sidebar summary, so all five
 *                   domains are visible without anything cosim-specific.
 *   useRuns()     — cosim campaign JSON held in IndexedDB. Drives the CPU-only
 *                   views (per-instruction diffs, the mutation catch-rate matrix)
 *                   that need detail the universal record deliberately omits.
 *
 * View switching is state-based (no router yet).
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import Sidebar from './components/layout/Sidebar'
import TopBar from './components/layout/TopBar'
import EmptyState from './components/primitives/EmptyState'
import Section from './components/primitives/Section'
import StateView from './components/primitives/StateView'
import FarmOverview from './components/dashboard/FarmOverview'
import OverviewView from './components/dashboard/OverviewView'
import RunsView from './components/dashboard/RunsView'
import CampaignView from './components/dashboard/CampaignView'
import TestsView from './components/dashboard/TestsView'
import RunView from './components/dashboard/RunView'
import TrendView from './components/dashboard/TrendView'
import UploadControl from './components/dashboard/UploadControl'
import { ToastProvider } from './components/primitives/Toast'
import { JobsProvider } from './data/jobs'
import { useRuns } from './data/useRuns'
import { farmSummary } from './data/records'
import { sampleRuns } from './data/sampleData'
import { getExperiments, getRecords, getStaticRuns, probeLive } from './data/api'
import styles from './App.module.css'

/* View state lives here so the providers can navigate from a toast. */
export default function App() {
  const [view, setView] = useState('overview')
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <ToastProvider>
      <JobsProvider onNavigate={setView}>
        <Shell view={view} setView={setView} menuOpen={menuOpen} setMenuOpen={setMenuOpen} />
      </JobsProvider>
    </ToastProvider>
  )
}

function Shell({ view, setView, menuOpen, setMenuOpen }) {
  const {
    status,
    loadError,
    records: cosimRuns,
    runs,
    activeId,
    activeRun,
    selectRun,
    addRun,
    addRunFromFile,
    loadSamples,
    removeRun,
  } = useRuns()

  const [backend, setBackend] = useState({ live: false, health: null })
  const [experiments, setExperiments] = useState([])
  const [farmRecords, setFarmRecords] = useState([])
  // bumped whenever a run finishes, to re-pull the record-derived views
  const [dataVersion, setDataVersion] = useState(0)

  useEffect(() => {
    probeLive().then(async (b) => {
      setBackend(b)
      if (b.live) {
        getExperiments().then(setExperiments).catch(() => setExperiments([]))
      }
      // Backend-less deploy (e.g. Vercel static): seed the bundled real runs so
      // the site isn't empty. Only when nothing is stored yet, so we never
      // duplicate on reload (IndexedDB persists across visits).
      if (!b.live && status === 'ready' && cosimRuns.length === 0) {
        const staticRuns = await getStaticRuns()
        for (const run of staticRuns) await addRun(run)
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once when load settles
  }, [status])

  // The sidebar summary counts every domain, so it reads the record store.
  useEffect(() => {
    if (!backend.live) return
    let alive = true
    getRecords()
      .then((r) => { if (alive) setFarmRecords(r) })
      .catch(() => { if (alive) setFarmRecords([]) })
    return () => { alive = false }
  }, [backend.live, dataVersion])

  const refreshFarm = useCallback(() => setDataVersion((v) => v + 1), [])

  // A fresh cosim run from the backend: store it and make it active.
  const onRunReady = useCallback(async (run) => {
    await addRun(run)
    refreshFarm()
  }, [addRun, refreshFarm])

  const farm = useMemo(() => farmSummary(farmRecords), [farmRecords])

  const navigate = (next) => {
    setView(next)
    setMenuOpen(false)
    // record-backed views should reflect anything that ran since they last loaded
    if (next === 'overview' || next === 'trend') refreshFarm()
  }

  const selectAndShow = (id) => {
    selectRun(id)
    setView('runs-detail')
  }

  const isEmpty = cosimRuns.length === 0

  const emptyState = (
    <Section>
      <EmptyState
        icon={backend.live ? 'folder' : 'upload'}
        title={backend.live ? 'No CPU runs yet' : 'Upload a verification run to begin'}
        hint={
          backend.live
            ? 'These views need a cosim run’s per-instruction detail. Generate a CPU test folder on the Tests tab, then run it from Experiments. Other domains’ results are on the Overview.'
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
        view={view === 'runs-detail' ? 'runs' : view}
        onNavigate={navigate}
        onUpload={addRunFromFile}
        farm={farm}
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
      />

      <div className={styles.main}>
        <TopBar
          view={view}
          activeRun={view === 'runs-detail' ? activeRun : null}
          onOpenMenu={() => setMenuOpen(true)}
        />

        <div className={styles.scrollArea}>
          <main className={styles.content}>
            {view === 'overview' ? (
              <FarmOverview live={backend.live} experiments={experiments} onNavigate={navigate} />
            ) : view === 'tests' ? (
              <TestsView live={backend.live} health={backend.health} experiments={experiments}
                         onNavigate={navigate} />
            ) : view === 'run' ? (
              <RunView
                live={backend.live}
                health={backend.health}
                onRunReady={onRunReady}
                onNavigate={navigate}
                onCampaignDone={refreshFarm}
              />
            ) : view === 'trend' ? (
              <TrendView live={backend.live} experiments={experiments} />
            ) : (
              <StateView status={status} error={loadError} isEmpty={isEmpty} empty={emptyState}>
                {view === 'runs-detail' &&
                  (activeRun ? (
                    <OverviewView key={activeId} run={activeRun} />
                  ) : (
                    <Section title="Run detail">
                      <EmptyState
                        icon="overview"
                        title="No run selected"
                        hint="Pick a run from CPU runs to see its per-instruction results here."
                      />
                    </Section>
                  ))}

                {view === 'runs' && (
                  <RunsView
                    records={cosimRuns}
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
