import { delay } from './client'
import * as mock from '@/mock/content'

export async function listDrafts() {
  await delay(480)
  return mock.listDrafts()
}

export async function listExports({ empty } = {}) {
  await delay(480)
  if (empty) return { items: [], total: 0 }
  return mock.listExports()
}

export async function listSnapshots(exportId) {
  await delay(320)
  return mock.listSnapshots(exportId)
}

export async function getSnapshot(id) {
  await delay(260)
  return mock.getSnapshot(id)
}

export async function deleteDraft(id) {
  await delay(300)
  mock.deleteDraft(id)
  return { ok: true }
}

export async function backfillMetrics(id, metrics) {
  await delay(520)
  return mock.backfillMetrics(id, metrics)
}
