/*
 * Badge / chip for categorical and state values. Per the design skill: status and
 * category fields render as chips, never plain text. Color is meaningful — it maps
 * to data state, not decoration. An optional leading icon draws the eye to urgent
 * states (e.g. a cross on a failing run).
 */
import Icon from './Icon'
import styles from './Badge.module.css'

const ICON_FOR = {
  pass: 'check',
  fail: 'cross',
  warning: 'alert',
}

export default function Badge({ variant = 'neutral', children, icon, withIcon = false, className }) {
  const iconName = icon ?? (withIcon ? ICON_FOR[variant] : null)
  return (
    <span className={`${styles.badge} ${styles[variant]} ${className ?? ''}`}>
      {iconName && <Icon name={iconName} size={13} className={styles.icon} />}
      {children}
    </span>
  )
}
