<template>
  <div class="page">
    <PageHeader
      eyebrow="复盘 · Retrospective"
      title="复盘看板"
      desc="发布后回填真实数据，看互动趋势、各角度表现与回流案例。高表现内容会自动回流进案例库。"
    >
      <template #actions>
        <button class="yc-btn yc-btn--ghost" @click="reload"><Icon name="refresh" :size="15" /> 刷新</button>
        <button class="yc-btn yc-btn--wine" @click="$router.push('/library')"><Icon name="download" :size="15" /> 去回填数据</button>
      </template>
    </PageHeader>

    <!-- LOADING: skeletons shaped like the real board, not spinners -->
    <div v-if="loading" class="db">
      <div class="db-lead db-lead--sk"></div>
      <div class="db-band">
        <Skeleton width="30%" height="12px" />
        <Skeleton variant="block" width="100%" height="240px" />
      </div>
      <div class="db-split">
        <Skeleton variant="block" width="100%" height="260px" />
        <Skeleton variant="block" width="100%" height="260px" />
      </div>
    </div>

    <!-- ERROR -->
    <ErrorState v-else-if="error" title="看板加载失败" :desc="error.message" :code="error.code" @retry="reload" />

    <!-- EMPTY -->
    <EmptyState
      v-else-if="!board"
      icon="chart"
      title="还没有可复盘的数据"
      desc="去生成工作台产出内容，在小红书发布后回到内容库回填浏览 / 点赞 / 收藏，这里就会出现趋势与回流分析。"
    >
      <template #actions>
        <button class="yc-btn yc-btn--wine yc-btn--sm" @click="$router.push('/studio')"><Icon name="spark" :size="14" /> 开始创作</button>
      </template>
    </EmptyState>

    <!-- DATA -->
    <div v-else class="db">
      <!-- ── lead band: one dominant judgment on the night surface ─────────── -->
      <section class="db-lead">
        <div class="db-lead__main">
          <span class="db-lead__label">{{ lead.label }}</span>
          <p class="db-lead__value">
            <span class="yc-num">{{ lead.value }}</span><span class="db-lead__unit">{{ lead.unit }}</span>
          </p>
          <p class="db-lead__delta" :class="Number(lead.delta) >= 0 ? 'is-up' : 'is-down'">
            <Icon name="arrow" :size="14" :style="Number(lead.delta) >= 0 ? 'transform:rotate(-45deg)' : 'transform:rotate(45deg)'" />
            {{ Number(lead.delta) >= 0 ? '+' : '' }}{{ lead.delta }} 对比上一周期
          </p>
          <svg class="db-lead__spark" viewBox="0 0 240 56" preserveAspectRatio="none" aria-hidden="true">
            <polyline :points="leadSpark" fill="none" stroke="var(--blush)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </div>

        <ul class="db-lead__rest">
          <li v-for="k in restKpis" :key="k.key">
            <span class="db-lead__rest-label">{{ k.label }}</span>
            <span class="db-lead__rest-value">
              <span class="yc-num">{{ k.value }}</span><small>{{ k.unit }}</small>
            </span>
            <span class="db-lead__rest-delta" :class="Number(k.delta) >= 0 ? 'is-up' : 'is-down'">
              {{ Number(k.delta) >= 0 ? '+' : '' }}{{ k.delta }}
            </span>
          </li>
        </ul>
      </section>

      <!-- ── trend: full-bleed, no card chrome ─────────────────────────────── -->
      <section class="db-band">
        <header class="db-band__h">
          <h2 class="yc-label">互动趋势</h2>
          <span class="yc-faint yc-mono">近 8 周</span>
        </header>
        <LineChart :series="board.trend.series" :x-labels="board.trend.weeks" :height="250" />
      </section>

      <!-- ── two unequal columns on the inset surface ──────────────────────── -->
      <div class="db-split">
        <section class="db-panel yc-surface">
          <header class="db-band__h">
            <h2 class="yc-label">各选题角度表现</h2>
            <span class="yc-faint yc-mono">已发布篇数</span>
          </header>
          <BarChart
            :categories="board.byAngle.map((a) => a.angle)"
            :values="board.byAngle.map((a) => a.value)"
            :color="varWine"
            :height="230"
          />
        </section>

        <section class="db-panel yc-surface">
          <header class="db-band__h">
            <h2 class="yc-label">内容状态分布</h2>
          </header>
          <DonutChart :segments="board.statusDist" :center-value="statusTotal" center-label="内容总数" />
        </section>
      </div>

      <!-- ── quality rates + backfill entry ────────────────────────────────── -->
      <div class="db-split db-split--rev">
        <section class="db-panel yc-surface">
          <header class="db-band__h">
            <h2 class="yc-label">质量达标率</h2>
          </header>
          <div class="db-rings">
            <ProgressRing v-for="r in board.rates" :key="r.key" :value="r.value" :label="r.label" :color="r.color" />
          </div>
          <p class="yc-note">回流阈值达标的内容会自动进案例库</p>
        </section>

        <section class="db-panel db-backfill">
          <header class="db-band__h">
            <h2 class="yc-label">回填一条真实数据</h2>
          </header>
          <div class="yc-field">
            <label>导出记录</label>
            <select v-model="bfId" class="yc-select">
              <option v-for="e in pendingExports" :key="e.id" :value="e.id">{{ e.title }}</option>
              <option v-if="!pendingExports.length" disabled value="">暂无可回填记录</option>
            </select>
          </div>
          <div class="db-bf">
            <div class="yc-field"><label>浏览</label><input v-model.number="bf.views" type="number" min="0" class="yc-input" /></div>
            <div class="yc-field"><label>点赞</label><input v-model.number="bf.likes" type="number" min="0" class="yc-input" /></div>
            <div class="yc-field"><label>收藏</label><input v-model.number="bf.collects" type="number" min="0" class="yc-input" /></div>
          </div>
          <button class="yc-btn yc-btn--wine yc-btn--sm" :disabled="!bfId" @click="submitBackfill">
            <Icon name="check" :size="14" /> 回填并提交
          </button>
        </section>
      </div>

      <!-- ── recycled table + editorial top list ───────────────────────────── -->
      <div class="db-split db-split--wide">
        <section class="yc-card yc-card--flush db-table">
          <header class="db-band__h db-table__h">
            <h2 class="yc-label">回流案例库</h2>
            <span class="yc-faint yc-mono">{{ board.recycled.length }} 条</span>
          </header>
          <DataTable
            :columns="recycleCols"
            :rows="board.recycled"
            :loading="false"
            :error="null"
            row-key="id"
            :page-size="6"
            empty-title="暂无回流案例"
            empty-desc="当内容表现超过阈值，会自动回流进案例库。"
          >
            <template #cell-title="{ value }"><span class="cell-strong">{{ value }}</span></template>
            <template #cell-views="{ value }"><span class="yc-mono">{{ value.toLocaleString() }}</span></template>
            <template #cell-likes="{ value }"><span class="yc-mono">{{ value.toLocaleString() }}</span></template>
            <template #cell-collects="{ value }"><span class="yc-mono">{{ value.toLocaleString() }}</span></template>
            <template #cell-score="{ value }"><span class="yc-num">{{ value }}</span></template>
            <template #cell-recycled_at="{ value }"><span class="yc-faint">{{ fmtDate(value) }}</span></template>
            <template #cell-status="{ value }">
              <span class="yc-badge" :class="value === 'done' ? 'yc-badge--success' : 'yc-badge--warning'">{{ value === 'done' ? '已回流' : '待确认' }}</span>
            </template>
          </DataTable>
        </section>

        <section class="db-panel db-top">
          <header class="db-band__h">
            <h2 class="yc-label">表现最好的五篇</h2>
          </header>
          <ol class="db-top__list">
            <li v-for="(t, i) in board.top" :key="i" class="db-top__item">
              <span class="db-top__rank yc-ghost">{{ i + 1 }}</span>
              <div class="db-top__meta">
                <strong>{{ t.title }}</strong>
                <span class="yc-faint yc-mono">{{ t.views.toLocaleString() }} 浏览 · 互动率 {{ t.engagement }}%</span>
              </div>
            </li>
          </ol>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import Icon from '@/components/Icon.vue'
import PageHeader from '@/components/PageHeader.vue'
import DataTable from '@/components/DataTable.vue'
import Skeleton from '@/components/Skeleton.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import LineChart from '@/components/charts/LineChart.vue'
import BarChart from '@/components/charts/BarChart.vue'
import DonutChart from '@/components/charts/DonutChart.vue'
import ProgressRing from '@/components/charts/ProgressRing.vue'
import { useToast } from '@/composables/useToast'
import * as analyticsApi from '@/api/analytics'
import * as contentApi from '@/api/content'

const { push } = useToast()
const route = useRoute()
const demo = computed(() => route.query.demo)
const varWine = 'var(--wine)'

const loading = ref(false)
const error = ref(null)
const board = ref(null)

function mkErr() { return Object.assign(new Error('演示错误：分析服务不可用（HTTP 503）。'), { code: 'SERVICE_UNAVAILABLE' }) }

async function reload() {
  loading.value = true
  error.value = null
  if (demo.value === 'loading') return
  if (demo.value === 'error') { error.value = mkErr(); loading.value = false; return }
  try {
    const d = await analyticsApi.getDashboard()
    board.value = demo.value === 'empty' ? null : d
  } catch (e) {
    error.value = e
  } finally {
    if (demo.value !== 'loading') loading.value = false
  }
}

/* One metric leads the board; the rest sit beside it as plain type. */
const lead = computed(() => {
  const k = board.value && board.value.kpis
  return (k && (k.find((x) => x.key === 'eng') || k[0])) || {}
})
const restKpis = computed(() => (board.value ? board.value.kpis.filter((k) => k.key !== lead.value.key) : []))

const leadSpark = computed(() => {
  const s = lead.value.spark
  if (!s || s.length < 2) return ''
  const min = Math.min(...s)
  const max = Math.max(...s)
  const span = max - min || 1
  return s
    .map((v, i) => `${((i / (s.length - 1)) * 240).toFixed(1)},${(56 - ((v - min) / span) * 48 - 4).toFixed(1)}`)
    .join(' ')
})

const statusTotal = computed(() => (board.value ? board.value.statusDist.reduce((a, s) => a + s.value, 0) : 0))

const recycleCols = [
  { key: 'title', label: '标题', skelW: '70%' },
  { key: 'views', label: '浏览', align: 'right', skelW: '30%' },
  { key: 'likes', label: '点赞', align: 'right', skelW: '30%' },
  { key: 'collects', label: '收藏', align: 'right', skelW: '30%' },
  { key: 'score', label: '表现分', align: 'right', skelW: '30%' },
  { key: 'recycled_at', label: '回流时间', align: 'right', skelW: '50%' },
  { key: 'status', label: '状态', skelW: '30%' }
]

/* backfill */
const exports = ref([])
const bfId = ref('')
const bf = ref({ views: 0, likes: 0, collects: 0 })
const pendingExports = computed(() => exports.value.filter((e) => !e.backfilled))

async function loadExports() {
  try {
    const res = await contentApi.listExports()
    exports.value = res.items
    if (!bfId.value && pendingExports.value[0]) bfId.value = pendingExports.value[0].id
  } catch (e) { /* non-blocking */ }
}
async function submitBackfill() {
  if (!bfId.value) return
  try {
    await analyticsApi.backfillExport(bfId.value, { ...bf.value })
    push('已回填，飞轮转动中', 'success')
    await loadExports()
    await reload()
  } catch (e) { push('回填失败：' + e.message, 'error') }
}

function fmtDate(iso) {
  const d = new Date(iso)
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

reload()
loadExports()
</script>

<style scoped>
.db { display: flex; flex-direction: column; gap: var(--sp-8); }

/* ── lead band ────────────────────────────────────────────────────────────
   The one dark surface on the page (brand "night beat"). It carries the
   single judgment the board is about, so the rest of the page can stay calm
   instead of shouting through four identical KPI cards. */
.db-lead {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) 1.15fr;
  gap: var(--sp-8);
  background: var(--night);
  border-radius: var(--r-panel);
  padding: var(--sp-8);
  color: #fff;
  position: relative;
  overflow: hidden;
}
.db-lead--sk { min-height: 220px; display: block; }
.db-lead__main { position: relative; min-width: 0; }
.db-lead__label {
  font-size: var(--fs-caption); font-weight: 700;
  letter-spacing: .16em; text-transform: uppercase;
  color: var(--denim-light);
}
.db-lead__value { margin: var(--sp-2) 0 0; display: flex; align-items: baseline; gap: 6px; }
.db-lead__value .yc-num {
  font-size: clamp(3rem, 7vw, 4.6rem);
  line-height: 1.05; color: #fff; font-weight: 600;
}
.db-lead__unit { font-size: 1.15rem; color: var(--denim-light); }
.db-lead__delta {
  display: inline-flex; align-items: center; gap: 5px;
  margin: var(--sp-2) 0 0; font-size: var(--fs-small);
  color: rgba(255,255,255,.68);
}
.db-lead__delta.is-up { color: #A9D2B0; }
.db-lead__delta.is-down { color: var(--blush-200); }
.db-lead__spark { display: block; width: 100%; height: 56px; margin-top: var(--sp-5, 20px); opacity: .9; }

.db-lead__rest {
  list-style: none; margin: 0; padding: 0;
  display: flex; flex-direction: column; justify-content: center;
  border-left: 1px solid var(--border-dark);
  padding-left: var(--sp-8);
}
.db-lead__rest li {
  display: grid; grid-template-columns: 1fr auto auto;
  align-items: baseline; gap: var(--sp-4);
  padding: var(--sp-4) 0;
  border-bottom: 1px solid var(--border-dark);
}
.db-lead__rest li:last-child { border-bottom: 0; }
.db-lead__rest-label { font-size: var(--fs-small); color: var(--denim-light); }
.db-lead__rest-value { color: #fff; }
.db-lead__rest-value .yc-num { font-size: 1.65rem; }
.db-lead__rest-value small { font-size: var(--fs-caption); color: rgba(255,255,255,.55); margin-left: 3px; }
.db-lead__rest-delta { font-family: var(--font-code); font-size: var(--fs-caption); min-width: 34px; text-align: right; }
.db-lead__rest-delta.is-up { color: #A9D2B0; }
.db-lead__rest-delta.is-down { color: var(--blush-200); }

/* ── open band: chart on the page surface, no card box around it ─────────── */
.db-band { border-top: 1px solid var(--border-default); padding-top: var(--sp-5, 20px); }
.db-band__h {
  display: flex; align-items: baseline; justify-content: space-between;
  gap: var(--sp-3); margin-bottom: var(--sp-4);
}
.db-band__h h2 { font-family: inherit; }

/* ── inset panels ────────────────────────────────────────────────────────── */
.db-split { display: grid; grid-template-columns: 1.5fr 1fr; gap: var(--sp-6); align-items: start; }
.db-split--rev { grid-template-columns: 1fr 1.25fr; }
.db-split--wide { grid-template-columns: 1.7fr 1fr; }
.db-panel { padding: var(--sp-6); border-radius: var(--r-content); }
.db-rings { display: flex; gap: var(--sp-6); flex-wrap: wrap; justify-content: space-around; }
.db-panel .yc-note { margin-top: var(--sp-5, 20px); }

.db-backfill { background: var(--paper); border: 1px solid var(--border-default); }
.db-bf { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--sp-3); margin: var(--sp-3) 0 var(--sp-4); }

.db-table__h { padding: var(--sp-4) var(--sp-6); margin: 0; border-bottom: 1px solid var(--border-subtle); }

/* ── top list: ranked by type weight, not by grey pills ─────────────────── */
.db-top { background: var(--paper); border: 1px solid var(--border-default); }
.db-top__list { list-style: none; margin: 0; padding: 0; }
.db-top__item {
  display: flex; align-items: center; gap: var(--sp-4);
  padding: var(--sp-3) 0;
  border-bottom: 1px solid var(--border-subtle);
}
.db-top__item:last-child { border-bottom: 0; }
.db-top__rank { font-size: 2rem; width: 34px; flex: 0 0 auto; text-align: right; }
.db-top__item:first-child .db-top__rank { opacity: .3; }
.db-top__meta { display: flex; flex-direction: column; gap: 3px; min-width: 0; flex: 1; }
.db-top__meta strong { font-size: var(--fs-small); color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.db-top__meta .yc-faint { font-size: var(--fs-caption); }

@media (max-width: 1080px) {
  .db-lead { grid-template-columns: 1fr; gap: var(--sp-6); }
  .db-lead__rest { border-left: 0; border-top: 1px solid var(--border-dark); padding-left: 0; padding-top: var(--sp-2); }
}
/* the recycled-cases table carries 7 columns; below this it needs the full
   measure rather than sharing the row with the top-five list */
@media (max-width: 1280px) {
  .db-split--wide { grid-template-columns: 1fr; }
}
@media (max-width: 980px) {
  .db-split, .db-split--rev, .db-split--wide { grid-template-columns: 1fr; }
  .db-lead { padding: var(--sp-6); }
}
</style>
