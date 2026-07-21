/*
 * Bug-injection panel. Each row injects one known CPU bug; bugs stack, so you
 * can inject several before running. An injected bug is marked and can't be
 * injected again until you Reset, which restores the clean CPU. The Run button
 * (main view) then runs the selected folder against whatever is injected here.
 */
import Icon from '../primitives/Icon'
import styles from './MutationsPanel.module.css'

export default function MutationsPanel({ mutations, injected, onInject, onReset, busy }) {
  const injectedNames = new Set((injected ?? []).map((b) => b.name))

  return (
    <div className={styles.panel}>
      <div className={styles.head}>
        <Icon name="bug" size={16} />
        <h3 className={styles.title}>Inject a bug</h3>
      </div>
      <p className={styles.blurb}>
        Mutate the CPU with known defects. Bugs stack until you reset. Then run a
        folder — a good suite drops the pass rate, which is the bug being caught.
      </p>

      <div className={styles.statusRow}>
        <span className={styles.injectedCount}>
          {injectedNames.size === 0 ? 'Clean CPU' : `${injectedNames.size} bug${injectedNames.size === 1 ? '' : 's'} injected`}
        </span>
        <button
          type="button"
          className={styles.resetBtn}
          onClick={onReset}
          disabled={busy || injectedNames.size === 0}
          title="Restore the clean CPU"
        >
          Reset
        </button>
      </div>

      {mutations.length === 0 ? (
        <p className={styles.empty}>No bugs available.</p>
      ) : (
        <ul className={styles.list}>
          {mutations.map((m) => {
            const isInjected = injectedNames.has(m.name)
            return (
              <li key={m.name} className={styles.item}>
                <div className={styles.itemText}>
                  <span className={styles.itemName}>{m.function}</span>
                  <span className={styles.itemDesc}>{m.description}</span>
                </div>
                <button
                  type="button"
                  className={`${styles.injectBtn} ${isInjected ? styles.injected : ''}`}
                  onClick={() => onInject(m.function)}
                  disabled={busy || isInjected}
                  title={isInjected ? 'Already injected — reset to change' : `Inject "${m.name}"`}
                >
                  {isInjected ? 'Injected' : 'Inject'}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
