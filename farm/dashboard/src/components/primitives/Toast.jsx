/*
 * Transient notifications for work that completes off-screen.
 *
 * Success toasts auto-dismiss; errors persist until dismissed. A toast with an
 * onClick navigates to the view that owns it.
 */
import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'
import Icon from './Icon'
import styles from './Toast.module.css'

const ToastContext = createContext(null)

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>')
  return ctx
}

const ICON = { success: 'check', error: 'alert', info: 'campaign' }

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const nextId = useRef(1)

  const dismiss = useCallback((id) => {
    setToasts((list) => list.filter((t) => t.id !== id))
  }, [])

  const pushToast = useCallback(({ title, body, tone = 'info', onClick, timeout }) => {
    const id = nextId.current++
    // errors persist: a failure that auto-hides is a failure you debug twice
    const ms = timeout ?? (tone === 'error' ? 0 : 7000)
    setToasts((list) => [...list, { id, title, body, tone, onClick }])
    if (ms > 0) setTimeout(() => dismiss(id), ms)
    return id
  }, [dismiss])

  const value = useMemo(() => ({ pushToast, dismiss }), [pushToast, dismiss])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className={styles.stack} role="region" aria-label="Notifications">
        {toasts.map((t) => (
          <div key={t.id}
               className={`${styles.toast} ${styles[t.tone]}`}
               role="status"
               aria-live={t.tone === 'error' ? 'assertive' : 'polite'}>
            <Icon name={ICON[t.tone] ?? 'campaign'} size={16} className={styles.icon} />
            <div className={styles.text}>
              {t.onClick ? (
                <button type="button" className={styles.titleBtn}
                        onClick={() => { t.onClick(); dismiss(t.id) }}>
                  {t.title}
                </button>
              ) : (
                <span className={styles.title}>{t.title}</span>
              )}
              {t.body && <span className={styles.body}>{t.body}</span>}
            </div>
            <button type="button" className={styles.close} onClick={() => dismiss(t.id)}
                    aria-label="Dismiss notification">
              <Icon name="cross" size={13} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
