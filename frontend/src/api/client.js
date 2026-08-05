/**
 * API client core.
 *
 * The project backend (FastAPI) is the source of truth. Every route requires an
 * `X-User-ID` header (JWT lands in Stage 4). For the UI deliverable we run
 * against an in-browser mock layer (USE_MOCK = true) so the five pages are fully
 * functional and demoable without a running backend — and so loading / empty /
 * error states can be exercised. Set VITE_USE_MOCK=false (and VITE_API_BASE) to
 * talk to the real backend; the function shapes below already match the backend
 * schemas in backend/app/schemas/kb.py etc.
 */

/** Only the knowledge-base domain has real endpoints today; the other four pages
 *  are mock-only regardless of this flag. */
export const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false'
export const API_BASE = import.meta.env.VITE_API_BASE ?? ''
export const DEMO_USER_ID = '00000000-0000-0000-0000-000000000001'

export function authHeaders() {
  return {
    'X-User-ID': DEMO_USER_ID,
    'Content-Type': 'application/json'
  }
}

export function delay(ms = 600) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** Thin real-fetch wrapper, kept ready for when USE_MOCK is flipped off. */
export async function request(path, { method = 'GET', body } = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: authHeaders(),
    body: body ? JSON.stringify(body) : undefined
  })
  if (!res.ok) {
    throw await httpError(res)
  }
  if (res.status === 204) return null
  return res.json()
}

/**
 * Fetch a binary response as a Blob.
 *
 * An <iframe src> or <a download> cannot carry the X-User-ID header, so the file
 * is pulled here and handed to the DOM as an object URL. Callers own that URL and
 * must revoke it.
 */
export async function requestBlob(path) {
  const res = await fetch(`${API_BASE}${path}`, { headers: { 'X-User-ID': DEMO_USER_ID } })
  if (!res.ok) {
    throw await httpError(res)
  }
  return res.blob()
}

/** Turn a failed response into an Error carrying the backend's own detail text. */
async function httpError(res) {
  let detail = ''
  try {
    const body = await res.json()
    detail = typeof body?.detail === 'string' ? body.detail : ''
  } catch {
    // A non-JSON error body (proxy timeout, HTML error page) leaves the status only.
  }
  const err = new Error(detail || `请求失败：${res.status}`)
  err.code = `HTTP_${res.status}`
  err.status = res.status
  return err
}
