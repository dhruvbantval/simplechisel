/*
 * useRuns — the app's single data hook. Loads persisted runs from IndexedDB on
 * mount, tracks which run is active (newest by default), and exposes async
 * mutations. Components never touch db.js directly; they go through here.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  deleteRecord,
  generateId,
  getActiveId,
  getAllRecords,
  putRecord,
  setActiveId,
} from './db'
import { parseAndValidate, validateRun } from './validateRun'

export function useRuns() {
  const [records, setRecords] = useState([])
  const [activeId, setActive] = useState(null)
  const [status, setStatus] = useState('loading') // 'loading' | 'ready' | 'error'
  const [loadError, setLoadError] = useState(null)

  // Initial load.
  useEffect(() => {
    let cancelled = false
    getAllRecords()
      .then((recs) => {
        if (cancelled) return
        setRecords(recs)
        const stored = getActiveId()
        const exists = recs.some((r) => r.id === stored)
        setActive(exists ? stored : (recs[0]?.id ?? null))
        setStatus('ready')
      })
      .catch((err) => {
        if (cancelled) return
        setLoadError(err.message ?? String(err))
        setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const selectRun = useCallback((id) => {
    setActive(id)
    setActiveId(id)
  }, [])

  // Persist a validated run object. Newest becomes active.
  const addValidatedRun = useCallback(async (run, fileName) => {
    const record = { id: generateId(), fileName, run, uploadedAt: Date.now() }
    await putRecord(record)
    setRecords((prev) => [record, ...prev])
    setActive(record.id)
    setActiveId(record.id)
    return record
  }, [])

  /* Read a File, parse + validate, store it. Returns { ok, errors }. */
  const addRunFromFile = useCallback(
    async (file) => {
      const text = await file.text()
      const { ok, errors, run } = parseAndValidate(text)
      if (!ok) return { ok, errors }
      await addValidatedRun(run, file.name)
      return { ok: true, errors: [] }
    },
    [addValidatedRun],
  )

  /* Load the bundled sample runs (explicit user action from the empty state). */
  const loadSamples = useCallback(
    async (runs) => {
      let last = null
      for (const run of runs) {
        if (!validateRun(run).ok) continue
        // eslint-disable-next-line no-await-in-loop -- keep insertion order/ids deterministic
        last = await addValidatedRun(run, `${run.runId}.json`)
      }
      return last
    },
    [addValidatedRun],
  )

  const removeRun = useCallback(
    async (id) => {
      await deleteRecord(id)
      setRecords((prev) => {
        const next = prev.filter((r) => r.id !== id)
        setActive((current) => {
          if (current !== id) return current
          const fallback = next[0]?.id ?? null
          setActiveId(fallback)
          return fallback
        })
        return next
      })
    },
    [],
  )

  const runs = useMemo(() => records.map((r) => r.run), [records])
  const activeRun = useMemo(
    () => records.find((r) => r.id === activeId)?.run ?? null,
    [records, activeId],
  )

  return {
    status,
    loadError,
    records, // [{ id, fileName, run, uploadedAt }]
    runs, // run objects only
    activeId,
    activeRun,
    selectRun,
    addRunFromFile,
    loadSamples,
    removeRun,
  }
}
