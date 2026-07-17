/*
 * Async-region switch: renders loading / error / empty / content based on status.
 * Centralizes the three states the skill says beginners forget, so every data
 * region in the app handles them consistently.
 *
 *   status: 'loading' | 'error' | 'ready'
 *   isEmpty: when ready but there's nothing to show
 */
import EmptyState from './EmptyState'
import styles from './StateView.module.css'

export default function StateView({ status, error, isEmpty, empty, children }) {
  if (status === 'loading') {
    return (
      <div className={styles.center}>
        <span className={styles.spinner} aria-hidden="true" />
        <span className="u-muted">Loading…</span>
      </div>
    )
  }
  if (status === 'error') {
    return (
      <EmptyState
        icon="alert"
        tone="danger"
        title="Couldn't load runs"
        hint={error ?? 'Your browser may be blocking local storage (IndexedDB).'}
      />
    )
  }
  if (isEmpty) return empty ?? null
  return children
}
