/*
 * Slim header above the content column. Shows the current view title and, when a
 * run is active, its identity (runId + status + RTL dir) so context is never lost
 * while scrolling. Hosts the mobile menu button that opens the Sidebar.
 */
import Badge from '../primitives/Badge'
import CopyButton from '../primitives/CopyButton'
import Icon from '../primitives/Icon'
import Tooltip from '../primitives/Tooltip'
import { useJobs } from '../../data/jobs'
import styles from './TopBar.module.css'

/* Every view needs an entry; a missing one renders an empty <h1>. */
const TITLES = {
  overview: 'Overview',
  tests: 'Tests',
  run: 'Experiments',
  trend: 'Regression trend',
  runs: 'CPU runs',
  'runs-detail': 'Run detail',
  campaign: 'CPU mutations',
}

export default function TopBar({ view, activeRun, onOpenMenu }) {
  const failed = activeRun?.tests?.some((t) => !t.passed)
  const { running } = useJobs()
  return (
    <header className={styles.bar}>
      <div className={styles.left}>
        <Tooltip label="Menu" side="bottom">
          <button type="button" className={styles.menuBtn} onClick={onOpenMenu} aria-label="Open menu">
            <Icon name="menu" size={18} />
          </button>
        </Tooltip>
        <h1 className={styles.title}>{TITLES[view]}</h1>

        {/* Jobs continue across navigation. */}
        {running.length > 0 && (
          <Tooltip label={running.map((j) => j.label).join(' · ')} side="bottom">
            <span className={styles.running}>
              <span className={styles.spinner} aria-hidden="true" />
              {running.length} running
            </span>
          </Tooltip>
        )}
      </div>

      {activeRun && (
        <div className={styles.context}>
          <Badge variant={failed ? 'fail' : 'pass'} withIcon>
            {failed ? 'Failing' : 'Passing'}
          </Badge>
          <span className={styles.runId}>
            <CopyButton value={activeRun.runId}>
              <span className="u-mono">{activeRun.runId}</span>
            </CopyButton>
          </span>
          <Tooltip label="RTL directory under test" side="bottom">
            <span className={styles.rtl}>{activeRun.rtlDir}</span>
          </Tooltip>
        </div>
      )}
    </header>
  )
}
