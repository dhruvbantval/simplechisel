/*
 * Slim header above the content column. Shows the current view title and, when a
 * run is active, its identity (runId + status + RTL dir) so context is never lost
 * while scrolling. Hosts the mobile menu button that opens the Sidebar.
 */
import Badge from '../primitives/Badge'
import CopyButton from '../primitives/CopyButton'
import Icon from '../primitives/Icon'
import Tooltip from '../primitives/Tooltip'
import styles from './TopBar.module.css'

const TITLES = {
  overview: 'Overview',
  runs: 'Runs',
  campaign: 'Campaign',
}

export default function TopBar({ view, activeRun, onOpenMenu }) {
  const failed = activeRun?.tests?.some((t) => !t.passed)
  return (
    <header className={styles.bar}>
      <div className={styles.left}>
        <Tooltip label="Menu" side="bottom">
          <button type="button" className={styles.menuBtn} onClick={onOpenMenu} aria-label="Open menu">
            <Icon name="menu" size={18} />
          </button>
        </Tooltip>
        <h1 className={styles.title}>{TITLES[view]}</h1>
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
