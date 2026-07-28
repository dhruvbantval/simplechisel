/*
 * CPU selector + uploader. Choose which CPU a run builds against — the built-in
 * DINO (Chisel, bug-injectable) or an uploaded set of .sv files. Upload accepts
 * one or more SystemVerilog files; the top module must be `SingleCycleCPU` and
 * expose the same imem/dmem interface plus an internal register file and pc that
 * the trace testbench reads. "Download sample" gives you a known-good DINO to
 * start from.
 */
import { useEffect, useRef, useState } from 'react'
import Icon from '../primitives/Icon'
import { getCpuSample, getCpus, selectCpu, uploadCpu } from '../../data/api'
import styles from './CpuPanel.module.css'

export default function CpuPanel({ onCpuChange }) {
  const [cpus, setCpus] = useState([])
  const [active, setActive] = useState('__builtin__')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const [err, setErr] = useState(null)
  const fileRef = useRef(null)

  const refresh = () =>
    getCpus().then((d) => {
      setCpus(d.cpus ?? [])
      setActive(d.active ?? '__builtin__')
      onCpuChange?.(d.active ?? null)
    }).catch(() => {})

  // Note the arrow body: refresh() returns a Promise, and an effect must return a
  // cleanup function or nothing — returning the Promise makes React call it on
  // unmount and crash. Wrap it so the effect returns undefined.
  useEffect(() => { refresh() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function onSelect(name) {
    setErr(null)
    setMsg(null)
    setBusy(true)
    try {
      await selectCpu(name)
      await refresh()
    } catch (e) {
      setErr(e.message ?? String(e))
    } finally {
      setBusy(false)
    }
  }

  async function onUpload(fileList) {
    const files = [...fileList].filter((f) => f.name.endsWith('.sv') || f.name.endsWith('.v'))
    if (files.length === 0) {
      setErr('pick one or more .sv files')
      return
    }
    setErr(null)
    setMsg(null)
    setBusy(true)
    try {
      const payload = await Promise.all(
        files.map(async (f) => ({ name: f.name, content: await f.text() })),
      )
      const name = files.length === 1
        ? files[0].name.replace(/\.(sv|v)$/, '')
        : `upload-${payload.length}-files`
      const res = await uploadCpu(name, payload)
      if (res.error) {
        setErr(res.error)
      } else {
        setMsg(`Uploaded “${res.name}” (${res.files} file${res.files === 1 ? '' : 's'}) and selected it.`)
        await refresh()
      }
    } catch (e) {
      setErr(e.message ?? String(e))
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function onDownloadSample() {
    setErr(null)
    try {
      const { files } = await getCpuSample()
      // Combine all modules into one re-uploadable .sv file.
      const banner = '// DINO SingleCycleCPU — sample custom CPU for the cosim dashboard.\n'
        + '// Top module SingleCycleCPU. Edit and re-upload to test your own core.\n\n'
      const blob = new Blob(
        [banner + files.map((f) => `// ==== ${f.name} ====\n${f.content}`).join('\n\n')],
        { type: 'text/plain' },
      )
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'dino-sample.sv'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setErr(e.message ?? String(e))
    }
  }

  return (
    <div className={styles.panel}>
      <div className={styles.row}>
        <label className={styles.field}>
          <span className={styles.label}>CPU under test</span>
          <select value={active} onChange={(e) => onSelect(e.target.value)} disabled={busy}>
            {cpus.map((c) => (
              <option key={c.name} value={c.name}>
                {c.label}{!c.builtin ? ` (${c.files} sv)` : ''}
              </option>
            ))}
          </select>
        </label>

        <div className={styles.actions}>
          <button type="button" className={styles.btn} onClick={() => fileRef.current?.click()} disabled={busy}>
            <Icon name="upload" size={15} /> Upload .sv
          </button>
          <button type="button" className={styles.btnGhost} onClick={onDownloadSample} disabled={busy}>
            Download sample
          </button>
          <input
            ref={fileRef} type="file" accept=".sv,.v" multiple hidden
            onChange={(e) => onUpload(e.target.files)}
          />
        </div>
      </div>

      <p className={styles.hint}>
        Your CPU’s top module must be <code>SingleCycleCPU</code> with the same
        <code>io_imem_*</code>/<code>io_dmem_*</code> interface and an internal
        <code>registers.regs[]</code> + <code>pc</code>. Start from the sample.
      </p>
      {msg && <p className={styles.ok}><Icon name="check" size={14} /> {msg}</p>}
      {err && <p className={styles.err}><Icon name="alert" size={14} /> {err}</p>}
    </div>
  )
}
