<template>
  <div class="page eval-page">
    <PageHeader
      eyebrow="度量 · Evaluation"
      title="检索评测"
      desc="先冻结配置，再看每次检索究竟错在知识库、召回集合还是排序。"
    >
      <template #actions>
        <select v-model="selectedDataset" class="yc-select eval-select" :disabled="!datasets.length">
          <option value="" disabled>选择评测集</option>
          <option v-for="dataset in datasets" :key="dataset.id" :value="dataset.id">
            {{ dataset.name }} · {{ dataset.stats?.active ?? dataset.case_count }} 条
          </option>
        </select>
        <button class="yc-btn yc-btn--wine" :disabled="!selectedDataset || triggering" @click="runBaseline">
          {{ triggering ? '已排队…' : '跑一次 baseline' }}
        </button>
        <button class="yc-btn yc-btn--ghost" @click="reload">刷新</button>
      </template>
    </PageHeader>

    <div v-if="loading" class="eval-loading yc-card">正在读取评测记录…</div>
    <ErrorState v-else-if="error" title="评测记录加载失败" :desc="error.message" :code="error.code" @retry="reload" />
    <EmptyState
      v-else-if="!runs.length"
      icon="chart"
      title="还没有跑分记录"
      desc="先创建评测集并生成至少一条用例，然后从这里触发异步 baseline。"
    />
    <template v-else>
      <section class="eval-overview">
        <article v-for="metric in headlineMetrics" :key="metric.key" class="yc-card eval-kpi">
          <span class="yc-label yc-label--muted">{{ metric.label }}</span>
          <strong class="yc-num">{{ metric.value }}</strong>
          <small>{{ metric.note }}</small>
        </article>
      </section>

      <section class="yc-card eval-runs">
        <div class="eval-section-head">
          <div>
            <h2 class="yc-label">跑分记录</h2>
            <p class="yc-faint">配置快照随 run 保存，停用用例不会改写历史结果。</p>
          </div>
          <div class="eval-compare-controls">
            <select v-model="baselineId" class="yc-select">
              <option value="">选择 baseline</option>
              <option v-for="run in runs" :key="run.id" :value="run.id">{{ shortId(run.id) }}</option>
            </select>
            <select v-model="currentId" class="yc-select">
              <option value="">选择对比 run</option>
              <option v-for="run in runs" :key="run.id" :value="run.id">{{ shortId(run.id) }}</option>
            </select>
            <button class="yc-btn yc-btn--soft yc-btn--sm" :disabled="!canCompare || comparing" @click="compare">
              {{ comparing ? '比较中…' : '比较' }}
            </button>
          </div>
        </div>

        <div class="eval-table-wrap">
          <table class="eval-table">
            <thead>
              <tr><th>Run</th><th>状态</th><th>用例</th><th>Recall@5</th><th>MRR</th><th>NDCG@5</th><th>P95</th><th>归因主类</th></tr>
            </thead>
            <tbody>
              <tr v-for="run in runs" :key="run.id" :class="{ 'is-selected': run.id === currentId }" @click="currentId = run.id">
                <td class="yc-mono">{{ shortId(run.id) }}</td>
                <td><span class="yc-badge" :class="statusClass(run.status)"><span class="dot"></span>{{ statusText(run.status) }}</span></td>
                <td>{{ run.summary_metrics?.case_count ?? '—' }}</td>
                <td class="yc-num">{{ pct(run.summary_metrics?.recall_at_k) }}</td>
                <td class="yc-num">{{ pct(run.summary_metrics?.mrr) }}</td>
                <td class="yc-num">{{ pct(run.summary_metrics?.ndcg_at_k) }}</td>
                <td class="yc-mono">{{ ms(run.summary_metrics?.latency_p95_ms) }}</td>
                <td>{{ leadingAttribution(run.summary_metrics?.attribution_percentages) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section v-if="comparison" class="yc-card eval-compare">
        <div class="eval-section-head">
          <div><h2 class="yc-label">对比结果</h2><p class="yc-faint">逐项显示变好与变差的用例。</p></div>
          <span class="yc-tag yc-tag--sel">{{ comparison.improved_cases.length }} 条变好 · {{ comparison.regressed_cases.length }} 条变差</span>
        </div>
        <div class="eval-diff-grid">
          <div v-for="metric in compareMetrics" :key="metric.key" class="eval-diff">
            <span>{{ metric.label }}</span>
            <strong class="yc-num">{{ signedDelta(metric.key) }}</strong>
          </div>
        </div>
        <details class="eval-config"><summary>查看配置差异（{{ Object.keys(comparison.config_diff).length }} 项）</summary><pre>{{ JSON.stringify(comparison.config_diff, null, 2) }}</pre></details>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import * as evaluationApi from '@/api/evaluation'

const datasets = ref([])
const runs = ref([])
const comparison = ref(null)
const selectedDataset = ref('')
const baselineId = ref('')
const currentId = ref('')
const loading = ref(true)
const triggering = ref(false)
const comparing = ref(false)
const error = ref(null)

const latest = computed(() => runs.value[0]?.summary_metrics || {})
const headlineMetrics = computed(() => [
  { key: 'recall_at_k', label: 'Recall@5', value: pct(latest.value.recall_at_k), note: '相关 chunk 召回率' },
  { key: 'mrr', label: 'MRR', value: pct(latest.value.mrr), note: '首个命中排序质量' },
  { key: 'ndcg_at_k', label: 'NDCG@5', value: pct(latest.value.ndcg_at_k), note: '整体排序质量' },
  { key: 'latency_p95_ms', label: 'P95 延迟', value: ms(latest.value.latency_p95_ms), note: '检索耗时' }
])
const compareMetrics = [
  { key: 'recall_at_k', label: 'Recall@5' },
  { key: 'mrr', label: 'MRR' },
  { key: 'ndcg_at_k', label: 'NDCG@5' }
]
const canCompare = computed(() => baselineId.value && currentId.value && baselineId.value !== currentId.value)

async function reload() {
  loading.value = true
  error.value = null
  try {
    const [datasetResponse, runResponse] = await Promise.all([evaluationApi.getDatasets(), evaluationApi.getRuns()])
    datasets.value = datasetResponse
    runs.value = runResponse.runs || []
    if (!selectedDataset.value && datasets.value[0]) selectedDataset.value = datasets.value[0].id
    if (!currentId.value && runs.value[0]) currentId.value = runs.value[0].id
  } catch (err) {
    error.value = err
  } finally {
    loading.value = false
  }
}

async function runBaseline() {
  triggering.value = true
  try { await evaluationApi.triggerRun(selectedDataset.value); await reload() } catch (err) { error.value = err } finally { triggering.value = false }
}

async function compare() {
  comparing.value = true
  try { comparison.value = await evaluationApi.compareRuns(currentId.value, baselineId.value) } catch (err) { error.value = err } finally { comparing.value = false }
}

function pct(value) { return typeof value === 'number' ? `${(value * 100).toFixed(1)}%` : '—' }
function ms(value) { return typeof value === 'number' ? `${value.toFixed(1)} ms` : '—' }
function shortId(id) { return id ? id.slice(0, 8) : '—' }
function statusText(value) { return ({ queued: '排队中', running: '运行中', completed: '完成', failed: '失败' })[value] || value }
function statusClass(value) { return ({ queued: 'yc-badge--warning', running: 'yc-badge--info', completed: 'yc-badge--success', failed: 'yc-badge--error' })[value] || 'yc-badge--neutral' }
function leadingAttribution(values) {
  if (!values) return '—'
  const [key, value] = Object.entries(values).sort((a, b) => b[1] - a[1])[0] || []
  return key ? `${key} ${(value || 0).toFixed(1)}%` : '—'
}
function signedDelta(key) {
  const delta = (comparison.value?.current_summary?.[key] || 0) - (comparison.value?.baseline_summary?.[key] || 0)
  return `${delta >= 0 ? '+' : ''}${(delta * 100).toFixed(1)} pp`
}

onMounted(reload)
</script>

<style scoped>
.eval-page { display: flex; flex-direction: column; gap: var(--sp-6); }
.eval-loading { color: var(--ink-muted); }
.eval-select { width: auto; min-width: 190px; }
.eval-overview { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--sp-4); }
.eval-kpi { display: flex; flex-direction: column; gap: var(--sp-2); }
.eval-kpi strong { font-size: 2rem; color: var(--wine-deep); }
.eval-kpi small { color: var(--ink-faint); }
.eval-section-head { display: flex; align-items: center; justify-content: space-between; gap: var(--sp-4); margin-bottom: var(--sp-4); }
.eval-section-head p { margin: var(--sp-2) 0 0; font-size: var(--fs-small); }
.eval-compare-controls { display: flex; align-items: center; gap: var(--sp-2); }
.eval-compare-controls .yc-select { width: auto; min-width: 128px; }
.eval-table-wrap { overflow-x: auto; }
.eval-table { width: 100%; border-collapse: collapse; font-size: var(--fs-small); }
.eval-table th, .eval-table td { padding: 12px 10px; text-align: left; border-top: 1px solid var(--border-subtle); white-space: nowrap; }
.eval-table th { color: var(--ink-faint); font-size: var(--fs-caption); font-weight: 700; letter-spacing: .06em; }
.eval-table tbody tr { cursor: pointer; transition: background var(--dur-fast) var(--ease-out); }
.eval-table tbody tr:hover, .eval-table tbody tr.is-selected { background: var(--denim-50); }
.eval-diff-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--sp-3); }
.eval-diff { background: var(--cream-deep); border: 1px solid var(--border-subtle); border-radius: var(--r-content); padding: var(--sp-4); display: flex; justify-content: space-between; gap: var(--sp-3); }
.eval-diff strong { color: var(--success-deep); }
.eval-config { margin-top: var(--sp-4); color: var(--ink-muted); font-size: var(--fs-small); }
.eval-config pre { overflow-x: auto; background: var(--night); color: #f4eee2; padding: var(--sp-4); border-radius: var(--r-content); font-size: var(--fs-caption); }
@media (max-width: 900px) { .eval-overview { grid-template-columns: repeat(2, minmax(0, 1fr)); } .eval-section-head { align-items: flex-start; flex-direction: column; } .eval-compare-controls { width: 100%; flex-wrap: wrap; } }
@media (max-width: 560px) { .eval-overview { grid-template-columns: 1fr; } .eval-compare-controls .yc-select { flex: 1; min-width: 0; } }
</style>
