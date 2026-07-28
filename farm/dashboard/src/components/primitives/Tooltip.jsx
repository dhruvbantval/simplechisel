/*
 * Lightweight hover/focus tooltip. Wraps any element; shows `label` on hover and
 * keyboard focus. CSS-only positioning, no portal — fine for short hints on icons
 * and ambiguous labels (the skill's "invisible UI" layer). Use for every icon-only
 * control and any abbreviation a newcomer wouldn't know (rd, rs1, PC, catch rate).
 */
import styles from './Tooltip.module.css'

export default function Tooltip({ label, children, side = 'top', className }) {
  if (!label) return children
  return (
    <span className={`${styles.wrap} ${className ?? ''}`} data-side={side}>
      {children}
      <span role="tooltip" className={styles.bubble}>
        {label}
      </span>
    </span>
  )
}
