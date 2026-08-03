/*
 * A generic experiment page. Any experiment declared in farm.yaml with
 * `ui: campaign` renders through this: it shows what's being tested against what,
 * lists the cases from the config, and runs the whole campaign with one button.
 *
 * It knows nothing about PIDs, heartbeats or circuits — all of that lives in the
 * config and the adapter. That's why adding a science needs no new UI.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import Section from '../primitives/Section'
import Icon from '../primitives/Icon'
import LogPane from '../primitives/LogPane'
import {
  getBatches,
  getCampaignCases,
  runCustomCase,
  startCampaign,
  uploadCase,
} from '../../data/api'
import { useJobs } from '../../data/jobs'
import styles from './RunView.module.css'

// read a File as base64 (for binary uploads like WFDB .dat/.atr)
function toBase64(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(String(r.result).split(',')[1] || '')
    r.onerror = reject
    r.readAsDataURL(file)
  })
}

export default function CampaignPanel({ live, experiment, missingTools = [], onDone }) {
  const [cases, setCases] = useState([])
  const [params, setParams] = useState({})
  const fileRef = useRef(null)

  // Runs are tracked in the job store so they survive this panel unmounting.
  const { startJob, jobFor } = useJobs()

  const type = experiment?.type
  const upload = experiment?.upload
  const customCase = experiment?.custom_case

  const jobKey = `campaign:${type}`
  const job = jobFor(jobKey)
  const busy = job.busy
  const log = job.log
  const error = job.error
  const result = job.result
    ? { passed: job.result.passed, total: job.result.totalTests, detail: job.result.detail }
    : null

  // '' selects every configured and generated case, matching the CLI default.
  const [batches, setBatches] = useState([])
  const [batch, setBatch] = useState('')

  const loadCases = useCallback((which) => {
    if (!live || !type) return
    getCampaignCases(type, which || undefined)
      .then((d) => setCases(d.cases || []))
      .catch(() => setCases([]))
  }, [live, type])

  useEffect(() => {
    setCases([]); setBatch('')
    // seed the upload-form params from their defaults
    setParams(Object.fromEntries(
      [...(upload?.params || []), ...(customCase?.params || [])].map((p) => [p.name, p.default ?? '']),
    ))
    if (live && type) {
      loadCases('')
      getBatches(type).then((d) => setBatches(d.batches || [])).catch(() => setBatches([]))
    }
  }, [live, type, upload, customCase, loadCases])

  useEffect(() => { loadCases(batch) }, [batch, loadCases])

  const track = (startFn, after) => startJob({
    key: jobKey,
    kind: 'campaign',
    label: experiment?.label ?? type,
    view: 'run',
    start: startFn,
    describe: (snap) => snap.run
      ? `${snap.run.passed}/${snap.run.totalTests} cases passed`
      : undefined,
    onComplete: (snap) => {
      if (snap.status !== 'error') onDone?.()
      after?.(snap)
    },
  })

  const onRun = () => track(() => startCampaign(type, batch || undefined))

  const pick = (defs) => Object.fromEntries((defs || []).map((p) => [p.name, params[p.name]]))

  async function onUpload(fileList) {
    const list = [...(fileList || [])]
    if (!list.length) return
    const binary = !!upload?.binary
    const readOne = async (f) => ({
      name: f.name,
      content: binary ? await toBase64(f) : await f.text(),
    })
    const files = await Promise.all(list.map(readOne))
    track(() => uploadCase(type, files, pick(upload?.params), binary ? 'base64' : undefined),
          () => loadCases(batch))
    if (fileRef.current) fileRef.current.value = ''
  }

  const onCustom = () => track(() => runCustomCase(type, pick(customCase?.params)))

  if (!experiment) return null

  return (
    <div className={styles.main}>
      <Section
        title={experiment.label}
        description={`${experiment.dut} checked against ${experiment.golden}. Every case must agree with the golden reference; the headline number is ${experiment.metric ?? 'the domain metric'}.`}
      >
        <div className={styles.runRow}>
          <label className={styles.field}>
            <span className={styles.fieldLabel}>Cases</span>
            <select value={batch} onChange={(e) => setBatch(e.target.value)} disabled={busy}>
              <option value="">All cases ({cases.length ? cases.length : '—'})</option>
              {batches.map((b) => (
                <option key={b.name} value={b.name}>
                  {b.name} ({b.count})
                </option>
              ))}
            </select>
          </label>
          <button type="button" className={styles.primary} onClick={onRun}
                  disabled={busy || !type || missingTools.length > 0}>
            <Icon name="play" size={16} />
            {busy ? 'Running…' : batch ? `Run “${batch}”` : `Run ${experiment.label}`}
          </button>
        </div>
        <p className={styles.setupNote}>
          {batches.length === 0
            ? 'Runs the cases configured in farm.yaml. Generate a batch on the Tests tab to add more.'
            : 'Select a batch to run only its cases, or “All cases” for every configured and generated case.'}
        </p>

        {experiment.setup && (
          <p className={styles.setupNote}>
            First time? This experiment needs its data fetched once:
            <code>{experiment.setup}</code>
          </p>
        )}

        {upload && (
          <div className={styles.uploadBox}>
            <div className={styles.uploadHead}>
              <Icon name="upload" size={15} /> Test your own {upload.label}
            </div>
            <div className={styles.uploadRow}>
              {(upload.params || []).map((p) => (
                <label key={p.name} className={styles.uploadField}>
                  <span>{p.label ?? p.name}</span>
                  <input
                    type="number" step="any" value={params[p.name] ?? ''}
                    onChange={(e) => setParams((v) => ({ ...v, [p.name]: e.target.value }))}
                    disabled={busy}
                  />
                </label>
              ))}
              <button type="button" className={styles.primary}
                      onClick={() => fileRef.current?.click()} disabled={busy}>
                <Icon name="upload" size={15} /> Upload & run
              </button>
              <input ref={fileRef} type="file" accept={upload.accept} hidden
                     multiple={!!upload.multiple} onChange={(e) => onUpload(e.target.files)} />
            </div>
            <p className={styles.setupNote}>
              Your {upload.label} is saved and run against the golden reference right here.
            </p>
          </div>
        )}

        {customCase && (
          <div className={styles.uploadBox}>
            <div className={styles.uploadHead}>
              <Icon name="sliders" size={15} /> Run your own {customCase.label}
            </div>
            <div className={styles.uploadRow}>
              {(customCase.params || []).map((p) => (
                <label key={p.name} className={styles.uploadField}>
                  <span>{p.label ?? p.name}</span>
                  <input
                    type="text" value={params[p.name] ?? ''}
                    onChange={(e) => setParams((v) => ({ ...v, [p.name]: e.target.value }))}
                    disabled={busy}
                  />
                </label>
              ))}
              <button type="button" className={styles.primary} onClick={onCustom} disabled={busy}>
                <Icon name="play" size={15} /> Run
              </button>
            </div>
          </div>
        )}

        {result && (
          <div className={`${styles.result} ${result.passed === result.total ? styles.ok : styles.bad}`}
               style={{ marginTop: 'var(--space-4)' }}>
            <span className={styles.rate}>
              {result.total ? Math.round((result.passed / result.total) * 100) : 0}%
            </span>
            <span className={styles.rateLabel}>
              {result.passed}/{result.total} cases passed
              <br />
              <span className={styles.muted}>see the “{type}” line on the Trend tab</span>
            </span>
          </div>
        )}
        {error && <p className={styles.error}><Icon name="alert" size={15} /> {error}</p>}
        <LogPane lines={log} label="Run output" />
      </Section>

      <Section
        title={batch ? `Cases — batch “${batch}”` : 'Cases'}
        description={
          batch
            ? `The ${cases.length} synthesized case(s) in this batch. Manage batches on the Tests tab.`
            : `The inputs for this experiment (${experiment.inputs ?? 'from farm.yaml'}). Edit the "${type}" block in farm/farm.yaml to add or change cases, or generate a batch on the Tests tab.`
        }
      >
        {cases.length === 0 ? (
          <p className={styles.muted}>No cases configured.</p>
        ) : (
          <ul className={styles.corpus}>
            {cases.map((c, i) => (
              <li key={`${c.batch ?? ''}-${c.name ?? i}`} className={styles.corpusRow}>
                <span className={styles.corpusName}>
                  {c.name ?? `case ${i + 1}`}
                  {!batch && c.batch && <span className={styles.caseBatch}>{c.batch}</span>}
                </span>
                <span className={styles.corpusBytes}>
                  {Object.entries(c)
                    .filter(([k]) => k !== 'name' && k !== 'batch')
                    .map(([k, v]) => `${k}=${String(v).split('/').pop()}`)
                    .join('  ')}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  )
}
