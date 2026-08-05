<template>
  <div class="page">
    <PageHeader
      eyebrow="知识资产 · Output"
      title="输出配置"
      desc="定义每类内容的生成骨架：结构字段、few-shot 示例与风格约束。生成工作台与导出都以此为蓝本。"
    >
      <template #actions>
        <button class="yc-btn yc-btn--soft" @click="createProfile"><Icon name="plus" :size="16" /> 新建配置</button>
        <button class="yc-btn yc-btn--wine" :disabled="!draft" @click="save"><Icon name="check" :size="16" /> 保存改动</button>
      </template>
    </PageHeader>

    <div class="oc-body">
      <!-- LEFT: profile list -->
      <section class="oc-list yc-card yc-card--flush">
        <div class="oc-list__head">
          <span class="yc-label">配置档案</span>
          <span class="oc-list__count yc-mono">{{ profiles.length }}</span>
        </div>
        <div class="oc-list__items">
          <template v-if="loading">
            <div v-for="i in 3" :key="i" class="oc-list__item">
              <Skeleton width="70%" /><br /><Skeleton width="40%" height="10px" />
            </div>
          </template>
          <template v-else-if="error">
            <ErrorState title="配置加载失败" :desc="error.message" :code="error.code" @retry="reload" />
          </template>
          <template v-else-if="profiles.length === 0">
            <EmptyState icon="sliders" title="还没有输出配置" desc="新建一份配置，定义内容结构与风格约束。" compact>
              <template #actions><button class="yc-btn yc-btn--wine yc-btn--sm" @click="createProfile"><Icon name="plus" :size="14" /> 新建</button></template>
            </EmptyState>
          </template>
          <template v-else>
            <button
              v-for="p in profiles"
              :key="p.id"
              class="oc-list__item"
              :class="{ active: selectedId === p.id }"
              @click="select(p.id)"
            >
              <div class="oc-list__meta">
                <strong>{{ p.name }}</strong>
                <small>{{ p.description }}</small>
              </div>
              <span class="oc-format" :class="'oc-format--' + p.format">{{ p.format }}</span>
            </button>
          </template>
        </div>
      </section>

      <!-- RIGHT: editor -->
      <section v-if="draft" class="oc-editor yc-card">
        <div class="oc-editor__bar yc-row yc-row--between">
          <div class="yc-row">
            <span class="yc-tag yc-tag--wine">{{ draft.platform }}</span>
            <span class="yc-tag">{{ draft.format }}</span>
            <span v-if="dirty" class="oc-dirty">● 未保存</span>
          </div>
          <button class="yc-btn yc-btn--danger yc-btn--sm" @click="askDelete"><Icon name="trash" :size="14" /> 删除</button>
        </div>

        <!-- 基础信息 -->
        <div class="oc-section">
          <h3 class="oc-section__t">基础信息</h3>
          <div class="oc-grid2">
            <div class="yc-field">
              <label>配置名称</label>
              <input v-model="draft.name" class="yc-input" placeholder="配置名称" />
            </div>
            <div class="yc-field">
              <label>内容形式</label>
              <select v-model="draft.format" class="yc-select">
                <option>图文</option>
                <option>视频脚本</option>
              </select>
            </div>
          </div>
          <div class="yc-field" style="margin-top: var(--sp-3)">
            <label>说明</label>
            <input v-model="draft.description" class="yc-input" placeholder="这份配置用来做什么" />
          </div>
        </div>

        <hr class="divider" />

        <!-- 人设与语气 -->
        <div class="oc-section">
          <h3 class="oc-section__t">人设与语气</h3>
          <div class="yc-field">
            <label>人设（persona）</label>
            <textarea v-model="draft.persona" class="yc-textarea" placeholder="你希望 Agent 以怎样的口吻写作？"></textarea>
          </div>
          <div class="oc-grid2" style="margin-top: var(--sp-3)">
            <div class="yc-field">
              <label>语气基调</label>
              <input v-model="draft.tone" class="yc-input" placeholder="如：亲切、专业、不爹味" />
            </div>
            <div class="yc-field">
              <label>话题标签数</label>
              <input v-model.number="draft.hashtag_count" type="number" min="0" max="20" class="yc-input" />
            </div>
          </div>
          <div class="yc-field" style="margin-top: var(--sp-3)">
            <label>Emoji 策略</label>
            <div class="oc-chips">
              <button v-for="(m, key) in EMOJI_POLICY" :key="key"
                class="oc-chip" :class="{ active: draft.emoji_policy === key }" @click="draft.emoji_policy = key">
                {{ m.label }}
              </button>
            </div>
            <small class="yc-faint">{{ EMOJI_POLICY[draft.emoji_policy]?.desc }}</small>
          </div>
          <div class="oc-grid2" style="margin-top: var(--sp-3)">
            <div class="yc-field">
              <label>字数下限</label>
              <input v-model.number="draft.word_range[0]" type="number" min="0" class="yc-input" />
            </div>
            <div class="yc-field">
              <label>字数上限</label>
              <input v-model.number="draft.word_range[1]" type="number" min="0" class="yc-input" />
            </div>
          </div>
        </div>

        <hr class="divider" />

        <!-- 禁用词 -->
        <div class="oc-section">
          <h3 class="oc-section__t">禁用词</h3>
          <div class="oc-banned">
            <span v-for="(w, i) in draft.banned_words" :key="i" class="oc-banned__tag">
              {{ w }} <button @click="draft.banned_words.splice(i, 1)"><Icon name="x" :size="12" /></button>
            </span>
            <input v-model="bannedInput" class="oc-banned__input" placeholder="输入后回车添加" @keyup.enter="addBanned" />
          </div>
        </div>

        <hr class="divider" />

        <!-- 结构定义 -->
        <div class="oc-section">
          <div class="oc-section__h yc-row yc-row--between">
            <h3 class="oc-section__t" style="margin:0">结构定义</h3>
            <button class="yc-btn yc-btn--soft yc-btn--sm" @click="addField"><Icon name="plus" :size="13" /> 字段</button>
          </div>
          <div class="oc-fields">
            <div v-for="(f, i) in draft.structure" :key="i" class="oc-field-row">
              <input v-model="f.label" class="yc-input" placeholder="字段名" />
              <input v-model="f.hint" class="yc-input" placeholder="提示（可选）" />
              <label class="oc-req"><input type="checkbox" v-model="f.required" /> 必填</label>
              <button class="yc-btn--icon" @click="draft.structure.splice(i, 1)"><Icon name="trash" :size="14" /></button>
            </div>
            <p v-if="!draft.structure.length" class="oc-empty">至少保留一个结构字段。</p>
          </div>
        </div>

        <hr class="divider" />

        <!-- few-shot -->
        <div class="oc-section">
          <div class="oc-section__h yc-row yc-row--between">
            <h3 class="oc-section__t" style="margin:0">Few-shot 示例</h3>
            <button class="yc-btn yc-btn--soft yc-btn--sm" @click="addShot"><Icon name="plus" :size="13" /> 示例</button>
          </div>
          <div class="oc-shots">
            <div v-for="(s, i) in draft.few_shot" :key="i" class="oc-shot">
              <div class="oc-shot__head yc-row yc-row--between">
                <span class="yc-label yc-label--muted">示例 {{ i + 1 }}</span>
                <button class="yc-btn--icon yc-btn--sm" @click="draft.few_shot.splice(i, 1)"><Icon name="trash" :size="13" /></button>
              </div>
              <textarea v-model="s.input" class="yc-textarea" placeholder="输入（选题 / 角度）" style="min-height:64px"></textarea>
              <textarea v-model="s.output" class="yc-textarea" placeholder="期望输出" style="min-height:80px"></textarea>
            </div>
            <p v-if="!draft.few_shot.length" class="oc-empty">添加 1–2 个示例，生成质量更稳定。</p>
          </div>
        </div>

        <hr class="divider" />

        <!-- 预览 -->
        <div class="oc-section">
          <h3 class="oc-section__t">实时预览</h3>
          <div class="oc-preview yc-surface">
            <div class="oc-preview__meta">
              <span class="yc-hand">{{ draft.persona || '（未填写人设）' }}</span>
            </div>
            <p class="oc-preview__tone">语气：{{ draft.tone || '—' }} ｜ 字数 {{ draft.word_range[0] }}–{{ draft.word_range[1] }} ｜ Emoji：{{ EMOJI_POLICY[draft.emoji_policy]?.label }}</p>
            <ol class="oc-preview__struct">
              <li v-for="f in draft.structure" :key="f.label">{{ f.label }}<small v-if="f.required" class="oc-req-tag">必填</small></li>
            </ol>
            <p class="oc-preview__banned">禁用词：{{ draft.banned_words.length ? draft.banned_words.join('、') : '无' }}</p>
          </div>
        </div>
      </section>

      <!-- no selection -->
      <section v-else class="oc-empty-pick yc-card">
        <EmptyState icon="sliders" title="选择左侧配置开始编辑" desc="或新建一份输出配置，定义内容结构与风格约束。" />
      </section>
    </div>

    <Modal :open="!!pendingDel" title="删除配置" @close="pendingDel = false">
      <p class="yk-confirm">确定删除配置 <strong>{{ draft && draft.name }}</strong> 吗？此操作不可恢复。</p>
      <template #footer>
        <button class="yc-btn yc-btn--ghost" @click="pendingDel = false">取消</button>
        <button class="yc-btn yc-btn--danger" @click="confirmDelete"><Icon name="trash" :size="15" /> 删除</button>
      </template>
    </Modal>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import Icon from '@/components/Icon.vue'
import PageHeader from '@/components/PageHeader.vue'
import Skeleton from '@/components/Skeleton.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import Modal from '@/components/Modal.vue'
import { useToast } from '@/composables/useToast'
import * as cfgApi from '@/api/config'
import { EMOJI_POLICY } from '@/mock/config'

const { push } = useToast()
const route = useRoute()
const demo = computed(() => route.query.demo)

const loading = ref(false)
const error = ref(null)
const profiles = ref([])
const selectedId = ref(null)
const edits = ref({}) // id -> working draft
const bannedInput = ref('')
const pendingDel = ref(false)

const draft = computed(() => (selectedId.value ? edits.value[selectedId.value] : null))
const dirty = computed(() => {
  if (!draft.value) return false
  const orig = profiles.value.find((p) => p.id === selectedId.value)
  return orig ? JSON.stringify(orig) !== JSON.stringify(draft.value) : true
})

async function reload() {
  loading.value = true
  error.value = null
  if (demo.value === 'error') { error.value = Object.assign(new Error('演示错误：配置服务不可用（HTTP 503）。'), { code: 'SERVICE_UNAVAILABLE' }); loading.value = false; return }
  try {
    const res = await cfgApi.listConfigs()
    profiles.value = res.items
    if (!selectedId.value && profiles.value.length) selectedId.value = profiles.value[0].id
    if (selectedId.value && !edits.value[selectedId.value]) loadDraft(selectedId.value)
  } catch (e) {
    error.value = e
  } finally {
    loading.value = false
  }
}

function loadDraft(id) {
  const p = profiles.value.find((x) => x.id === id)
  if (p) edits.value[id] = JSON.parse(JSON.stringify(p))
}

function select(id) {
  if (id === selectedId.value) return
  selectedId.value = id
  if (!edits.value[id]) loadDraft(id)
}

async function createProfile() {
  const p = await cfgApi.createConfig('未命名配置')
  profiles.value.push(p)
  edits.value[p.id] = JSON.parse(JSON.stringify(p))
  selectedId.value = p.id
  push('已新建配置', 'success')
}

async function save() {
  if (!draft.value) return
  if (!draft.value.name.trim()) { push('请填写配置名称', 'error'); return }
  if (!draft.value.structure.length) { push('至少保留一个结构字段', 'error'); return }
  try {
    const saved = await cfgApi.saveConfig(draft.value)
    const i = profiles.value.findIndex((p) => p.id === saved.id)
    if (i >= 0) profiles.value[i] = saved
    edits.value[saved.id] = JSON.parse(JSON.stringify(saved))
    push('配置已保存', 'success')
  } catch (e) {
    push('保存失败：' + e.message, 'error')
  }
}

function addBanned() {
  const w = bannedInput.value.trim()
  if (w && !draft.value.banned_words.includes(w)) draft.value.banned_words.push(w)
  bannedInput.value = ''
}
function addField() {
  draft.value.structure.push({ key: 'f' + Date.now(), label: '', required: false, hint: '' })
}
function addShot() {
  draft.value.few_shot.push({ input: '', output: '' })
}
function askDelete() { pendingDel.value = true }
async function confirmDelete() {
  try {
    await cfgApi.deleteConfig(selectedId.value)
    delete edits.value[selectedId.value]
    profiles.value = profiles.value.filter((p) => p.id !== selectedId.value)
    selectedId.value = profiles.value[0]?.id || null
    if (selectedId.value) loadDraft(selectedId.value)
    push('配置已删除', 'success')
  } catch (e) {
    push('删除失败：' + e.message, 'error')
  }
  pendingDel.value = false
}

reload()
</script>

<style scoped>
/* Page-level scroll: the .page wrapper must allow the editor (right column)
   to grow past the viewport. The sticky list caps its own height so it
   never blocks page-level scrolling. */
.page { display: block; }

.oc-body { display: grid; grid-template-columns: 300px 1fr; gap: var(--sp-6); align-items: start; }

/* Sticky left list — capped to viewport minus topbar so it can never push
   the page-level scrollbar off-screen. */
.oc-list {
  position: sticky;
  top: var(--stick-top);
  max-height: calc(var(--view-h) - var(--stick-top) * 2);
  display: flex;
  flex-direction: column;
  overflow: hidden;            /* list itself doesn't scroll */
}
.oc-list__head { display: flex; align-items: center; justify-content: space-between; padding: var(--sp-4); border-bottom: 1px solid var(--border-subtle); flex: 0 0 auto; }
.oc-list__count { font-family: var(--font-code); font-size: var(--fs-caption); color: var(--ink-faint); background: var(--cream-deep); padding: 2px 9px; border-radius: var(--r-pill); }
.oc-list__items {
  padding: var(--sp-2);
  display: flex; flex-direction: column; gap: 4px;
  flex: 1 1 auto;               /* fill the remaining sticky height */
  min-height: 0;                /* allow inner scroll without overflowing */
  overflow-y: auto;             /* only the items area scrolls internally */
}
.oc-list__item {
  display: flex; align-items: center; justify-content: space-between; gap: var(--sp-3);
  text-align: left; padding: 14px 16px;
  border-radius: var(--r-content);
  border: 1px solid transparent;
  background: transparent; cursor: pointer;
  transition: all var(--dur-fast) var(--ease-out);
}
.oc-list__item:hover { background: var(--cream-deep); }
.oc-list__item.active { background: var(--denim-50); border-color: var(--denim-200); }
.oc-list__meta { display: flex; flex-direction: column; gap: 4px; min-width: 0; flex: 1; }
.oc-list__meta strong { font-size: var(--fs-small); color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.oc-list__meta small { font-size: var(--fs-caption); color: var(--ink-faint); line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

/* ----- Format tag (图文 / 视频脚本) -----
   Fixed-width pill so both formats occupy identical space regardless of
   character count. Color is the sole differentiator between types. */
.oc-format {
  display: inline-flex; align-items: center; justify-content: center;
  width: 72px; height: 26px;          /* fixed box — both formats identical */
  font-family: var(--font-accent); font-style: italic;
  font-size: var(--fs-caption); letter-spacing: .03em;
  border-radius: var(--r-pill); flex-shrink: 0;
  border: 1.5px solid;
  white-space: nowrap; line-height: 1;
}
.oc-format--视频脚本 { background: var(--blush-50); border-color: var(--blush-100); color: var(--blush-deep); }
.oc-format--图文 { background: var(--denim-soft); border-color: var(--denim-200); color: var(--denim-deep); }
.oc-list__item.active .oc-format { box-shadow: 0 0 0 1.5px currentColor; }

.oc-editor { padding: var(--sp-6); }
.oc-editor__bar { margin-bottom: var(--sp-4); }
.oc-dirty { font-size: var(--fs-caption); color: var(--warning-deep); font-family: var(--font-code); }
.oc-section { margin: 0; }
.oc-section__t { font-family: var(--font-serif); font-size: var(--fs-h3); color: var(--ink); margin-bottom: var(--sp-3); }
.oc-section__h { margin-bottom: var(--sp-3); }
.oc-grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: var(--sp-3); }
.oc-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.oc-chip { font-size: var(--fs-caption); padding: 6px 12px; border-radius: var(--r-pill); border: 1px solid var(--border-default); background: var(--paper); color: var(--ink-muted); transition: all var(--dur-fast) var(--ease-out); }
.oc-chip.active { background: var(--wine); color: #fff; border-color: var(--wine); }
.oc-banned { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.oc-banned__tag { display: inline-flex; align-items: center; gap: 4px; background: var(--wine-50); color: var(--wine-deep); border: 1px solid var(--wine-100); border-radius: var(--r-pill); padding: 4px 10px; font-size: var(--fs-caption); }
.oc-banned__tag button { border: 0; background: transparent; color: var(--wine-deep); cursor: pointer; display: grid; place-items: center; }
.oc-banned__input { border: 1px dashed var(--border-default); border-radius: var(--r-pill); padding: 6px 12px; font-size: var(--fs-caption); background: var(--paper); outline: none; width: 160px; }
.oc-banned__input:focus { border-color: var(--denim); }
.oc-fields { display: flex; flex-direction: column; gap: var(--sp-2); }
.oc-field-row { display: grid; grid-template-columns: 1.2fr 1.6fr auto auto; gap: var(--sp-2); align-items: center; }
.oc-req { font-size: var(--fs-caption); color: var(--ink-muted); display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
.oc-empty { font-size: var(--fs-caption); color: var(--ink-faint); }
.oc-shots { display: flex; flex-direction: column; gap: var(--sp-3); }
.oc-shot { padding: var(--sp-3); background: var(--cream-deep); border-radius: var(--r-content); display: flex; flex-direction: column; gap: 8px; }
.oc-shot__head { margin-bottom: 2px; }
.oc-preview { padding: var(--sp-4); }
.oc-preview__meta { margin-bottom: var(--sp-2); }
.oc-preview__tone { font-size: var(--fs-caption); color: var(--ink-muted); margin: 0 0 var(--sp-2); }
.oc-preview__struct { margin: 0; padding-left: 20px; display: flex; flex-direction: column; gap: 4px; font-size: var(--fs-small); color: var(--ink); }
.oc-req-tag { font-size: 10px; color: var(--wine-deep); margin-left: 6px; font-family: var(--font-code); }
.oc-preview__banned { font-size: var(--fs-caption); color: var(--ink-faint); margin: var(--sp-2) 0 0; }
.oc-empty-pick { display: grid; place-items: center; }

@media (max-width: 980px) {
  .oc-body { grid-template-columns: 1fr; }
  .oc-list { position: static; max-height: none; }
  .oc-grid2 { grid-template-columns: 1fr; }
  .oc-field-row { grid-template-columns: 1fr 1fr; }
}
</style>
