import { delay } from './client'
import * as mock from '@/mock/config'

export async function listConfigs() {
  await delay(480)
  return mock.listConfigs()
}

export async function getConfig(id) {
  await delay(300)
  return mock.getConfig(id)
}

export async function saveConfig(cfg) {
  await delay(520)
  return mock.saveConfig(cfg)
}

export async function createConfig(name) {
  await delay(320)
  return mock.createConfig(name)
}

export async function deleteConfig(id) {
  await delay(300)
  mock.deleteConfig(id)
  return { ok: true }
}
