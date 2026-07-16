/*
 * IndexedDB persistence for uploaded runs. One object store keyed by a generated
 * id; each record is { id, fileName, run, uploadedAt }. The active-run selection
 * is small and synchronous-ish, so it lives in localStorage instead.
 *
 * This is the single seam to swap for a real backend/database later: replace the
 * bodies below with fetch() calls and keep the same signatures.
 */

const DB_NAME = 'cpu-dashboard'
const DB_VERSION = 1
const STORE = 'runs'
const ACTIVE_KEY = 'cpu-dashboard:activeRunId'

let dbPromise = null

function openDb() {
  if (dbPromise) return dbPromise
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'id' })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
  return dbPromise
}

function tx(mode, fn) {
  return openDb().then(
    (db) =>
      new Promise((resolve, reject) => {
        const transaction = db.transaction(STORE, mode)
        const store = transaction.objectStore(STORE)
        const result = fn(store)
        transaction.oncomplete = () => resolve(result)
        transaction.onerror = () => reject(transaction.error)
        transaction.onabort = () => reject(transaction.error)
      }),
  )
}

export function generateId() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

/* Returns all records sorted newest-first by uploadedAt. */
export async function getAllRecords() {
  const records = await tx('readonly', (store) => {
    const out = []
    store.openCursor().onsuccess = (e) => {
      const cursor = e.target.result
      if (cursor) {
        out.push(cursor.value)
        cursor.continue()
      }
    }
    return out
  })
  return records.sort((a, b) => b.uploadedAt - a.uploadedAt)
}

export async function putRecord(record) {
  await tx('readwrite', (store) => store.put(record))
  return record
}

export async function deleteRecord(id) {
  await tx('readwrite', (store) => store.delete(id))
}

export function getActiveId() {
  return localStorage.getItem(ACTIVE_KEY)
}

export function setActiveId(id) {
  if (id == null) localStorage.removeItem(ACTIVE_KEY)
  else localStorage.setItem(ACTIVE_KEY, id)
}
