/*
 * App shell. Owns top-level UI state (current view, mobile menu) and wires the
 * useRuns data hook into the layout. View switching is state-based (no router yet);
 * each view reads from the same run store so toggling the active run updates
 * everything consistently.
 */
import { useMemo, useState } from 'react'
import Sidebar from './components/layout/Sidebar'
import TopBar from './components/layout/TopBar'
import EmptyState from './components/primitives/EmptyState'
import Section from './components/primitives/Section'
import StateView from './components/primitives/StateView'
import OverviewView from './components/dashboard/OverviewView'
import RunsView from './components/dashboard/RunsView'
import CampaignView from './components/dashboard/CampaignView'
import UploadControl from './components/dashboard/UploadControl'
import { useRuns } from './data/useRuns'
import { globalSummary } from './data/metrics'
import { sampleRuns } from './data/sampleData'
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
    addRunFromFile,
    loadSamples,
    removeRun,
  } = useRuns()

  const [view, setView] = useState('overview')
  const [menuOpen, setMenuOpen] = useState(false)

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
        icon="upload"
        title="Upload a verification run to begin"
        hint="Drop a run JSON exported by the comparison harness. It's stored in your browser, becomes the active run, and is kept in history so you can switch between runs later."
        action={
          <div className={styles.emptyActions}>
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
          </main>
        </div>
      </div>
    </div>
  )
}
