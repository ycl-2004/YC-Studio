<template>
  <div class="page">
    <PageHeader
      eyebrow="创作流 · Library"
      title="内容库"
      desc="管理草稿、已导出记录与不可变快照；在别处发布后回来回填浏览 / 点赞 / 收藏，驱动复盘飞轮。"
    >
      <template #actions>
        <button class="yc-btn yc-btn--wine" @click="$router.push('/studio')">
          <Icon name="spark" :size="16" /> 去工作台新建
        </button>
      </template>
    </PageHeader>

    <div class="cl-tabs yc-row">
      <button v-for="t in tabs" :key="t.key" class="cl-tab" :class="{ active: tab === t.key }" @click="tab = t.key">
        {{ t.label }}<span class="cl-tab__c yc-mono">{{ counts[t.key] }}</span>
        <span v-if="t.key === 'exports' && pendingBackfill" class="cl-tab__alert">{{ pendingBackfill }} 待回填</span>
      </button>
    </div>

    <!-- DRAFTS -->
    <section v-show="tab === 'drafts'" class="cl-panel yc-card yc-card--flush">
      <DataTable
        :columns="draftCols"
        :rows="drafts.data.value || []"
        :loading="drafts.loading.value"
        :error="drafts.error.value"
        row-key="id"
        empty-icon="doc"
        empty-title="还没有草稿"
        empty-desc="去生成工作台聊出选题，运行工作流后即可把正文存为草稿。"
        @retry="drafts.reload"
      >
        <template #cell-title="{ value }"><span class="cell-strong">{{ value }}</span></template>
        <template #cell-status="{ value }">
          <span class="yc-badge" :class="STATUS_META[value].tone === 'neutral' ? 'yc-badge--neutral' : 'yc-badge--' + STATUS_META[value].tone">
            {{ STATUS_META[value].label }}
          </span>
        </template>
        <template #cell-config_name="{ value }"><span class="yc-faint">{{ value }}</span></template>
        <template #cell-words="{ value }"><span class="yc-mono">{{ value }}</span></template>
        <template #cell-updated_at="{ value }"><span class="yc-faint">{{ fmtDate(value) }}</span></template>
        <template #actions="{ row }">
          <button class="yc-btn--icon" title="在工作台打开" @click="$router.push('/studio')"><Icon name="edit" :size="15" /></button>
          <button class="yc-btn--icon" title="删除" @click="askDelete(row)"><Icon name="trash" :size="15" /></button>
        </template>
      </DataTable>
    </section>

    <!-- EXPORTS -->
    <section v-show="tab === 'exports'" class="cl-panel yc-card yc-card--flush">
      <DataTable
        :columns="exportCols"
        :rows="exports.data.value || []"
        :loading="exports.loading.value"
        :error="exports.error.value"
        row-key="id"
        empty-icon="download"
        empty-title="还没有导出记录"
        empty-desc="在工作台人审通过后导出，这里会出现 Markdown 成品与快照。"
        @retry="exports.reload"
      >
        <template #cell-title="{ value }"><span class="cell-strong">{{ value }}</span></template>
        <template #cell-platform="{ value }"><span class="yc-tag yc-tag--sel">{{ value }}</span></template>
        <template #cell-format="{ value }"><span class="yc-tag">{{ value }}</span></template>
        <template #cell-exported_at="{ value }"><span class="yc-faint">{{ fmtDate(value) }}</span></template>
        <template #cell-views="{ value }"><span class="yc-mono">{{ value.toLocaleString() }}</span></template>
        <template #cell-likes="{ value }"><span class="yc-mono">{{ value.toLocaleString() }}</span></template>
        <template #cell-collects="{ value }"><span class="yc-mono">{{ value.toLocaleString() }}</span></template>
        <template #cell-backfilled="{ value }">
          <span class="yc-badge" :class="value ? 'yc-badge--success' : 'yc-badge--warning'">{{ value ? '已回填' : '待回填' }}</span>
        </template>
        <template #actions="{ row }">
          <button v-if="!row.backfilled" class="yc-btn--icon" title="回填数据" @click="openBackfill(row)"><Icon name="edit" :size="15" /></button>
          <button class="yc-btn--icon" title="查看快照" @click="viewSnapshot(row)"><Icon name="file" :size="15" /></button>
        </template>
      </DataTable>
    </section>

    <!-- SNAPSHOTS -->
    <section v-show="tab === 'snapshots'" class="cl-panel yc-card yc-card--flush">
      <DataTable
        :columns="snapCols"
        :rows="snaps.data.value || []"
        :loading="snaps.loading.value"
        :error="snaps.error.value"
        row-key="id"
        empty-icon="file"
        empty-title="还没有不可变快照"
        empty-desc="每次导出都会留存一份只读快照，作为历史证据。"
        @retry="snaps.reload"
      >
        <template #cell-title="{ value }"><span class="cell-strong">{{ value }}</span></template>
        <template #cell-created_at="{ value }"><span class="yc-faint">{{ fmtDate(value) }}</span></template>
        <template #actions="{ row }">
          <button class="yc-btn--icon" title="查看" @click="viewSnapshot(row)"><Icon name="file" :size="15" /></button>
        </template>
      </DataTable>
    </section>

    <!-- BACKFILL MODAL -->
    <Modal :open="!!backfillRow" title="回填效果数据" @close="backfillRow = null">
      <p class="yk-confirm">为 <strong>{{ backfillRow && backfillRow.title }}</strong> 回填你在小红书发布后的真实数据。</p>
      <div class="cl-bf">
        <div class="yc-field"><label>浏览量</label><input v-model.number="bf.views" type="number" min="0" class="yc-input" /></div>
        <div class="yc-field"><label>点赞</label><input v-model.number="bf.likes" type="number" min="0" class="yc-input" /></div>
        <div class="yc-field"><label>收藏</label><input v-model.number="bf.collects" type="number" min="0" class="yc-input" /></div>
      </div>
      <template #footer>
        <button class="yc-btn yc-btn--ghost" @click="backfillRow = null">取消</button>
        <button class="yc-btn yc-btn--wine" @click="submitBackfill"><Icon name="check" :size="15" /> 保存</button>
      </template>
    </Modal>

    <!-- SNAPSHOT DRAWER -->
    <Drawer :open="!!snapView" :title="snapView ? snapView.title : ''" eyebrow="不可变快照" @close="snapView = null">
      <div v-if="snapLoading" class="yk-row"><span class="yc-spin yc-spin--sm"></span> 加载中…</div>
      <pre v-else class="cl-snap">{{ snapView && snapView.content }}</pre>
    </Drawer>

    <!-- DELETE CONFIRM -->
    <Modal :open="!!pendingDel" title="删除草稿" @close="pendingDel = null">
      <p class="yk-confirm">确定删除草稿 <strong>{{ pendingDel && pendingDel.title }}</strong> 吗？此操作不可恢复。</p>
      <template #footer>
        <button class="yc-btn yc-btn--ghost" @click="pendingDel = null">取消</button>
        <button class="yc-btn yc-btn--danger" @click="confirmDelete"><Icon name="trash" :size="15" /> 删除</button>
      </template>
    </Modal>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useRoute } from 'vue-router'
import Icon from '@/components/Icon.vue'
import PageHeader from '@/components/PageHeader.vue'
import DataTable from '@/components/DataTable.vue'
import Modal from '@/components/Modal.vue'
import Drawer from '@/components/Drawer.vue'
import { useToast } from '@/composables/useToast'
import * as contentApi from '@/api/content'
import { STATUS_META } from '@/mock/content'

const { push } = useToast()
const route = useRoute()
const demo = computed(() => route.query.demo)

/* small per-dataset loader (handles demo loading/error) */
function useDataset(fetcher) {
  const data = ref(null)
  const loading = ref(false)
  const error = ref(null)
  async function reload() {
    loading.value = true
    error.value = null
    if (demo.value === 'loading') return
    if (demo.value === 'error') { error.value = Object.assign(new Error('演示错误：服务不可用（HTTP 503）。'), { code: 'SERVICE_UNAVAILABLE' }); loading.value = false; return }
    try { data.value = await fetcher() } catch (e) { error.value = e } finally { if (demo.value !== 'loading') loading.value = false }
  }
  reload()
  return { data, loading, error, reload }
}

const tabs = [
  { key: 'drafts', label: '草稿' },
  { key: 'exports', label: '导出记录' },
  { key: 'snapshots', label: '不可变快照' }
]
const tab = ref('drafts')

const drafts = useDataset(() => contentApi.listDrafts().then((r) => (demo.value === 'empty' ? { items: [], total: 0 } : r)).then((r) => r.items))
const exports = useDataset(() => contentApi.listExports({ empty: demo.value === 'empty' }).then((r) => r.items))
const snaps = useDataset(() => contentApi.listSnapshots().then((r) => (demo.value === 'empty' ? [] : r.items)))

const pendingBackfill = computed(() => (exports.data.value || []).filter((e) => !e.backfilled).length)
const counts = computed(() => ({
  drafts: drafts.data.value?.length || 0,
  exports: exports.data.value?.length || 0,
  snapshots: snaps.data.value?.length || 0
}))

const draftCols = [
  { key: 'title', label: '标题', skelW: '70%' },
  { key: 'topic', label: '选题', skelW: '50%' },
  { key: 'angle', label: '角度', skelW: '40%' },
  { key: 'status', label: '状态', skelW: '30%' },
  { key: 'config_name', label: '配置', skelW: '50%' },
  { key: 'words', label: '字数', align: 'right', skelW: '30%' },
  { key: 'updated_at', label: '更新', align: 'right', skelW: '50%' }
]
const exportCols = [
  { key: 'title', label: '标题', skelW: '70%' },
  { key: 'platform', label: '平台', skelW: '30%' },
  { key: 'format', label: '格式', skelW: '30%' },
  { key: 'exported_at', label: '导出时间', skelW: '50%' },
  { key: 'views', label: '浏览', align: 'right', skelW: '30%' },
  { key: 'likes', label: '点赞', align: 'right', skelW: '30%' },
  { key: 'collects', label: '收藏', align: 'right', skelW: '30%' },
  { key: 'backfilled', label: '数据', skelW: '30%' }
]
const snapCols = [
  { key: 'title', label: '标题', skelW: '70%' },
  { key: 'created_at', label: '留存时间', skelW: '50%' }
]

/* delete */
const pendingDel = ref(null)
function askDelete(row) { pendingDel.value = row }
async function confirmDelete() {
  try {
    await contentApi.deleteDraft(pendingDel.value.id)
    push('草稿已删除', 'success')
    pendingDel.value = null
    drafts.reload()
  } catch (e) { push('删除失败：' + e.message, 'error') }
}

/* backfill */
const backfillRow = ref(null)
const bf = reactive({ views: 0, likes: 0, collects: 0 })
function openBackfill(row) {
  backfillRow.value = row
  bf.views = row.views; bf.likes = row.likes; bf.collects = row.collects
}
async function submitBackfill() {
  try {
    await contentApi.backfillMetrics(backfillRow.value.id, { ...bf })
    push('效果数据已回填', 'success')
    backfillRow.value = null
    exports.reload()
  } catch (e) { push('回填失败：' + e.message, 'error') }
}

/* snapshot view */
const snapView = ref(null)
const snapLoading = ref(false)
async function viewSnapshot(row) {
  snapLoading.value = true
  snapView.value = row
  try {
    const full = row.content ? row : await contentApi.getSnapshot(row.id)
    snapView.value = full
  } finally {
    snapLoading.value = false
  }
}

function fmtDate(iso) {
  const d = new Date(iso)
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
</script>

<style scoped>
.cl-tabs { gap: 6px; margin-bottom: var(--sp-4); border-bottom: 1px solid var(--border-subtle); }
.cl-tab { display: inline-flex; align-items: center; gap: 8px; padding: 10px 4px; margin-right: var(--sp-6); background: transparent; border: 0; border-bottom: 2px solid transparent; color: var(--ink-muted); font-size: var(--fs-small); font-weight: 500; cursor: pointer; transition: all var(--dur-fast) var(--ease-out); }
.cl-tab:hover { color: var(--ink); }
.cl-tab.active { color: var(--wine); border-bottom-color: var(--wine); font-weight: 700; }
.cl-tab__c { font-size: var(--fs-caption); color: var(--ink-faint); background: var(--cream-deep); padding: 1px 8px; border-radius: var(--r-pill); }
.cl-tab__alert { font-size: var(--fs-caption); color: var(--warning-deep); background: var(--warning-soft); padding: 1px 8px; border-radius: var(--r-pill); }

.cl-bf { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: var(--sp-3); margin-top: var(--sp-4); }
.cl-snap { white-space: pre-wrap; word-break: break-word; font-family: var(--font-sans); font-size: var(--fs-small); line-height: 1.8; color: var(--ink); background: var(--cream-deep); border-radius: var(--r-content); padding: var(--sp-4); margin: 0; }

@media (max-width: 980px) {
}
</style>
