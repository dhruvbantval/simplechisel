/*
 * Test dashboard — every experiment, not just the CPU.
 *
 * Generation is decoupled from running: this view builds the inputs, the
 * Experiments view runs them. Both halves work the same way (name a batch,
 * choose how many, Generate, browse the library), but the CPU's inputs are
 * folders of RISC-V programs while a campaign experiment's are JSON case lists,
 * so each gets its own panel:
 *
 *   cosim (ui: cosim)     -> riscv-dv test folders, below
 *   anything else         -> BatchLibrary, driven by farm.yaml's `generate:`
 *
 * Requires a live backend. Without one, generation isn't possible, so the view
 * explains that instead of showing dead controls.
 */
import { useEffect, useRef, useState } from 'react'
import Section from '../primitives/Section'
import EmptyState from '../primitives/EmptyState'
import Icon from '../primitives/Icon'
import LogPane from '../primitives/LogPane'
import ExperimentTabs from './ExperimentTabs'
import BatchLibrary from './BatchLibrary'
import {
  deleteFolder, deleteTest, getFolder, getFolders, startGenerate, uploadTests,
} from '../../data/api'
import { useJobs } from '../../data/jobs'
import styles from './TestsView.module.css'

export default function TestsView({ live, health, experiments, onFoldersChanged, onNavigate }) {
  const tabs = experiments?.length ? experiments : [{ type: 'cosim', label: 'CPU cosim' }]
  const [active, setActive] = useState('cosim')
  const current = tabs.find((e) => e.type === active) ?? tabs[0]

  if (!live) {
    return (
      <Section title="Tests">
        <EmptyState
          icon="folder"
          title="No backend connected"
          hint="Generating tests runs each experiment's generator on a backend (farm/webapp/server.py). Start it, or set VITE_API_BASE to a running instance, to build test batches here."
        />
      </Section>
    )
  }

  return (
    <>
      <ExperimentTabs tabs={tabs} active={active} onSelect={setActive} />
      {current?.ui === 'cosim' || current?.type === 'cosim' ? (
        <CosimTests live={live} health={health} onFoldersChanged={onFoldersChanged} />
      ) : (
        <div className={styles.wrap}>
          <BatchLibrary experiment={current} onNavigate={onNavigate} />
        </div>
      )}
    </>
  )
}

/* The CPU's own test-folder generator (riscv-dv). */
function CosimTests({ live, health, onFoldersChanged }) {
  const [name, setName] = useState('')
  const [tests, setTests] = useState(10)
  const [instrCnt, setInstrCnt] = useState(120)
  const [type, setType] = useState('mixed')

  const [error, setError] = useState(null)
  const [folders, setFolders] = useState([])
  const [openFolder, setOpenFolder] = useState(null) // { name, tests: [] }
  const fileRef = useRef(null)

  // Generation takes minutes, so it is tracked in the job store.
  const { startJob, jobFor } = useJobs()
  const job = jobFor('cosim:generate')
  const busy = job.busy
  const log = job.log

  // A single request rather than a tracked job, so it keeps a local flag.
  const [uploading, setUploading] = useState(false)

  async function onUploadPrograms(fileList) {
    const picked = [...fileList].filter((f) => f.name.endsWith('.S') || f.name.endsWith('.s'))
    if (picked.length === 0) { setError('pick one or more .S files'); return }
    setUploading(true); setError(null)
    try {
      const files = await Promise.all(picked.map(async (f) => ({ name: f.name, content: await f.text() })))
      const folderName = name.trim() || `uploaded-${Date.now()}`
      const res = await uploadTests(folderName, files)
      if (res.error) setError(res.error)
      else { setName(''); refreshFolders(); onFoldersChanged?.() }
    } catch (e) {
      setError(e.message ?? String(e))
    } finally {
      setUploading(false)
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

  function onGenerate() {
    setError(null)
    const folderName = name.trim() || `batch-${Date.now()}`
    startJob({
      key: 'cosim:generate',
      kind: 'generate',
      label: `Generating “${folderName}”`,
      view: 'tests',
      start: () => startGenerate({
        name: folderName, tests: Number(tests), instrCnt: Number(instrCnt), type,
      }),
      describe: (snap) => snap.run
        ? `${folderName}: ${snap.run.count} test${snap.run.count === 1 ? '' : 's'} (+${snap.run.added})`
        : undefined,
      onComplete: (snap) => {
        if (snap.status !== 'error') setName('')
        refreshFolders()
        onFoldersChanged?.()
      },
    })
  }

  const toggleFolder = async (folderName) => {
    if (openFolder?.name === folderName) return setOpenFolder(null)
    const detail = await getFolder(folderName)
    setOpenFolder(detail)
  }

  async function onDeleteFolder(folderName) {
    setError(null)
    try {
      await deleteFolder(folderName)
      if (openFolder?.name === folderName) setOpenFolder(null)
      refreshFolders()
      onFoldersChanged?.()
    } catch (e) {
      setError(e.message ?? String(e))
    }
  }

  async function onDeleteTest(folderName, testName) {
    setError(null)
    try {
      const res = await deleteTest(folderName, testName)
      // the backend drops a folder that just lost its last program
      if (res.folderRemoved) setOpenFolder(null)
      else setOpenFolder(await getFolder(folderName))
      refreshFolders()
      onFoldersChanged?.()
    } catch (e) {
      setError(e.message ?? String(e))
    }
  }

  return (
    <div className={styles.wrap}>
      <Section
        title="Generate a test batch"
        description="Random RV64I programs from riscv-dv, saved as a named folder to run from the Experiments view."
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
          <button type="button" className={styles.secondary} onClick={() => fileRef.current?.click()} disabled={busy || uploading}>
            <Icon name="upload" size={15} /> {uploading ? 'Uploading…' : 'Upload your own .S programs'}
          </button>
          <input ref={fileRef} type="file" accept=".S,.s" multiple hidden
                 onChange={(e) => onUploadPrograms(e.target.files)} />
        </div>
        {error && <p className={styles.error}><Icon name="alert" size={15} /> {error}</p>}
        <LogPane lines={log} label="Generator output" />
      </Section>

      <Section title="Test library" description="Saved folders. Open one to see its programs; run them from the Experiments view.">
        {folders.length === 0 ? (
          <EmptyState icon="folder" title="No test folders yet"
            hint="Generate a batch above to create your first folder." />
        ) : (
          <ul className={styles.folders}>
            {folders.map((f) => (
              <li key={f.name} className={styles.folder}>
                <div className={styles.folderRow}>
                  <button type="button" className={styles.folderHead} onClick={() => toggleFolder(f.name)}>
                    <Icon name="folder" size={16} />
                    <span className={styles.folderName}>{f.name}</span>
                    <span className={styles.folderCount}>{f.count} test{f.count === 1 ? '' : 's'}</span>
                  </button>
                  <button type="button" className={styles.del}
                          onClick={() => onDeleteFolder(f.name)}
                          title={`Delete folder ${f.name}`}
                          aria-label={`Delete folder ${f.name}`}>
                    <Icon name="trash" size={15} />
                  </button>
                </div>
                {openFolder?.name === f.name && (
                  <ul className={styles.testList}>
                    {openFolder.tests.map((t) => (
                      <li key={t.name} className={styles.testRow}>
                        <span className={styles.testName}>{t.name}</span>
                        <span className={styles.testInstr}>{t.instrCount} instr</span>
                        <button type="button" className={styles.delTest}
                                onClick={() => onDeleteTest(f.name, t.name)}
                                title={`Delete ${t.name}`}
                                aria-label={`Delete test ${t.name}`}>
                          <Icon name="trash" size={13} />
                        </button>
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
