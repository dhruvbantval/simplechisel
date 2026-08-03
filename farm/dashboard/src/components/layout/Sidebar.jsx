/*
 * Primary navigation. A calm left rail: product mark, the three views, the upload
 * CTA, and a compact global summary at the foot so the system-wide health is
 * always one glance away regardless of which view is open. Collapses to a slide-in
 * panel on mobile (toggled from the TopBar via `open`/`onClose`).
 */
import Icon from '../primitives/Icon'
import Tooltip from '../primitives/Tooltip'
import UploadControl from '../dashboard/UploadControl'
import styles from './Sidebar.module.css'

/* Shared views first, then the two cosim-specific ones under a CPU heading. */
const NAV = [
  { id: 'overview', label: 'Overview', icon: 'overview', hint: 'Every domain’s results, from the shared record store' },
  { id: 'tests', label: 'Tests', icon: 'folder', hint: 'Generate and browse test batches for any experiment' },
  { id: 'run', label: 'Experiments', icon: 'play', hint: 'Run any experiment: CPU, compiler, PID, ECG, SPICE' },
  { id: 'trend', label: 'Trend', icon: 'campaign', hint: 'Pass-rate per version, per domain — regressions show as drops' },
  { id: 'runs', label: 'CPU runs', icon: 'runs', hint: 'Past cosim runs; pick one for the per-instruction diff', group: 'CPU' },
  { id: 'campaign', label: 'CPU mutations', icon: 'bug', hint: 'Catch-rate of injected CPU bugs across programs', group: 'CPU' },
]

export default function Sidebar({ view, onNavigate, onUpload, farm, open, onClose }) {
  return (
    <>
      <div className={`${styles.scrim} ${open ? styles.scrimOpen : ''}`} onClick={onClose} aria-hidden="true" />
      <aside className={`${styles.sidebar} ${open ? styles.open : ''}`}>
        <div className={styles.brand}>
          <img className={styles.brandMark} src="/logo.png" alt="" width="28" height="28" />
          <span className={styles.brandText}>
            AutoExperiment<span className={styles.brandThin}>Farm</span>
          </span>
        </div>

        <nav className={styles.nav}>
          {NAV.map((item, i) => (
            <div key={item.id} className={styles.navSlot}>
              {item.group && NAV[i - 1]?.group !== item.group && (
                <span className={styles.navGroup}>{item.group}</span>
              )}
              <Tooltip label={item.hint} side="right">
                <button
                  type="button"
                  className={`${styles.navItem} ${view === item.id ? styles.active : ''}`}
                  onClick={() => {
                    onNavigate(item.id)
                    onClose?.()
                  }}
                  aria-current={view === item.id ? 'page' : undefined}
                >
                  <Icon name={item.icon} size={17} />
                  {item.label}
                </button>
              </Tooltip>
            </div>
          ))}
        </nav>

        <div className={styles.upload}>
          <UploadControl onUpload={onUpload} label="Upload run" />
        </div>

        {/* Farm-wide totals from the shared record store. */}
        <div className={styles.summary}>
          <SummaryRow label="Records" value={farm.total} hint="One per experiment case run, all domains" />
          <SummaryRow
            label="Pass rate"
            value={farm.total ? `${farm.passRate}%` : '—'}
            tone={farm.total === 0 ? 'muted' : farm.passRate >= 80 ? 'success' : 'muted'}
            hint="Across every experiment"
          />
          <SummaryRow
            label="Failed"
            value={farm.failed}
            tone={farm.failed > 0 ? 'danger' : 'muted'}
            hint="Disagreed with the golden reference"
          />
          <SummaryRow
            label="Errored"
            value={farm.errored}
            tone={farm.errored > 0 ? 'warning' : 'muted'}
            hint="Could not run — usually a missing tool"
          />
        </div>
      </aside>
    </>
  )
}

function SummaryRow({ label, value, tone = 'muted', hint }) {
  const labelNode = <span className={styles.summaryLabel}>{label}</span>
  return (
    <div className={styles.summaryRow}>
      {hint ? (
        <Tooltip label={hint} side="right">
          {labelNode}
        </Tooltip>
      ) : (
        labelNode
      )}
      <span className={`${styles.summaryValue} ${styles[tone]}`}>{value}</span>
    </div>
  )
}
