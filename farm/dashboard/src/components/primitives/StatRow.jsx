/*
 * KPI display. Per the core skill principle, KPIs *flow* as a row of
 * "big number + small label", separated by space and a hairline divider — NOT a
 * grid of bordered tiles. Stat carries an optional tone so a single number can
 * signal state (e.g. failures shown in danger color) and an optional tooltip on
 * the label for any abbreviation.
 */
import Tooltip from './Tooltip'
import styles from './StatRow.module.css'

export function Stat({ value, label, sub, tone = 'default', hint }) {
  return (
    <div className={styles.stat}>
      <div className={`${styles.value} ${styles[tone]}`}>{value}</div>
      <div className={styles.label}>
        {hint ? (
          <Tooltip label={hint} side="bottom">
            <span className={styles.labelText}>{label}</span>
          </Tooltip>
        ) : (
          <span className={styles.labelText}>{label}</span>
        )}
      </div>
      {sub != null && <div className={styles.sub}>{sub}</div>}
    </div>
  )
}

export function StatRow({ children, className }) {
  return <div className={`${styles.row} ${className ?? ''}`}>{children}</div>
}

export default StatRow
