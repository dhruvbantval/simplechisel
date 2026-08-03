/*
 * Banner listing an experiment's missing system tools with copyable install
 * commands for the current platform.
 */
import CopyButton from '../primitives/CopyButton'
import Icon from '../primitives/Icon'
import { installHints } from '../../data/installHints'
import styles from './InstallNeeded.module.css'

export default function InstallNeeded({ missing, inWsl }) {
  const hints = installHints(missing)
  if (hints.length === 0) return null

  return (
    <div className={styles.box}>
      <div className={styles.head}>
        <Icon name="alert" size={16} className={styles.icon} />
        <span>
          This experiment needs{' '}
          {hints.map((h, i) => (
            <span key={h.tool}>{i > 0 && ', '}<code>{h.tool}</code></span>
          ))}
          {inWsl
            ? ' inside WSL, where this experiment runs.'
            : ' on your PATH.'}
          {' '}Install {hints.length === 1 ? 'it' : 'them'}, then restart the backend:
        </span>
      </div>

      <ul className={styles.list}>
        {hints.map((h) => (
          <li key={h.tool} className={styles.row}>
            <span className={styles.tool}>{h.tool}</span>
            {h.command ? (
              <CopyButton value={h.command} className={styles.cmd}>
                <code>{h.command}</code>
              </CopyButton>
            ) : (
              <span className={styles.muted}>see farm/README.md</span>
            )}
            {h.note && <span className={styles.note}>{h.note}</span>}
          </li>
        ))}
      </ul>
    </div>
  )
}
