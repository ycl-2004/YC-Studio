/**
 * Knowledge-base API.
 *
 * This is the one domain with real FastAPI endpoints behind it, so every call has
 * both a mock and a live path. The live responses are normalized here — collections
 * arrive as `{collections}` and sources as `{sources}`, and the backend's six ingest
 * states collapse into the three the table renders — so the pages never branch on
 * which layer answered.
 */

import { API_BASE, DEMO_USER_ID, USE_MOCK, delay, request, requestBlob } from './client'
import * as mock from '@/mock/kb'

/** The upload form still has no metadata step; Stage 2 output config supplies these. */
const DEFAULT_UPLOAD_META = { platform: 'general', content_type: 'tutorial' }

/** backend IngestStatus -> the three states KnowledgeBase.vue has a badge for. */
const STATUS_ALIASES = {
  completed: 'done',
  pending: 'processing',
  parsing: 'processing',
  chunking: 'processing',
  embedding: 'processing',
  failed: 'failed'
}

function normalizeStatus(status) {
  return STATUS_ALIASES[status] || 'processing'
}

function normalizeSource(source) {
  return {
    ...source,
    ingest_status: normalizeStatus(source.ingest_status),
    // The list endpoint has no byte size; the preview drawer reads it from disk.
    size_kb: source.size_kb ?? 0,
    title: source.title || source.filename
  }
}

export async function listCollections({ kind } = {}) {
  if (!USE_MOCK) {
    const res = await request(`/api/kb/collections${kind ? `?kind=${kind}` : ''}`)
    return { items: res.collections, total: res.collections.length }
  }
  await delay(520)
  return mock.listCollections(kind)
}

export async function createCollection({ kind, name }) {
  if (!USE_MOCK) {
    return request('/api/kb/collections', { method: 'POST', body: { kind, name } })
  }
  await delay(420)
  return mock.createCollection(kind, name)
}

export async function getCollection(id) {
  if (!USE_MOCK) return request(`/api/kb/collections/${id}`)
  await delay(280)
  return mock.getCollection(id)
}

export async function listSources({ collectionId, empty } = {}) {
  if (!USE_MOCK) {
    const res = await request(`/api/kb/collections/${collectionId}/sources`)
    const items = res.sources.map(normalizeSource)
    return { items, total: items.length }
  }
  await delay(520)
  return mock.listSources(collectionId, empty)
}

export async function deleteSource(id) {
  if (!USE_MOCK) {
    await request(`/api/kb/sources/${id}`, { method: 'DELETE' })
    return { ok: true }
  }
  await delay(360)
  mock.deleteSource(id)
  return { ok: true }
}

export async function deleteCollection(id) {
  if (!USE_MOCK) {
    await request(`/api/kb/collections/${id}`, { method: 'DELETE' })
    return { ok: true }
  }
  await delay(360)
  mock.deleteCollection(id)
  return { ok: true }
}

export async function uploadSource({ collectionId, kind, file, filename, sizeKb }) {
  if (!USE_MOCK) {
    const form = new FormData()
    form.append('file', file, file.name)
    form.append('collection_id', collectionId)
    form.append('kind', kind)
    form.append('platform', DEFAULT_UPLOAD_META.platform)
    form.append('content_type', DEFAULT_UPLOAD_META.content_type)
    const res = await fetch(`${API_BASE}/api/kb/upload`, {
      method: 'POST',
      // No Content-Type header: the browser must set the multipart boundary itself.
      headers: { 'X-User-ID': DEMO_USER_ID },
      body: form
    })
    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      const err = new Error(body.detail || `上传失败：${res.status}`)
      err.code = `HTTP_${res.status}`
      throw err
    }
    return res.json()
  }
  await delay(900)
  return mock.uploadSource(collectionId, filename, sizeKb)
}

export async function searchChunks({ collectionId, kind, query } = {}) {
  if (!USE_MOCK) {
    const res = await request('/api/kb/search', {
      method: 'POST',
      body: { query, kind, top_k: 10 }
    })
    return {
      items: res.results.map((r) => ({
        chunk_id: r.chunk_id,
        source_id: r.source.id,
        title: r.document.title,
        text: r.text,
        score: r.score.toFixed(2)
      })),
      total: res.results.length
    }
  }
  await delay(420)
  return mock.searchChunks(collectionId, query)
}

/** File facts, parsed text and ordered chunks for one uploaded document. */
export async function getSourcePreview(sourceId) {
  if (!USE_MOCK) {
    const res = await request(`/api/kb/sources/${sourceId}/preview`)
    // The drawer renders the same badge as the table, so it needs the same three states.
    return { ...res, ingest_status: normalizeStatus(res.ingest_status) }
  }
  await delay(420)
  return mock.getSourcePreview(sourceId)
}

/**
 * The stored original bytes as a Blob.
 *
 * Throws with code HTTP_404 when only the parsed text survives — the caller shows
 * that as a note next to the parsed text rather than as a failure.
 */
export async function getSourceFile(sourceId, { download = false } = {}) {
  if (!USE_MOCK) {
    return requestBlob(`/api/kb/sources/${sourceId}/file${download ? '?download=true' : ''}`)
  }
  await delay(320)
  return mock.getSourceFile(sourceId)
}
