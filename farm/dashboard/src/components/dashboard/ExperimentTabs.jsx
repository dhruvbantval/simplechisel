/*
 * Experiment switcher shared by the Tests and Experiments views. Tabs show what
 * each experiment is checked against, flag missing system tools, and mark
 * experiments with a job in flight.
 */
import Icon from '../primitives/Icon'
import { useJobs } from '../../data/jobs'
import styles from './RunView.module.css'

export default function ExperimentTabs({ tabs, active, onSelect, disabled, toolsByType }) {
  const { running } = useJobs()
  // a job's key is "campaign:<type>" or "cosim:*", so match on the type segment
  const busyTypes = new Set(
    running.map((j) => (j.key ?? '').split(':')[1] ?? '')
      .map((t) => (t === 'run' || t === 'generate' ? 'cosim' : t)),
  )

  return (
    <div className={styles.expTabs} role="tablist">
      {tabs.map((e) => {
        const missing = toolsByType?.[e.type]?.missing ?? []
        const isRunning = busyTypes.has(e.type)
        return (
          <button
            key={e.type}
            type="button"
            role="tab"
            aria-selected={active === e.type}
            className={`${styles.expTab} ${active === e.type ? styles.expTabActive : ''}`}
            onClick={() => onSelect(e.type)}
            disabled={disabled}
            title={missing.length ? `needs ${missing.join(', ')}` : undefined}
          >
            <span className={styles.expTabTop}>
              {e.label}
              {isRunning && <span className={styles.expTabSpin} aria-label="running" />}
              {missing.length > 0 && (
                <Icon name="alert" size={13} className={styles.expTabWarn} />
              )}
            </span>
            {e.golden && <span className={styles.expTabSub}>vs {e.golden}</span>}
          </button>
        )
      })}
    </div>
  )
}
