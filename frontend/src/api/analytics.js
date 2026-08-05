import { delay } from './client'
import * as mock from '@/mock/analytics'

export async function getDashboard() {
  await delay(620)
  return mock.getDashboard()
}

export async function backfillExport(id, metrics) {
  await delay(520)
  return mock.backfillExport(id, metrics)
}
