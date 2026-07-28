/*
 * A generic experiment page. Any experiment declared in farm.yaml with
 * `ui: campaign` renders through this: it shows what's being tested against what,
 * lists the cases from the config, and runs the whole campaign with one button.
 *
 * It knows nothing about PIDs, heartbeats or circuits — all of that lives in the
 * config and the adapter. That's why adding a science needs no new UI.
 */
import { useEffect, useRef, useState } from 'react'
import Section from '../primitives/Section'
import Icon from '../primitives/Icon'
import {
  generateCases,
  getCampaignCases,
  pollJob,
  runCustomCase,
  startCampaign,
  uploadCase,
} from '../../data/api'
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

export default function CampaignPanel({ live, experiment }) {
  const [cases, setCases] = useState([])
  const [busy, setBusy] = useState(false)
  const [log, setLog] = useState([])
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [params, setParams] = useState({})
  const logRef = useRef(null)
  const fileRef = useRef(null)

  const type = experiment?.type
  const upload = experiment?.upload
  const customCase = experiment?.custom_case
  const generate = experiment?.generate
  const [genCount, setGenCount] = useState(generate?.default ?? 5)
  const [genBusy, setGenBusy] = useState(false)

  useEffect(() => {
    setCases([]); setResult(null); setLog([]); setError(null)
    setGenCount(generate?.default ?? 5)
    // seed the upload-form params from their defaults
    setParams(Object.fromEntries(
      [...(upload?.params || []), ...(customCase?.params || [])].map((p) => [p.name, p.default ?? '']),
    ))
    if (live && type) {
      getCampaignCases(type).then((d) => setCases(d.cases || [])).catch(() => {})
    }
  }, [live, type, upload, customCase, generate])

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [log])

  async function track(startFn, label) {
    setBusy(true); setLog([]); setResult(null); setError(null)
    try {
      const { jobId } = await startFn()
      const snap = await pollJob(jobId, { onLog: (lines) => setLog((p) => [...p, ...lines]) })
      if (snap.status === 'error') setError(snap.error || 'run failed')
      else if (snap.run) setResult({
        passed: snap.run.passed, total: snap.run.totalTests,
        detail: snap.run.detail, label,
      })
    } catch (e) {
      setError(e.message ?? String(e))
    } finally {
      setBusy(false)
    }
  }

  const onRun = () => track(() => startCampaign(type), 'campaign')

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
    await track(() => uploadCase(type, files, pick(upload?.params), binary ? 'base64' : undefined), 'upload')
    getCampaignCases(type).then((d) => setCases(d.cases || [])).catch(() => {})
    if (fileRef.current) fileRef.current.value = ''
  }

  const onCustom = () => track(() => runCustomCase(type, pick(customCase?.params)), 'custom')

  async function onGenerate() {
    setGenBusy(true); setError(null)
    try {
      const n = Math.max(1, Math.min(50, Number(genCount) || generate?.default || 5))
      const res = await generateCases(type, n)
      const d = await getCampaignCases(type)
      setCases(d.cases || [])
      setResult(null)
      setLog([`generated ${res.count} test case(s) — they're in the Cases list below; hit Run to score them`])
    } catch (e) {
      setError(e.message ?? String(e))
    } finally {
      setGenBusy(false)
    }
  }

  if (!experiment) return null

  return (
    <div className={styles.main}>
      <Section
        title={experiment.label}
        description={`${experiment.dut} checked against ${experiment.golden}. Every case must agree with the golden reference; the headline number is ${experiment.metric ?? 'the domain metric'}.`}
      >
        <div className={styles.runRow}>
          <button type="button" className={styles.primary} onClick={onRun} disabled={busy || !type}>
            <Icon name="play" size={16} /> {busy ? 'Running…' : `Run ${experiment.label}`}
          </button>
        </div>

        {generate && (
          <div className={styles.uploadBox}>
            <div className={styles.uploadHead}>
              <Icon name="generate" size={15} /> Generate tests — {generate.label}
            </div>
            <div className={styles.uploadRow}>
              <label className={styles.uploadField}>
                <span>how many</span>
                <input
                  type="number" min="1" max="50" step="1" value={genCount}
                  onChange={(e) => setGenCount(e.target.value)}
                  disabled={busy || genBusy}
                />
              </label>
              <button type="button" className={styles.primary} onClick={onGenerate}
                      disabled={busy || genBusy || !type}>
                <Icon name="generate" size={15} /> {genBusy ? 'Generating…' : 'Generate'}
              </button>
            </div>
            <p className={styles.setupNote}>
              Synthesizes {generate.label} with a known-correct answer, adds them to the
              Cases list below, then hit “Run” to score them — no files to drop in.
            </p>
          </div>
        )}

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
        {log.length > 0 && <pre className={styles.log} ref={logRef}>{log.join('\n')}</pre>}
      </Section>

      <Section
        title="Cases"
        description={`The inputs for this experiment (${experiment.inputs ?? 'from farm.yaml'}). Edit the "${type}" block in farm/farm.yaml to add or change cases.`}
      >
        {cases.length === 0 ? (
          <p className={styles.muted}>No cases configured.</p>
        ) : (
          <ul className={styles.corpus}>
            {cases.map((c, i) => (
              <li key={c.name ?? i} className={styles.corpusRow}>
                <span className={styles.corpusName}>{c.name ?? `case ${i + 1}`}</span>
                <span className={styles.corpusBytes}>
                  {Object.entries(c)
                    .filter(([k]) => k !== 'name')
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
