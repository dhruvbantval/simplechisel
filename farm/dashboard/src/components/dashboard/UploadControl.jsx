/*
 * Upload entry point for run JSON files. Two variants share one pipeline:
 *   - 'button'   compact control for the sidebar / section headers
 *   - 'dropzone' large drag-and-drop target for the empty state
 *
 * Files are handed to `onUpload(file)` (useRuns.addRunFromFile), which parses,
 * validates against the schema, and persists. Validation/parse failures are shown
 * inline as a friendly list rather than thrown — the original jsonFormat.txt was
 * invalid JSON, so this path matters.
 */
import { useRef, useState } from 'react'
import Icon from '../primitives/Icon'
import styles from './UploadControl.module.css'

export default function UploadControl({ onUpload, variant = 'button', label = 'Upload run' }) {
  const inputRef = useRef(null)
  const [errors, setErrors] = useState([])
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)

  const handleFiles = async (fileList) => {
    const files = Array.from(fileList ?? []).filter((f) => f.name.endsWith('.json') || f.type === 'application/json')
    if (files.length === 0) {
      setErrors(['Please choose a .json file.'])
      return
    }
    setBusy(true)
    setErrors([])
    const allErrors = []
    for (const file of files) {
      // eslint-disable-next-line no-await-in-loop -- sequential keeps newest-active deterministic
      const result = await onUpload(file)
      if (!result.ok) allErrors.push(`${file.name}: ${result.errors[0]}`, ...result.errors.slice(1))
    }
    setBusy(false)
    setErrors(allErrors)
  }

  const onInputChange = (e) => {
    handleFiles(e.target.files)
    e.target.value = '' // allow re-uploading the same filename
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  const pick = () => inputRef.current?.click()

  return (
    <div className={variant === 'dropzone' ? styles.dropWrap : styles.btnWrap}>
      <input
        ref={inputRef}
        type="file"
        accept="application/json,.json"
        multiple
        className="u-sr-only"
        onChange={onInputChange}
      />

      {variant === 'dropzone' ? (
        <button
          type="button"
          className={`${styles.dropzone} ${dragging ? styles.dragging : ''}`}
          onClick={pick}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <Icon name="upload" size={22} />
          <span className={styles.dropTitle}>{busy ? 'Reading…' : 'Drop a run JSON here'}</span>
          <span className={styles.dropHint}>or click to browse</span>
        </button>
      ) : (
        <button type="button" className={styles.button} onClick={pick} disabled={busy}>
          <Icon name="upload" size={15} />
          {busy ? 'Reading…' : label}
        </button>
      )}

      {errors.length > 0 && (
        <div className={styles.errors} role="alert">
          <div className={styles.errorsHead}>
            <Icon name="alert" size={14} /> Couldn&apos;t import file
          </div>
          <ul className={styles.errorList}>
            {errors.slice(0, 6).map((err, i) => (
              <li key={i}>{err}</li>
            ))}
            {errors.length > 6 && <li>…and {errors.length - 6} more.</li>}
          </ul>
        </div>
      )}
    </div>
  )
}
