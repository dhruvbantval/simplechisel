/*
 * Test dashboard. Generate a named batch of programs (saved as a folder) and
 * browse the saved library. Generation is decoupled from running: this view
 * builds the test folders; the Run view executes them against the CPU.
 *
 * Requires a live backend. Without one, generation isn't possible, so the view
 * explains that instead of showing dead controls.
 */
import { useEffect, useRef, useState } from 'react'
import Section from '../primitives/Section'
import EmptyState from '../primitives/EmptyState'
import Icon from '../primitives/Icon'
import { getFolder, getFolders, pollJob, startGenerate, uploadTests } from '../../data/api'
import styles from './TestsView.module.css'

export default function TestsView({ live, health, onFoldersChanged }) {
  const [name, setName] = useState('')
  const [tests, setTests] = useState(10)
  const [instrCnt, setInstrCnt] = useState(120)
  const [type, setType] = useState('mixed')

  const [busy, setBusy] = useState(false)
  const [log, setLog] = useState([])
  const [error, setError] = useState(null)
  const [folders, setFolders] = useState([])
  const [openFolder, setOpenFolder] = useState(null) // { name, tests: [] }
  const logRef = useRef(null)
  const fileRef = useRef(null)

  async function onUploadPrograms(fileList) {
    const picked = [...fileList].filter((f) => f.name.endsWith('.S') || f.name.endsWith('.s'))
    if (picked.length === 0) { setError('pick one or more .S files'); return }
    setBusy(true); setError(null)
    try {
      const files = await Promise.all(picked.map(async (f) => ({ name: f.name, content: await f.text() })))
      const folderName = name.trim() || `uploaded-${Date.now()}`
      const res = await uploadTests(folderName, files)
      if (res.error) setError(res.error)
      else { setName(''); refreshFolders(); onFoldersChanged?.() }
    } catch (e) {
      setError(e.message ?? String(e))
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const types = health?.types ?? ['mixed', 'arithmetic']

  const refreshFolders = () => {
    if (live) getFolders().then(setFolders).catch(() => setFolders([]))
  }
  // Arrow body: refreshFolders() returns a Promise; an effect must return a
  // cleanup fn or nothing, so wrap it (otherwise React calls the Promise on
  // unmount and the view crashes to blank).
  useEffect(() => { refreshFolders() }, [live]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [log])

  async function onGenerate() {
    setBusy(true)
    setLog([])
    setError(null)
    try {
      const folderName = name.trim() || `batch-${Date.now()}`
      const { jobId } = await startGenerate({
        name: folderName, tests: Number(tests), instrCnt: Number(instrCnt), type,
      })
      const snap = await pollJob(jobId, { onLog: (lines) => setLog((p) => [...p, ...lines]) })
      if (snap.status === 'error') {
        setError(snap.error || 'generation failed')
      } else {
        setName('')
        refreshFolders()
        onFoldersChanged?.()
      }
    } catch (err) {
      setError(err.message ?? String(err))
    } finally {
      setBusy(false)
    }
  }

  const toggleFolder = async (folderName) => {
    if (openFolder?.name === folderName) return setOpenFolder(null)
    const detail = await getFolder(folderName)
    setOpenFolder(detail)
  }

  if (!live) {
    return (
      <Section title="Tests">
        <EmptyState
          icon="folder"
          title="No backend connected"
          hint="Generating tests runs the riscv-dv generator on a backend (farm/webapp/server.py). Start it, or set VITE_API_BASE to a running instance, to build test folders here."
        />
      </Section>
    )
  }

  return (
    <div className={styles.wrap}>
      <Section
        title="Generate a test batch"
        description="Each batch is saved as a named folder you can run later from the Run view."
      >
        <div className={styles.form}>
          <label className={styles.field} style={{ gridColumn: '1 / -1' }}>
            <span className={styles.fieldLabel}>Folder name</span>
            <input
              type="text" placeholder="e.g. alu-smoke" value={name}
              onChange={(e) => setName(e.target.value)} disabled={busy}
            />
          </label>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>Number of tests</span>
            <input type="number" min="1" max="200" value={tests}
              onChange={(e) => setTests(e.target.value)} disabled={busy} />
          </label>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>Instructions / test</span>
            <input type="number" min="5" max="2000" step="5" value={instrCnt}
              onChange={(e) => setInstrCnt(e.target.value)} disabled={busy} />
          </label>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>Mix</span>
            <select value={type} onChange={(e) => setType(e.target.value)} disabled={busy}>
              {types.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
        </div>
        <div className={styles.genRow}>
          <button type="button" className={styles.primary} onClick={onGenerate} disabled={busy}>
            <Icon name="generate" size={16} />
            {busy ? 'Generating…' : 'Generate tests'}
          </button>
          <span className={styles.or}>or</span>
          <button type="button" className={styles.secondary} onClick={() => fileRef.current?.click()} disabled={busy}>
            <Icon name="upload" size={15} /> Upload your own .S programs
          </button>
          <input ref={fileRef} type="file" accept=".S,.s" multiple hidden
                 onChange={(e) => onUploadPrograms(e.target.files)} />
        </div>
        {error && <p className={styles.error}><Icon name="alert" size={15} /> {error}</p>}
        {log.length > 0 && <pre className={styles.log} ref={logRef}>{log.join('\n')}</pre>}
      </Section>

      <Section title="Test library" description="Saved folders. Open one to see its programs; run them from the Run view.">
        {folders.length === 0 ? (
          <EmptyState icon="folder" title="No test folders yet"
            hint="Generate a batch above to create your first folder." />
        ) : (
          <ul className={styles.folders}>
            {folders.map((f) => (
              <li key={f.name} className={styles.folder}>
                <button type="button" className={styles.folderHead} onClick={() => toggleFolder(f.name)}>
                  <Icon name="folder" size={16} />
                  <span className={styles.folderName}>{f.name}</span>
                  <span className={styles.folderCount}>{f.count} test{f.count === 1 ? '' : 's'}</span>
                </button>
                {openFolder?.name === f.name && (
                  <ul className={styles.testList}>
                    {openFolder.tests.map((t) => (
                      <li key={t.name} className={styles.testRow}>
                        <span className={styles.testName}>{t.name}</span>
                        <span className={styles.testInstr}>{t.instrCount} instr</span>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  )
}
