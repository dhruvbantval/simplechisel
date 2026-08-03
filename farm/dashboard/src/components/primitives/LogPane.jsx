/*
 * Scrollable job output with a copy button.
 *
 * Follows the newest line only while the user is already scrolled to the bottom,
 * so reading back through earlier output is not interrupted.
 */
import { useEffect, useRef, useState } from 'react'
import Icon from './Icon'
import styles from './LogPane.module.css'

export default function LogPane({ lines, label = 'Output', className }) {
  const preRef = useRef(null)
  const pinned = useRef(true)
  const [copied, setCopied] = useState(false)

  const text = Array.isArray(lines) ? lines.join('\n') : String(lines ?? '')

  // track whether the user is parked at the bottom
  const onScroll = () => {
    const el = preRef.current
    if (!el) return
    pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24
  }

  useEffect(() => {
    const el = preRef.current
    if (el && pinned.current) el.scrollTop = el.scrollHeight
  }, [text])

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1400)
    } catch {
      /* clipboard blocked (insecure context) — fall back to a manual selection */
      const el = preRef.current
      if (el) {
        const range = document.createRange()
        range.selectNodeContents(el)
        const sel = window.getSelection()
        sel.removeAllRanges()
        sel.addRange(range)
      }
    }
  }

  if (!text) return null

  return (
    <div className={`${styles.wrap} ${className ?? ''}`}>
      <div className={styles.bar}>
        <span className={styles.label}>{label}</span>
        <button type="button" className={styles.copy} onClick={copy}
                aria-label={copied ? 'Copied' : 'Copy output'}>
          <Icon name={copied ? 'check' : 'copy'} size={13} />
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className={styles.log} ref={preRef} onScroll={onScroll}>{text}</pre>
    </div>
  )
}
