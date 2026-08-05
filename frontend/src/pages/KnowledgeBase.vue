<template>
  <div class="page">
    <PageHeader
      eyebrow="知识资产 · Knowledge"
      title="知识库管理"
      desc="把参考资料上传进四层分库（案例 / 规则 / 模板 / 素材），解析、分块、嵌入后成为生成与检索的底料。"
    >
      <template #actions>
        <button class="yc-btn yc-btn--soft" @click="showCreate = true">
          <Icon name="plus" :size="16" /> 新建知识库
        </button>
        <button class="yc-btn yc-btn--wine" @click="openUpload(null)">
          <Icon name="upload" :size="16" /> 上传文档
        </button>
      </template>
    </PageHeader>

    <!-- a typographic summary line: same facts, one row, zero card chrome -->
    <div class="kb-meta">
      <span><strong class="yc-num">{{ totals.docs }}</strong> 篇文档</span>
      <span><strong class="yc-num">{{ totals.chunks }}</strong> 个切片</span>
      <span><strong class="yc-num">{{ totals.private }}</strong> 个私有库</span>
      <span class="kb-meta__legend">
        <i v-for="k in kinds" :key="k" :style="{ background: KIND_META[k].color }" :title="KIND_META[k].label"></i>
        四层分库
      </span>
    </div>

    <div class="kb-body">
      <!-- LEFT: collection list -->
      <section class="kb-col yc-card yc-card--flush">
        <div class="kb-col__head">
          <span class="yc-label">四层分库</span>
          <div class="kb-tabs">
            <button v-for="k in kinds" :key="k" :class="{ active: activeKind === k }" @click="activeKind = k">
              {{ KIND_META[k].label }}
            </button>
            <button :class="{ active: activeKind === 'all' }" @click="activeKind = 'all'">全部</button>
          </div>
          <div class="kb-scope">
            <button :class="{ active: scope === 'all' }" @click="scope = 'all'">全部</button>
            <button :class="{ active: scope === 'public' }" @click="scope = 'public'">公共</button>
            <button :class="{ active: scope === 'private' }" @click="scope = 'private'">我的</button>
          </div>
        </div>

        <div class="kb-col__list">
          <template v-if="cLoading">
            <div v-for="i in 4" :key="i" class="kb-col__item kb-col__item--sk">
              <Skeleton variant="circle" width="36px" />
              <div style="flex:1"><Skeleton width="70%" /><br /><Skeleton width="40%" height="10px" /></div>
            </div>
          </template>
          <template v-else-if="cError">
            <ErrorState title="知识库加载失败" :desc="cError.message" :code="cError.code" @retry="reloadCols" />
          </template>
          <template v-else>
            <button
              v-for="c in visibleCols"
              :key="c.id"
              class="kb-col__item"
              :class="{ active: selectedId === c.id }"
              @click="select(c)"
            >
              <span class="kb-col__dot" :style="{ background: KIND_META[c.kind].color }"></span>
              <div class="kb-col__meta">
                <strong>{{ c.name }}</strong>
                <small>{{ c.source_count }} 文档 · {{ c.chunk_count }} 切片</small>
              </div>
              <span class="yc-tag" :class="c.scope === 'public' ? '' : 'yc-tag--wine'">
                {{ c.scope === 'public' ? '公共' : '私有' }}
              </span>
            </button>
            <p v-if="visibleCols.length === 0" class="kb-col__empty">该筛选下暂无知识库，点「新建知识库」开始。</p>
          </template>
        </div>
      </section>

      <!-- RIGHT: source table -->
      <section class="kb-main yc-card yc-card--flush">
        <div class="kb-main__head">
          <div>
            <h2 class="kb-main__title">{{ selected ? selected.name : '请选择左侧知识库' }}</h2>
            <span v-if="selected" class="yc-tag" :class="selected.scope === 'public' ? '' : 'yc-tag--wine'">
              {{ KIND_META[selected.kind].label }} · {{ selected.scope === 'public' ? '公共库' : '私有库' }}
            </span>
          </div>
          <div class="kb-main__tools yc-row yc-wrap">
            <div class="kb-search">
              <Icon name="search" :size="15" />
              <input v-model="query" class="yc-input" placeholder="搜索文件名 / 标题" />
            </div>
            <select v-model="statusFilter" class="yc-select kb-select">
              <option value="">全部状态</option>
              <option value="done">已入库</option>
              <option value="processing">摄取中</option>
              <option value="failed">失败</option>
            </select>
          </div>
        </div>

        <!-- bulk action bar -->
        <div v-if="selectedIds.length" class="kb-bulk yc-row yc-row--between">
          <span>已选 <strong>{{ selectedIds.length }}</strong> 个文档</span>
          <button class="yc-btn yc-btn--danger yc-btn--sm" @click="bulkDelete"><Icon name="trash" :size="14" /> 批量删除</button>
        </div>

        <DataTable
          :columns="srcColumns"
          :rows="filteredSources"
          row-key="source_id"
          :loading="sLoading"
          :error="sError"
          :selectable="true"
          empty-icon="file"
          empty-title="这个知识库还没有文档"
          empty-desc="上传参考资料，系统会解析、分块并嵌入为可检索切片。"
          @retry="reloadSrc"
          @selection-change="(ids) => (selectedIds = ids)"
        >
          <template #cell-filename="{ row }">
            <button class="cell-file cell-file--link" :title="`预览 ${row.filename}`" @click="openPreview(row)">
              <Icon name="file" :size="16" />
              <span class="cell-strong">{{ row.filename }}</span>
            </button>
          </template>
          <template #cell-ingest_status="{ row }">
            <span class="yc-badge" :class="statusMeta[row.ingest_status].cls">
              <span class="dot"></span>{{ statusMeta[row.ingest_status].label }}
            </span>
          </template>
          <template #cell-chunk_count="{ value }"><span class="yc-mono">{{ value }}</span></template>
          <template #cell-size_kb="{ value }"><span class="yc-mono">{{ fmtSize(value) }}</span></template>
          <template #cell-created_at="{ value }"><span class="yc-faint">{{ fmtDate(value) }}</span></template>
          <template #actions="{ row }">
            <button class="yc-btn--icon" title="预览原文与切片" @click="openPreview(row)"><Icon name="doc" :size="15" /></button>
            <button class="yc-btn--icon" title="检索该文档切片" @click="openSearch(row)"><Icon name="search" :size="15" /></button>
            <button class="yc-btn--icon" title="删除" @click="askDelete('source', row)"><Icon name="trash" :size="15" /></button>
          </template>
          <template #empty-actions>
            <button class="yc-btn yc-btn--wine yc-btn--sm" @click="openUpload(selectedId)"><Icon name="upload" :size="14" /> 上传文档</button>
          </template>
        </DataTable>
      </section>
    </div>

    <!-- UPLOAD DRAWER -->
    <Drawer :open="uploadOpen" :title="uploadTargetName" eyebrow="上传文档" @close="closeUpload">
      <div class="yk-field">
        <label>目标知识库</label>
        <select v-model="uploadTarget" class="yc-select" :disabled="!writableCols.length">
          <option v-for="c in writableCols" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
        <small v-if="!writableCols.length" class="yc-faint">
          还没有私有库。公共库由仓库 seed 维护、不接受上传，请先「新建知识库」。
        </small>
      </div>

      <div class="yk-field" style="margin-top: var(--sp-4)">
        <label>选择文件（Markdown / TXT / PDF / DOCX）</label>
        <label class="yk-drop" :class="{ 'is-over': dragOver }"
          @dragover.prevent="dragOver = true" @dragleave.prevent="dragOver = false"
          @drop.prevent="onDrop">
          <Icon name="upload" :size="26" />
          <p>拖拽文件到此处，或 <span class="yc-underline">点击选择</span></p>
          <input type="file" multiple accept=".md,.txt,.pdf,.docx" class="yk-file" @change="onPick" />
        </label>
      </div>

      <ul v-if="pendingFiles.length" class="yk-files">
        <li v-for="(f, i) in pendingFiles" :key="i">
          <Icon name="file" :size="16" />
          <span class="cell-strong">{{ f.name }}</span>
          <span class="yc-faint yc-mono">{{ fmtSize(f.size) }}</span>
          <button class="yk-x" @click="pendingFiles.splice(i, 1)"><Icon name="x" :size="14" /></button>
        </li>
      </ul>

      <div v-if="uploading" class="yk-progress">
        <span class="yc-spin yc-spin--sm"></span>
        <span>正在解析、分块、嵌入… {{ progress }}%</span>
        <div class="yk-bar"><i :style="{ width: progress + '%' }"></i></div>
      </div>

      <template #footer>
        <button class="yc-btn yc-btn--ghost" @click="closeUpload">取消</button>
        <button class="yc-btn yc-btn--wine" :disabled="!pendingFiles.length || uploading" @click="submitUpload">
          <Icon name="check" :size="15" /> 开始摄取
        </button>
      </template>
    </Drawer>

    <!-- CREATE MODAL -->
    <Modal :open="showCreate" title="新建私有知识库" @close="showCreate = false">
      <div class="yk-field">
        <label>库名称</label>
        <input v-model="newName" class="yc-input" placeholder="例如：我的测评笔记" />
        <small class="yc-faint">同名私有库会返回冲突（409）。</small>
      </div>
      <div class="yk-field" style="margin-top: var(--sp-4)">
        <label>知识层</label>
        <div class="yk-kinds">
          <button v-for="k in kinds" :key="k" :class="{ active: newKind === k }" @click="newKind = k">
            {{ KIND_META[k].label }}
          </button>
        </div>
      </div>
      <template #footer>
        <button class="yc-btn yc-btn--ghost" @click="showCreate = false">取消</button>
        <button class="yc-btn yc-btn--wine" :disabled="!newName.trim()" @click="submitCreate">
          <Icon name="plus" :size="15" /> 创建
        </button>
      </template>
    </Modal>

    <!-- DELETE CONFIRM -->
    <Modal :open="!!pending" :title="pending && pending.type === 'collection' ? '删除知识库' : '删除文档'" @close="pending = null">
      <p v-if="pending" class="yk-confirm">
        确定要删除 <strong>{{ pending.name }}</strong> 吗？
        <template v-if="pending.type === 'collection'">其下所有文档与切片将一并移除，且不可恢复。</template>
        <template v-else>文档与切片将被软删除，不再参与检索。</template>
      </p>
      <template #footer>
        <button class="yc-btn yc-btn--ghost" @click="pending = null">取消</button>
        <button class="yc-btn yc-btn--danger" @click="confirmDelete">
          <Icon name="trash" :size="15" /> 确认删除
        </button>
      </template>
    </Modal>

    <!-- PREVIEW DRAWER -->
    <Drawer :open="previewOpen" :title="previewTitle" eyebrow="文档预览" @close="closePreview">
      <template v-if="previewLoading">
        <Skeleton width="60%" /><br /><Skeleton width="90%" /><br /><Skeleton width="80%" />
      </template>

      <ErrorState
        v-else-if="previewError"
        title="无法打开这个文档"
        :desc="previewError.message"
        :code="previewError.code"
        @retry="loadPreview"
      />

      <template v-else-if="preview">
        <!-- 1 · file facts -->
        <dl class="yp-facts">
          <div><dt>文件名</dt><dd class="cell-strong">{{ preview.filename }}</dd></div>
          <div><dt>类型</dt><dd class="yc-mono">{{ preview.suffix || '—' }}</dd></div>
          <div><dt>大小</dt><dd class="yc-mono">{{ fmtBytes(preview.size_bytes) }}</dd></div>
          <div>
            <dt>状态</dt>
            <dd>
              <span class="yc-badge" :class="statusMeta[normalizedStatus].cls">
                <span class="dot"></span>{{ statusMeta[normalizedStatus].label }}
              </span>
            </dd>
          </div>
          <div><dt>切片</dt><dd class="yc-mono">{{ preview.chunk_count }}</dd></div>
          <div><dt>创建时间</dt><dd class="yc-faint">{{ fmtDate(preview.created_at) }}</dd></div>
          <div v-if="preview.dir_path"><dt>目录</dt><dd class="yc-mono">{{ preview.dir_path }}</dd></div>
        </dl>

        <p v-if="preview.error_message" class="yp-note yp-note--error">
          <Icon name="alert" :size="15" /> {{ preview.error_message }}
        </p>

        <!-- 2 · original file / parsed text / chunks -->
        <div class="kb-tabs yp-tabs">
          <button :class="{ active: previewTab === 'original' }" @click="previewTab = 'original'">原始文件</button>
          <button :class="{ active: previewTab === 'parsed' }" @click="previewTab = 'parsed'">解析原文</button>
          <button :class="{ active: previewTab === 'chunks' }" @click="previewTab = 'chunks'">切片 {{ preview.chunk_count }}</button>
        </div>

        <!-- original -->
        <section v-if="previewTab === 'original'" class="yp-pane">
          <p v-if="!preview.original_available" class="yp-note">
            <Icon name="alert" :size="15" />
            这份文档没有留存原始文件（公共种子库与早期上传只保留解析结果），可查看「解析原文」。
          </p>
          <template v-else>
            <div v-if="originalLoading" class="yk-row"><span class="yc-spin yc-spin--sm"></span> 正在读取原始文件…</div>
            <p v-else-if="originalError" class="yp-note yp-note--error">
              <Icon name="alert" :size="15" /> {{ originalError.message }}
              <button class="yc-btn yc-btn--ghost yc-btn--sm" @click="loadOriginal">重试</button>
            </p>
            <pre v-else-if="preview.preview_mode === 'text'" class="yp-code">{{ originalText }}</pre>
            <iframe
              v-else-if="preview.preview_mode === 'pdf' && originalUrl"
              class="yp-frame"
              :src="originalUrl"
              :title="`${preview.filename} 预览`"
            ></iframe>
            <p v-else class="yp-note">
              <Icon name="file" :size="15" />
              {{ preview.suffix || '该格式' }} 不能在浏览器里直接渲染，请下载后用本地应用打开，或查看「解析原文」。
            </p>
          </template>
        </section>

        <!-- parsed -->
        <section v-else-if="previewTab === 'parsed'" class="yp-pane">
          <pre v-if="preview.raw_text" class="yp-code">{{ preview.raw_text }}</pre>
          <p v-else class="yp-note">
            <Icon name="alert" :size="15" /> 这份文档还没有解析结果（摄取未完成或已失败）。
          </p>
          <p v-if="preview.raw_text_truncated" class="yc-faint yp-trunc">
            正文过长，仅显示前 200,000 个字符。
          </p>
        </section>

        <!-- chunks -->
        <section v-else class="yp-pane">
          <ul v-if="preview.chunks.length" class="yk-chunks">
            <li v-for="c in preview.chunks" :key="c.chunk_id">
              <div class="yk-chunk__top">
                <strong>#{{ c.ordinal + 1 }}</strong>
                <span class="yc-mono yc-faint">{{ c.token_count }} tokens</span>
              </div>
              <p>{{ c.text }}</p>
            </li>
          </ul>
          <p v-else class="yp-note"><Icon name="alert" :size="15" /> 这份文档还没有切片。</p>
          <p v-if="preview.chunks_truncated" class="yc-faint yp-trunc">
            仅显示前 {{ preview.chunks.length }} 个切片，共 {{ preview.chunk_count }} 个。
          </p>
        </section>
      </template>

      <template #footer>
        <button
          v-if="preview && preview.original_available"
          class="yc-btn yc-btn--soft"
          @click="downloadOriginal"
        >
          <Icon name="download" :size="15" /> 下载原文件
        </button>
        <button class="yc-btn yc-btn--ghost" @click="closePreview">关闭</button>
      </template>
    </Drawer>

    <!-- SEARCH DRAWER -->
    <Drawer :open="searchOpen" :title="searchTitle" eyebrow="切片检索" @close="searchOpen = false">
      <div class="yk-field">
        <label>检索词（仅 case / material 参与向量检索）</label>
        <div class="yk-row">
          <input v-model="searchQ" class="yc-input" placeholder="例如：通勤穿搭 公式" @keyup.enter="runSearch" />
          <button class="yc-btn yc-btn--soft" @click="runSearch"><Icon name="search" :size="15" /> 检索</button>
        </div>
      </div>
      <div v-if="searchLoading" class="yk-row" style="margin-top: var(--sp-4)"><span class="yc-spin yc-spin--sm"></span> 检索中…</div>
      <ul v-else class="yk-chunks">
        <li v-for="c in searchResults" :key="c.chunk_id">
          <div class="yk-chunk__top"><strong>{{ c.title }}</strong><span class="yc-mono yc-faint">score {{ c.score }}</span></div>
          <p>{{ c.text }}</p>
        </li>
        <li v-if="!searchLoading && searchResults.length === 0" class="yk-chunk--empty">没有匹配的切片，换个检索词试试。</li>
      </ul>
    </Drawer>
  </div>
</template>

<script setup>
import { ref, computed, watch, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import Icon from '@/components/Icon.vue'
import PageHeader from '@/components/PageHeader.vue'
import DataTable from '@/components/DataTable.vue'
import EmptyState from '@/components/EmptyState.vue'
import ErrorState from '@/components/ErrorState.vue'
import Skeleton from '@/components/Skeleton.vue'
import Modal from '@/components/Modal.vue'
import Drawer from '@/components/Drawer.vue'
import { useToast } from '@/composables/useToast'
import * as kb from '@/api/kb'
import { KIND_META } from '@/mock/kb'

const { push } = useToast()
const route = useRoute()
const demo = computed(() => route.query.demo)

const kinds = ['case', 'rule', 'template', 'material']
const statusMeta = {
  done: { label: '已入库', cls: 'yc-badge--success' },
  processing: { label: '摄取中', cls: 'yc-badge--warning' },
  failed: { label: '失败', cls: 'yc-badge--error' }
}

/* ---- collections ---- */
const cLoading = ref(false)
const cError = ref(null)
const collections = ref([])
const activeKind = ref('all')
const scope = ref('all')

async function reloadCols() {
  cLoading.value = true
  cError.value = null
  if (demo.value === 'loading') return
  if (demo.value === 'error') { cError.value = mkErr(); cLoading.value = false; return }
  try {
    const res = await kb.listCollections()
    collections.value = res.items
  } catch (e) {
    cError.value = e
  } finally {
    if (demo.value !== 'loading') cLoading.value = false
  }
}
function mkErr() {
  return Object.assign(new Error('演示错误：无法连接到知识库服务（HTTP 503）。'), { code: 'SERVICE_UNAVAILABLE' })
}

const visibleCols = computed(() =>
  collections.value.filter((c) => (activeKind.value === 'all' || c.kind === activeKind.value) && (scope.value === 'all' || c.scope === scope.value))
)

const selectedId = ref(null)
const selected = computed(() => collections.value.find((c) => c.id === selectedId.value) || null)

function select(c) {
  selectedId.value = c.id
  reloadSrc()
}

const totals = computed(() => {
  const docs = collections.value.reduce((a, c) => a + c.source_count, 0)
  const chunks = collections.value.reduce((a, c) => a + c.chunk_count, 0)
  const priv = collections.value.filter((c) => c.scope === 'private').length
  return {
    docs, chunks, private: priv,
    deltaDocs: 8, deltaChunks: 12,
    sparkDocs: [10, 12, 14, 15, 18, 20, 23, docs || 24],
    sparkChunks: [120, 160, 200, 240, 300, 360, 420, chunks || 480]
  }
})

/* ---- sources ---- */
const sLoading = ref(false)
const sError = ref(null)
const sources = ref([])
const query = ref('')
const statusFilter = ref('')
const selectedIds = ref([])

async function reloadSrc() {
  sLoading.value = true
  sError.value = null
  if (!selectedId.value) { sources.value = []; sLoading.value = false; return }
  if (demo.value === 'loading') return
  if (demo.value === 'error') { sError.value = mkErr(); sLoading.value = false; return }
  try {
    const res = await kb.listSources({ collectionId: selectedId.value, empty: demo.value === 'empty' })
    sources.value = res.items
  } catch (e) {
    sError.value = e
  } finally {
    if (demo.value !== 'loading') sLoading.value = false
  }
}

const filteredSources = computed(() =>
  sources.value.filter((s) => {
    const q = query.value.trim().toLowerCase()
    const matchQ = !q || s.filename.toLowerCase().includes(q) || s.title.toLowerCase().includes(q)
    const matchS = !statusFilter.value || s.ingest_status === statusFilter.value
    return matchQ && matchS
  })
)

const srcColumns = [
  { key: 'filename', label: '文件名', skelW: '70%' },
  { key: 'ingest_status', label: '状态', skelW: '40%', width: '94px' },
  { key: 'chunk_count', label: '切片', align: 'right', skelW: '30%', width: '60px' },
  { key: 'size_kb', label: '大小', align: 'right', skelW: '30%', width: '72px' },
  { key: 'created_at', label: '创建时间', align: 'right', skelW: '50%', width: '96px' }
]

/* ---- upload ---- */
const uploadOpen = ref(false)
const uploadTarget = ref(null)
// The heading names the collection the file will actually land in, so it reads the
// selected target rather than the row highlighted in the sidebar — those two used to
// disagree, and the drawer confidently said "上传到 · 我的素材" while the form was
// pointing somewhere else entirely.
const uploadTargetName = computed(() => {
  const target = collections.value.find((c) => c.id === uploadTarget.value)
  return target ? `上传到 · ${target.name}` : '上传文档'
})
const pendingFiles = ref([])
const dragOver = ref(false)
const uploading = ref(false)
const progress = ref(0)

// Public libraries are seeded from the repo and the API rejects every write to them
// (403), so offering one as an upload target can only ever produce a failed upload.
const writableCols = computed(() => collections.value.filter((c) => c.scope === 'private'))

function openUpload(colId) {
  const preferred = [colId, selectedId.value].find((id) =>
    writableCols.value.some((c) => c.id === id)
  )
  uploadTarget.value = preferred || (writableCols.value[0] && writableCols.value[0].id) || null
  pendingFiles.value = []
  uploading.value = false
  progress.value = 0
  uploadOpen.value = true
}
function closeUpload() { uploadOpen.value = false }
// The File object itself is kept, not just its metadata: the real upload endpoint
// takes multipart bytes, while the mock only ever needed a name and a size.
function onPick(e) {
  for (const f of e.target.files) pendingFiles.value.push({ name: f.name, size: f.size / 1024, file: f })
  e.target.value = ''
}
function onDrop(e) {
  dragOver.value = false
  for (const f of e.dataTransfer.files) pendingFiles.value.push({ name: f.name, size: f.size / 1024, file: f })
}
async function submitUpload() {
  if (!uploadTarget.value) return
  uploading.value = true
  progress.value = 0
  const timer = setInterval(() => { if (progress.value < 92) progress.value += 8 }, 120)
  const target = collections.value.find((c) => c.id === uploadTarget.value)
  try {
    for (const f of pendingFiles.value) {
      await kb.uploadSource({
        collectionId: uploadTarget.value,
        kind: target ? target.kind : 'material',
        file: f.file,
        filename: f.name,
        sizeKb: Math.round(f.size)
      })
    }
    clearInterval(timer)
    progress.value = 100
    push(`已摄取 ${pendingFiles.value.length} 个文档`, 'success')
    await reloadCols()
    await reloadSrc()
    setTimeout(closeUpload, 400)
  } catch (e) {
    clearInterval(timer)
    push('摄取失败：' + e.message, 'error')
  } finally {
    uploading.value = false
  }
}

/* ---- create ---- */
const showCreate = ref(false)
const newName = ref('')
const newKind = ref('case')
async function submitCreate() {
  try {
    await kb.createCollection({ kind: newKind.value, name: newName.value.trim() })
    push('知识库已创建', 'success')
    showCreate.value = false
    newName.value = ''
    await reloadCols()
  } catch (e) {
    push(e.code === 'ALREADY_EXISTS' ? '已存在同名私有库' : '创建失败：' + e.message, 'error')
  }
}

/* ---- delete ---- */
const pending = ref(null)
function askDelete(type, row) {
  pending.value = { type, id: type === 'source' ? row.source_id : row.id, name: type === 'source' ? row.filename : row.name }
}
async function confirmDelete() {
  try {
    if (pending.value.type === 'source') {
      await kb.deleteSource(pending.value.id)
      push('文档已删除', 'success')
    } else {
      await kb.deleteCollection(pending.value.id)
      if (selectedId.value === pending.value.id) selectedId.value = null
      push('知识库已删除', 'success')
    }
    pending.value = null
    await reloadCols()
    await reloadSrc()
  } catch (e) {
    push('删除失败：' + e.message, 'error')
  }
}
async function bulkDelete() {
  for (const id of selectedIds.value) {
    try { await kb.deleteSource(id) } catch (e) { /* continue */ }
  }
  push(`已删除 ${selectedIds.value.length} 个文档`, 'success')
  selectedIds.value = []
  await reloadSrc()
}

/* ---- preview ----
   Two different things are on show here: `preview.raw_text` is the parsed, cleaned
   document the retrieval pipeline actually indexed, while the "原始文件" tab streams
   the bytes that were uploaded. A source can have one without the other. */
const previewOpen = ref(false)
const previewRow = ref(null)
const preview = ref(null)
const previewLoading = ref(false)
const previewError = ref(null)
const previewTab = ref('original')
const originalText = ref('')
const originalUrl = ref('')
const originalLoading = ref(false)
const originalError = ref(null)

const previewTitle = computed(() => (previewRow.value ? previewRow.value.filename : '文档预览'))
const normalizedStatus = computed(() =>
  preview.value && statusMeta[preview.value.ingest_status] ? preview.value.ingest_status : 'processing'
)

function openPreview(row) {
  previewRow.value = row
  previewOpen.value = true
  loadPreview()
}

function closePreview() {
  previewOpen.value = false
  releaseOriginal()
}

async function loadPreview() {
  releaseOriginal()
  preview.value = null
  previewError.value = null
  originalError.value = null
  originalText.value = ''
  previewLoading.value = true
  try {
    preview.value = await kb.getSourcePreview(previewRow.value.source_id)
    // Land on the tab that actually has something in it.
    previewTab.value = preview.value.original_available ? 'original' : 'parsed'
    if (preview.value.original_available) await loadOriginal()
  } catch (e) {
    previewError.value = e
  } finally {
    previewLoading.value = false
  }
}

async function loadOriginal() {
  const p = preview.value
  // A DOCX has no in-browser rendering path, so it is offered as a download only.
  if (!p || !p.original_available || p.preview_mode === 'download') return
  releaseOriginal()
  originalError.value = null
  originalLoading.value = true
  try {
    const blob = await kb.getSourceFile(p.source_id)
    if (p.preview_mode === 'pdf') originalUrl.value = URL.createObjectURL(blob)
    else originalText.value = await blob.text()
  } catch (e) {
    originalError.value = e
  } finally {
    originalLoading.value = false
  }
}

async function downloadOriginal() {
  try {
    const blob = await kb.getSourceFile(preview.value.source_id, { download: true })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = preview.value.filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    // Revoking immediately can cancel a download the browser has not started yet.
    setTimeout(() => URL.revokeObjectURL(url), 10000)
  } catch (e) {
    push('下载失败：' + e.message, 'error')
  }
}

function releaseOriginal() {
  if (!originalUrl.value) return
  URL.revokeObjectURL(originalUrl.value)
  originalUrl.value = ''
}

onUnmounted(releaseOriginal)

/* ---- search ---- */
const searchOpen = ref(false)
const searchTitle = ref('')
const searchQ = ref('')
const searchResults = ref([])
const searchLoading = ref(false)
function openSearch(row) {
  searchTitle.value = `检索 · ${row.title}`
  searchQ.value = ''
  searchResults.value = []
  searchOpen.value = true
}
async function runSearch() {
  if (!selectedId.value) return
  searchLoading.value = true
  try {
    const res = await kb.searchChunks({
      collectionId: selectedId.value,
      kind: selected.value ? selected.value.kind : 'case',
      query: searchQ.value
    })
    searchResults.value = res.items
  } finally {
    searchLoading.value = false
  }
}

/* ---- helpers ---- */
function fmtSize(kb) {
  if (!kb) return '—'
  return kb >= 1024 ? (kb / 1024).toFixed(1) + ' MB' : Math.round(kb) + ' KB'
}
function fmtBytes(bytes) {
  // null means the original file is not stored, which is different from a 0-byte file.
  if (bytes === null || bytes === undefined) return '未留存'
  if (bytes < 1024) return bytes + ' B'
  return fmtSize(bytes / 1024)
}
function fmtDate(iso) {
  const d = new Date(iso)
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

watch(() => collections.value, (v) => {
  if (!selectedId.value && v.length) selectedId.value = v[0].id
}, { immediate: false })

watch(selectedId, (v) => { if (v) reloadSrc() })

reloadCols()
if (selectedId.value) reloadSrc()
</script>

<style scoped>
.kb-meta {
  display: flex; align-items: center; flex-wrap: wrap;
  gap: var(--sp-6); margin-bottom: var(--sp-6);
  font-size: var(--fs-small); color: var(--ink-muted);
}
.kb-meta strong { font-size: 1.3rem; color: var(--ink); margin-right: 4px; }
.kb-meta__legend { display: inline-flex; align-items: center; gap: 5px; margin-left: auto; color: var(--ink-faint); font-size: var(--fs-caption); }
.kb-meta__legend i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
.kb-meta__legend i:last-of-type { margin-right: 4px; }
.kb-body { display: grid; grid-template-columns: 264px minmax(0, 1fr); gap: var(--sp-6); align-items: start; }
.kb-col { position: sticky; top: var(--stick-top); display: flex; flex-direction: column; max-height: calc(var(--view-h) - var(--stick-top) * 2); overflow: hidden; }
.kb-col__head { padding: var(--sp-4); border-bottom: 1px solid var(--border-subtle); display: flex; flex-direction: column; gap: var(--sp-3); flex: 0 0 auto; }
.kb-tabs { display: flex; flex-wrap: wrap; gap: 6px; }
.kb-tabs button, .kb-scope button, .yk-kinds button {
  font-size: var(--fs-caption); padding: 6px 10px; border-radius: var(--r-pill);
  border: 1px solid var(--border-default); background: var(--paper); color: var(--ink-muted);
  transition: all var(--dur-fast) var(--ease-out);
}
.kb-tabs button:hover, .kb-scope button:hover { border-color: var(--denim); color: var(--denim-deep); }
.kb-tabs button.active, .kb-scope button.active {
  background: var(--denim-soft); color: var(--denim-deep);
  border-color: var(--denim-200); font-weight: 700;
}
.yk-kinds button.active { background: var(--denim-soft); color: var(--denim-deep); border-color: var(--denim-200); font-weight: 700; }
.kb-scope { display: flex; gap: 6px; padding-top: var(--sp-3); border-top: 1px dashed var(--border-subtle); }
.kb-col__list { padding: var(--sp-2); display: flex; flex-direction: column; gap: 4px; flex: 1 1 auto; min-height: 0; overflow-y: auto; }
.kb-col__item {
  display: flex; align-items: center; gap: var(--sp-3); width: 100%; text-align: left;
  padding: 10px 12px; border-radius: var(--r-content); border: 1px solid transparent;
  background: transparent; cursor: pointer; transition: all var(--dur-fast) var(--ease-out);
}
.kb-col__item:hover { background: var(--cream-deep); }
.kb-col__item.active { background: var(--denim-50); border-color: var(--denim-200); }
.kb-col__item--sk { gap: var(--sp-3); }
.kb-col__dot { width: 12px; height: 12px; border-radius: 4px; flex: 0 0 auto; }
.kb-col__meta { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.kb-col__meta strong { font-size: var(--fs-small); color: var(--ink); }
.kb-col__meta small { font-size: var(--fs-caption); color: var(--ink-faint); }
.kb-col__empty { padding: var(--sp-6); text-align: center; color: var(--ink-faint); font-size: var(--fs-small); }

.kb-main__head { padding: var(--sp-4) var(--sp-6); border-bottom: 1px solid var(--border-subtle); display: flex; align-items: center; justify-content: space-between; gap: var(--sp-4); flex-wrap: wrap; }
.kb-main__title { font-size: var(--fs-h3); font-family: var(--font-serif); color: var(--ink); margin-bottom: 6px; }
.kb-main__tools { gap: var(--sp-2); }
.kb-search { display: flex; align-items: center; gap: 6px; background: var(--cream-deep); border: 1px solid var(--border-default); border-radius: var(--r-control); padding: 0 10px; color: var(--ink-faint); }
.kb-search:focus-within { border-color: var(--denim); box-shadow: 0 0 0 3px rgba(59,110,165,.16); }
.kb-search input { border: 0; background: transparent; outline: none; width: 180px; padding: 9px 0; font-family: var(--font-sans); font-size: var(--fs-small); color: var(--ink); }
.kb-select { width: auto; min-width: 120px; }
.kb-bulk { margin: var(--sp-3) var(--sp-6) 0; padding: 10px 14px; background: var(--wine-50); border: 1px solid var(--wine-100); border-radius: var(--r-content); font-size: var(--fs-small); color: var(--wine-deep); }
.cell-file { display: flex; align-items: center; gap: 8px; min-width: 0; max-width: 220px; }
.cell-file .cell-strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cell-file :deep(svg) { color: var(--denim); flex: 0 0 auto; }
.cell-file--link { border: 0; background: transparent; padding: 0; cursor: pointer; text-align: left; color: inherit; font: inherit; }
.cell-file--link:hover .cell-strong { color: var(--denim-deep); text-decoration: underline; text-underline-offset: 3px; }
.cell-file--link:focus-visible { outline: 2px solid var(--denim); outline-offset: 3px; border-radius: var(--r-control); }
/* three row actions instead of two need more room than DataTable's default column */
.kb-main :deep(.dt__actions-h), .kb-main :deep(.dt__actions) { width: 128px; }

/* preview drawer */
.yp-facts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--sp-3) var(--sp-4); margin: 0 0 var(--sp-5); }
.yp-facts > div { min-width: 0; }
.yp-facts dt { font-size: var(--fs-caption); color: var(--ink-faint); margin-bottom: 2px; }
.yp-facts dd { margin: 0; font-size: var(--fs-small); color: var(--ink); overflow-wrap: anywhere; }
.yp-note { display: flex; align-items: center; flex-wrap: wrap; gap: var(--sp-2); margin: 0 0 var(--sp-4); padding: 10px 12px; background: var(--cream-deep); border-radius: var(--r-content); font-size: var(--fs-small); color: var(--ink-muted); }
.yp-note :deep(svg) { flex: 0 0 auto; color: var(--ink-faint); }
.yp-note--error { background: var(--error-soft); color: var(--error-deep); }
.yp-note--error :deep(svg) { color: currentColor; }
.yp-tabs { margin-bottom: var(--sp-4); }
.yp-pane { min-height: 120px; }
.yp-code {
  margin: 0; padding: var(--sp-4); max-height: 46vh; overflow: auto;
  background: var(--cream-deep); border: 1px solid var(--border-subtle); border-radius: var(--r-content);
  font-family: var(--font-code); font-size: var(--fs-caption); line-height: 1.75; color: var(--ink);
  white-space: pre-wrap; overflow-wrap: anywhere;
}
.yp-frame { width: 100%; height: 52vh; border: 1px solid var(--border-subtle); border-radius: var(--r-content); background: var(--paper); }
.yp-trunc { margin: var(--sp-2) 0 0; font-size: var(--fs-caption); }
.yp-pane .yk-chunks { margin-top: 0; }

.yk-drop { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: var(--sp-8); border: 1.5px dashed var(--border-dashed); border-radius: var(--r-content); color: var(--ink-muted); cursor: pointer; transition: all var(--dur-base) var(--ease-out); text-align: center; }
.yk-drop.is-over { background: var(--denim-50); border-color: var(--denim); }
.yk-drop :deep(svg) { color: var(--denim); }
.yk-drop p { margin: 0; font-size: var(--fs-small); }
.yk-file { display: none; }
.yk-files { list-style: none; margin: var(--sp-4) 0 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.yk-files li { display: flex; align-items: center; gap: var(--sp-2); padding: 10px 12px; background: var(--cream-deep); border-radius: var(--r-content); font-size: var(--fs-small); }
.yk-files li :deep(svg) { color: var(--denim); }
.yk-files .yc-faint { margin-left: auto; }
.yk-x { margin-left: var(--sp-2); background: transparent; border: 0; color: var(--ink-faint); cursor: pointer; }
.yk-progress { display: flex; align-items: center; gap: var(--sp-2); margin-top: var(--sp-4); font-size: var(--fs-small); color: var(--denim-deep); flex-wrap: wrap; }
.yk-bar { flex: 1; min-width: 120px; height: 6px; background: var(--denim-50); border-radius: var(--r-pill); overflow: hidden; }
.yk-bar i { display: block; height: 100%; background: var(--denim); transition: width var(--dur-base) var(--ease-out); }
.yk-chunks { list-style: none; margin: var(--sp-4) 0 0; padding: 0; display: flex; flex-direction: column; gap: var(--sp-3); }
.yk-chunks li { padding: var(--sp-3); background: var(--cream-deep); border-radius: var(--r-content); }
.yk-chunk__top { display: flex; justify-content: space-between; gap: var(--sp-2); margin-bottom: 4px; }
.yk-chunks p { margin: 0; font-size: var(--fs-small); line-height: 1.7; color: var(--ink-muted); }
.yk-chunk--empty { text-align: center; color: var(--ink-faint); }

/* below this the collection column steals the width the table needs, so the
   two panels stack and the table gets the full measure */
@media (max-width: 1340px) {
  .kb-body { grid-template-columns: 1fr; }
  .kb-col { position: static; max-height: none; }
}
</style>
