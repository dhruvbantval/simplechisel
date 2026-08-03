/*
 * Tracks long-running backend jobs above the view tree, so navigating away does
 * not cancel polling or discard the result.
 *
 * Panels look their job up by a stable key (`campaign:control`, `cosim:generate`)
 * and recover the live log and status on remount. Completion posts a toast.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { getJob } from './api'
import { useToast } from '../components/primitives/Toast'

const JobsContext = createContext(null)

export function useJobs() {
  const ctx = useContext(JobsContext)
  if (!ctx) throw new Error('useJobs must be used inside <JobsProvider>')
  return ctx
}

/* Default job state, so callers never handle undefined. */
const IDLE = { status: 'idle', log: [], result: null, error: null, busy: false, label: null }

export function JobsProvider({ children, onNavigate }) {
  // key -> { id, key, kind, label, status, log, result, error, view }
  const [jobs, setJobs] = useState({})
  const { pushToast } = useToast()
  // completion callbacks by key; fire whether or not the panel is mounted
  const onCompleteRef = useRef({})
  const pollingRef = useRef(new Set())

  const patch = useCallback((key, fields) => {
    setJobs((prev) => ({ ...prev, [key]: { ...(prev[key] ?? {}), ...fields } }))
  }, [])

  /*
   * Publish a terminal state and fire the completion callback exactly once.
   * Both are keyed on the job id, so a newer job started under the same key is
   * never overwritten by a slower predecessor.
   */
  const finish = useCallback((key, jobId, snap) => {
    setJobs((prev) => {
      const cur = prev[key]
      if (!cur || cur.id !== jobId) return prev
      return {
        ...prev,
        [key]: {
          ...cur,
          status: snap.status,
          result: snap.run ?? null,
          error: snap.status === 'error' ? (snap.error || 'job failed') : null,
        },
      }
    })
    const cb = onCompleteRef.current[jobId]
    if (cb) {
      delete onCompleteRef.current[jobId]
      cb(snap)
    }
  }, [])

  const poll = useCallback(async (key, jobId) => {
    if (pollingRef.current.has(jobId)) return
    pollingRef.current.add(jobId)
    let since = 0
    try {
      for (;;) {
        const snap = await getJob(jobId, since)
        if (snap.log?.length) {
          since = snap.logLen
          setJobs((prev) => {
            const cur = prev[key]
            if (!cur || cur.id !== jobId) return prev
            return { ...prev, [key]: { ...cur, log: [...cur.log, ...snap.log] } }
          })
        }
        if (snap.status === 'done' || snap.status === 'error') {
          finish(key, jobId, snap)
          return snap
        }
        await new Promise((r) => setTimeout(r, 1500))
      }
    } catch (e) {
      finish(key, jobId, { status: 'error', error: e.message ?? String(e) })
    } finally {
      pollingRef.current.delete(jobId)
    }
  }, [finish])

  /*
   * Start a job and track it.
   *   key         stable id for the owning panel, e.g. "campaign:ecg"
   *   label       display name, used in the toast
   *   view        nav view the toast links to
   *   start       async () => ({ jobId })
   *   onComplete  (snapshot) => void, called on finish
   *   describe    (snapshot) => string for the toast body
   */
  const startJob = useCallback(async ({ key, kind, label, view, start, onComplete, describe }) => {
    patch(key, { key, kind, label, view, id: null, status: 'starting', log: [], result: null, error: null })
    const notify = (snap) => {
      onComplete?.(snap)
      const failed = snap.status === 'error'
      pushToast({
        tone: failed ? 'error' : 'success',
        title: failed ? `${label} failed` : `${label} finished`,
        body: failed ? (snap.error || 'see the log for details') : describe?.(snap),
        onClick: view && onNavigate ? () => onNavigate(view) : undefined,
      })
    }
    try {
      const { jobId } = await start()
      onCompleteRef.current[jobId] = notify
      patch(key, { id: jobId, status: 'running' })
      return poll(key, jobId)
    } catch (e) {
      const msg = e.message ?? String(e)
      patch(key, { status: 'error', error: msg })
      pushToast({ tone: 'error', title: `${label} could not start`, body: msg })
      return { status: 'error', error: msg }
    }
  }, [patch, poll, pushToast, onNavigate])

  /* Reconnect to jobs still running after a reload of this component tree. */
  useEffect(() => {
    for (const [key, job] of Object.entries(jobs)) {
      if (job?.id && job.status === 'running' && !pollingRef.current.has(job.id)) {
        poll(key, job.id)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-arm on job identity changes
  }, [Object.keys(jobs).join('|')])

  const jobFor = useCallback((key) => {
    const j = jobs[key]
    if (!j) return IDLE
    return {
      ...j,
      busy: j.status === 'starting' || j.status === 'running',
      log: j.log ?? [],
    }
  }, [jobs])

  const running = useMemo(
    () => Object.values(jobs).filter((j) => j.status === 'starting' || j.status === 'running'),
    [jobs],
  )

  const value = useMemo(
    () => ({ startJob, jobFor, running }),
    [startJob, jobFor, running],
  )

  return <JobsContext.Provider value={value}>{children}</JobsContext.Provider>
}
