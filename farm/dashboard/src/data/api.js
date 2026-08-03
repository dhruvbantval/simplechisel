/*
 * Client for the cosim backend (farm/webapp/server.py). Everything the site can
 * "do" — generate tests, inject mutations, poll a running job, list past runs —
 * goes through here so components never build URLs themselves.
 *
 * Base URL resolution:
 *   - dev (vite):        VITE_API_BASE unset -> '' -> vite proxies /api to :8000
 *   - served by python:  same origin -> '' works directly
 *   - Vercel (frontend): set VITE_API_BASE to the remote backend URL at build
 *
 * When no backend is reachable, isLive() is false and the UI hides the
 * generate/mutate controls (a static Vercel deploy can still browse runs the
 * serverless /api/runs route serves).
 */
const API_BASE = import.meta.env.VITE_API_BASE ?? ''

async function req(path, opts) {
  const res = await fetch(`${API_BASE}${path}`, opts)
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json()).error ?? ''
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail || `${res.status} ${res.statusText}`)
  }
  return res.json()
}

const post = (path, body) =>
  req(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })

export const getHealth = () => req('/api/health')
export const getMutations = () => req('/api/mutations')
export const getRuns = () => req('/api/runs')
export const getRun = (runId) => req(`/api/runs/${encodeURIComponent(runId)}`)
// Universal farm records (domain-agnostic; cosim is the first adapter). Feeds the
// cross-domain / regression-trend views.
export const getRecords = () => req('/api/records')

// Experiment types (domains) the farm can run, and the non-cosim domains' runs.
export const getExperiments = () => req('/api/experiments')
// `batch` scopes the case list to one saved batch (omit for every case).
export const getCampaignCases = (type, batch) =>
  req(`/api/campaign/${encodeURIComponent(type)}/cases`
      + (batch ? `?batch=${encodeURIComponent(batch)}` : ''))
// `batch` scopes the run the same way picking a cosim folder does.
export const startCampaign = (type, batch) => post('/api/campaign/run', { type, batch })
export const uploadCase = (type, files, params, encoding) => // files: [{name,content}]
  post(`/api/campaign/${encodeURIComponent(type)}/upload`, { files, params, encoding })
export const runCustomCase = (type, params) =>
  post(`/api/campaign/${encodeURIComponent(type)}/custom`, { params })

/*
 * Generated test batches — the campaign-side equivalent of cosim's test folders.
 * Generate into a *named* batch (re-using a name appends to it), list the saved
 * batches, or delete one.
 */
export const generateCases = (type, count, name) =>
  post(`/api/campaign/${encodeURIComponent(type)}/generate`, { count, name })
export const getBatches = (type) => req(`/api/campaign/${encodeURIComponent(type)}/batches`)
export const deleteBatch = (type, name) =>
  post(`/api/campaign/${encodeURIComponent(type)}/batches/delete`, { name })
export const getJob = (jobId, since = 0) => req(`/api/jobs/${jobId}?since=${since}`)

// Test library: generate saves a named folder; run executes a folder.
export const getFolders = () => req('/api/folders')
export const getFolder = (name) => req(`/api/folders/${encodeURIComponent(name)}`)
// Delete a whole folder, or one program from it (the folder is removed too if
// that was its last program — an empty folder is only ever debris).
export const deleteFolder = (folder) => post('/api/folders/delete', { folder })
export const deleteTest = (folder, test) => post('/api/tests/delete', { folder, test })
export const startGenerate = (params) => post('/api/generate', params) // {name,tests,instrCnt,type}
export const uploadTests = (folder, files) => post('/api/upload-tests', { folder, files }) // your own .S
export const startRun = (params) => post('/api/run', params) // {folder, steps}

// Stateful bug injection: bugs stack on the CPU until reset.
export const getInjected = () => req('/api/injected')
export const injectBug = (fn) => post('/api/inject', { function: fn })
export const resetBugs = () => post('/api/reset', {})

// Custom CPUs: upload .sv files, pick which CPU runs, download a compatible sample.
export const getCpus = () => req('/api/cpus')
export const uploadCpu = (name, files) => post('/api/cpu', { name, files }) // files:[{name,content}]
export const selectCpu = (name) => post('/api/cpu/select', { name })
export const getCpuSample = () => req('/api/cpu/sample')

/*
 * Static runs bundled into the site (public/runs/). Used by a backend-less
 * deploy (e.g. Vercel static) so the dashboard still shows real data. Returns
 * full run objects, or [] if none are bundled.
 */
export async function getStaticRuns() {
  try {
    const index = await fetch('/runs/index.json').then((r) => (r.ok ? r.json() : []))
    const runs = await Promise.all(
      index.map((r) =>
        fetch(`/runs/${encodeURIComponent(r.runId)}.json`).then((res) => (res.ok ? res.json() : null)),
      ),
    )
    return runs.filter(Boolean)
  } catch {
    return []
  }
}

/* Is a live backend reachable? Cached after the first probe. */
let liveProbe = null
export function probeLive() {
  if (!liveProbe) {
    liveProbe = getHealth()
      .then((h) => ({ live: true, health: h }))
      .catch(() => ({ live: false, health: null }))
  }
  return liveProbe
}

/*
 * Poll a job to completion, streaming new log lines to onLog as they arrive.
 * Resolves with the final job snapshot (status 'done' | 'error').
 */
export async function pollJob(jobId, { onLog, interval = 1500, signal } = {}) {
  let since = 0
  for (;;) {
    if (signal?.aborted) throw new Error('cancelled')
    const snap = await getJob(jobId, since)
    if (snap.log?.length) {
      since = snap.logLen
      onLog?.(snap.log)
    }
    if (snap.status === 'done' || snap.status === 'error') return snap
    await new Promise((r) => setTimeout(r, interval))
  }
}
