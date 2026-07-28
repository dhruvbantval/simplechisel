/*
 * Right-side slide-over for drill-down detail (progressive disclosure: the detail
 * is revealed on interaction, not always on screen). Closes on Esc and backdrop
 * click; moves focus into the panel on open and restores it on close. Separation
 * from the page comes from a hairline border + dimmed backdrop — no drop shadow.
 */
import { useEffect, useRef } from 'react'
import Icon from './Icon'
import Tooltip from './Tooltip'
import styles from './Drawer.module.css'

export default function Drawer({ open, onClose, title, subtitle, children }) {
  const panelRef = useRef(null)
  const restoreRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    restoreRef.current = document.activeElement
    panelRef.current?.focus()

    const onKey = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'

    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
      restoreRef.current?.focus?.()
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className={styles.overlay}>
      <div className={styles.backdrop} onClick={onClose} aria-hidden="true" />
      <aside
        ref={panelRef}
        className={styles.panel}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
      >
        <header className={styles.head}>
          <div className={styles.headText}>
            <h2 className={styles.title}>{title}</h2>
            {subtitle && <div className={styles.subtitle}>{subtitle}</div>}
          </div>
          <Tooltip label="Close (Esc)" side="left">
            <button type="button" className={styles.close} onClick={onClose} aria-label="Close">
              <Icon name="cross" size={18} />
            </button>
          </Tooltip>
        </header>
        <div className={styles.body}>{children}</div>
      </aside>
    </div>
  )
}
