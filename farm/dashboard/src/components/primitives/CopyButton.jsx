/*
 * Copy-on-click for cells holding IDs, hex values, and codes (skill: copy
 * functionality on relevant cells). Renders the value plus a small copy icon that
 * confirms with a brief "Copied" state. Inherits the surrounding text style so it
 * sits inline naturally.
 */
import { useState } from 'react'
import Icon from './Icon'
import Tooltip from './Tooltip'
import styles from './CopyButton.module.css'

export default function CopyButton({ value, children, className }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(String(value))
      setCopied(true)
      setTimeout(() => setCopied(false), 1200)
    } catch {
      /* clipboard unavailable (e.g. insecure context) — fail quietly */
    }
  }

  return (
    <Tooltip label={copied ? 'Copied' : 'Copy'}>
      <button type="button" className={`${styles.btn} ${className ?? ''}`} onClick={copy}>
        <span>{children ?? value}</span>
        <Icon name={copied ? 'check' : 'copy'} size={13} className={styles.icon} />
      </button>
    </Tooltip>
  )
}
