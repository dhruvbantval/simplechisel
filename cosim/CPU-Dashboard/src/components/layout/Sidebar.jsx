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

const NAV = [
  { id: 'overview', label: 'Overview', icon: 'overview', hint: 'KPIs and tests for the active run' },
  { id: 'runs', label: 'Runs', icon: 'runs', hint: 'Every uploaded run; pick one to inspect' },
  { id: 'campaign', label: 'Campaign', icon: 'campaign', hint: 'Catch-rate of injected bugs across programs' },
]

export default function Sidebar({ view, onNavigate, onUpload, summary, open, onClose }) {
  return (
    <>
      <div className={`${styles.scrim} ${open ? styles.scrimOpen : ''}`} onClick={onClose} aria-hidden="true" />
      <aside className={`${styles.sidebar} ${open ? styles.open : ''}`}>
        <div className={styles.brand}>
          <span className={styles.brandMark} aria-hidden="true">
            <Icon name="chip" size={18} />
          </span>
          <span className={styles.brandText}>
            CPU<span className={styles.brandThin}>Verify</span>
          </span>
        </div>

        <nav className={styles.nav}>
          {NAV.map((item) => (
            <Tooltip key={item.id} label={item.hint} side="right">
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
          ))}
        </nav>

        <div className={styles.upload}>
          <UploadControl onUpload={onUpload} label="Upload run" />
        </div>

        <div className={styles.summary}>
          <SummaryRow label="Runs" value={summary.totalRuns} />
          <SummaryRow label="Mutations" value={summary.mutationRuns} hint="Runs with an injected bug" />
          <SummaryRow
            label="Bugs caught"
            value={summary.bugsCaught}
            tone={summary.bugsCaught > 0 ? 'success' : 'muted'}
            hint="Mutation runs where at least one program failed"
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
