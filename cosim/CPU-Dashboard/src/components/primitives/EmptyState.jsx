/*
 * Designed empty state (the skill flags missing empty states as a beginner tell).
 * An icon, a short message, an optional longer hint, and a slot for the primary
 * action so an empty region always tells the user what to do next.
 */
import Icon from './Icon'
import styles from './EmptyState.module.css'

export default function EmptyState({ icon = 'empty', title, hint, action, tone = 'default' }) {
  return (
    <div className={styles.wrap}>
      <div className={`${styles.iconWrap} ${styles[tone]}`}>
        <Icon name={icon} size={26} />
      </div>
      <div className={styles.title}>{title}</div>
      {hint && <p className={styles.hint}>{hint}</p>}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  )
}
