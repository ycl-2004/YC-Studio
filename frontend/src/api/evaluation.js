import { USE_MOCK, delay, request } from './client'

const mockRun = {
  id: '00000000-0000-0000-0000-000000000101',
  dataset_id: '00000000-0000-0000-0000-000000000201',
  status: 'completed',
  config_snapshot: {
    retrieval_strategy: 'vector',
    top_k: 5,
    fusion: 'none',
    rerank: false,
    embedding_model: 'BAAI/bge-base-zh-v1.5',
    evaluator_version: 'stage2.v1'
  },
  started_at: '2026-08-05T16:00:00Z',
  finished_at: '2026-08-05T16:00:02Z',
  summary_metrics: {
    case_count: 60,
    recall_at_k: 0.72,
    mrr: 0.58,
    ndcg_at_k: 0.63,
    latency_p50_ms: 31.4,
    latency_p95_ms: 68.2,
    attribution_percentages: {
      not_in_kb: 5,
      not_recalled: 18,
      low_rank: 12,
      hit: 60,
      ambiguous: 5
    }
  },
  error_message: null,
  created_at: '2026-08-05T16:00:00Z'
}

const mockDatasets = [
  {
    id: '00000000-0000-0000-0000-000000000201',
    name: 'Stage 2 demo set',
    version: 'v1',
    construction_method: 'synthetic_plus_manual',
    case_count: 60,
    stats: { total: 80, active: 60, synthetic_total: 60, synthetic_active: 40, manual_active: 20, synthetic_retention_rate: 66.7 }
  }
]

export async function getDatasets() {
  if (USE_MOCK) {
    await delay(220)
    return mockDatasets
  }
  return request('/api/eval/datasets')
}

export async function getRuns() {
  if (USE_MOCK) {
    await delay(320)
    return { runs: [mockRun] }
  }
  return request('/api/eval/runs')
}

export async function triggerRun(datasetId, configOverrides = {}) {
  if (USE_MOCK) {
    await delay(260)
    return { run_id: mockRun.id, status: 'queued' }
  }
  return request('/api/eval/runs', {
    method: 'POST',
    body: { dataset_id: datasetId, config_overrides: configOverrides }
  })
}

export async function compareRuns(currentId, baselineId) {
  if (USE_MOCK) {
    await delay(280)
    return {
      baseline_run_id: baselineId,
      current_run_id: currentId,
      baseline_summary: { recall_at_k: 0.68, mrr: 0.54, ndcg_at_k: 0.59 },
      current_summary: mockRun.summary_metrics,
      config_diff: { evaluator_version: { baseline: 'stage2.v1', current: 'stage2.v1' } },
      case_diffs: [],
      improved_cases: [],
      regressed_cases: []
    }
  }
  return request(`/api/eval/runs/${currentId}/compare?baseline=${baselineId}`)
}
