/* In-browser mock for the Knowledge Base domain.
   Mirrors backend/app/schemas/kb.py shapes (CollectionSummary / SourceSummary). */

let _seq = 100
const uid = (p = 'c') => `${p}_${(++_seq).toString(36)}${Date.now().toString(36).slice(-4)}`

const KIND_LABEL = { case: '案例库', rule: '规则库', template: '模板库', material: '素材库' }

const collections = [
  { id: 'col_pub_case', kind: 'case', scope: 'public', name: '案例库 · 公共', source_count: 12, document_count: 12, chunk_count: 386 },
  { id: 'col_pub_rule', kind: 'rule', scope: 'public', name: '规则库 · 公共', source_count: 2, document_count: 2, chunk_count: 28 },
  { id: 'col_pub_template', kind: 'template', scope: 'public', name: '模板库 · 公共', source_count: 3, document_count: 3, chunk_count: 41 },
  { id: 'col_pub_material', kind: 'material', scope: 'public', name: '素材库 · 公共', source_count: 8, document_count: 8, chunk_count: 174 },
  { id: 'col_priv_case', kind: 'case', scope: 'private', name: '我的案例', source_count: 4, document_count: 4, chunk_count: 96 },
  { id: 'col_priv_material', kind: 'material', scope: 'private', name: '我的素材', source_count: 5, document_count: 5, chunk_count: 120 },
  { id: 'col_priv_rule', kind: 'rule', scope: 'private', name: '我的笔记方法', source_count: 1, document_count: 1, chunk_count: 17 }
]

const sources = [
  // public case
  { source_id: 'src_01', collection_id: 'col_pub_case', filename: '护肤爆款拆解-早C晚A.md', title: '早C晚A 护肤爆款拆解', ingest_status: 'done', chunk_count: 42, size_kb: 38, created_at: '2026-07-28T09:12:00Z' },
  { source_id: 'src_02', collection_id: 'col_pub_case', filename: '职场穿搭-通勤三件套.md', title: '通勤穿搭三件套拆解', ingest_status: 'done', chunk_count: 31, size_kb: 29, created_at: '2026-07-26T14:03:00Z' },
  { source_id: 'src_03', collection_id: 'col_pub_case', filename: '减脂餐-21天打卡.md', title: '21 天减脂餐打卡', ingest_status: 'done', chunk_count: 55, size_kb: 61, created_at: '2026-07-21T10:40:00Z' },
  { source_id: 'src_04', collection_id: 'col_pub_case', filename: '租房改造-10㎡变大.md', title: '10㎡ 租房显大改造', ingest_status: 'processing', chunk_count: 0, size_kb: 44, created_at: '2026-08-01T18:22:00Z' },
  { source_id: 'src_05', collection_id: 'col_pub_case', filename: '宠物用品-避坑清单.md', title: '宠物用品避坑清单', ingest_status: 'failed', chunk_count: 0, size_kb: 12, created_at: '2026-07-30T08:05:00Z' },
  // public rule
  { source_id: 'src_06', collection_id: 'col_pub_rule', filename: 'content-safety-baseline.md', title: '内容安全基线', ingest_status: 'done', chunk_count: 14, size_kb: 9, created_at: '2026-07-20T11:00:00Z' },
  { source_id: 'src_07', collection_id: 'col_pub_rule', filename: 'platform-community-rules.md', title: '社区规范要点', ingest_status: 'done', chunk_count: 14, size_kb: 11, created_at: '2026-07-20T11:01:00Z' },
  // public template
  { source_id: 'src_08', collection_id: 'col_pub_template', filename: 'content-brief.md', title: '内容结构模板', ingest_status: 'done', chunk_count: 18, size_kb: 15, created_at: '2026-07-22T09:30:00Z' },
  { source_id: 'src_09', collection_id: 'col_pub_template', filename: 'hook-openers.md', title: '开头钩子模板', ingest_status: 'done', chunk_count: 12, size_kb: 8, created_at: '2026-07-22T09:31:00Z' },
  { source_id: 'src_10', collection_id: 'col_pub_template', filename: 'cta-closers.md', title: '结尾行动号召模板', ingest_status: 'done', chunk_count: 11, size_kb: 7, created_at: '2026-07-22T09:32:00Z' },
  // public material
  { source_id: 'src_11', collection_id: 'col_pub_material', filename: '金句库-情感向.md', title: '情感向金句库', ingest_status: 'done', chunk_count: 40, size_kb: 22, created_at: '2026-07-23T13:10:00Z' },
  { source_id: 'src_12', collection_id: 'col_pub_material', filename: 'emoji组合-高点击.md', title: '高点击 Emoji 组合', ingest_status: 'done', chunk_count: 22, size_kb: 6, created_at: '2026-07-23T13:11:00Z' },
  // The uploader accepts four formats, so the mock carries a binary one of each: they
  // exercise the preview drawer's PDF and download-only branches.
  { source_id: 'src_13', collection_id: 'col_pub_material', filename: '品牌VI规范.pdf', title: '品牌 VI 规范', ingest_status: 'done', chunk_count: 26, size_kb: 1840, created_at: '2026-07-24T09:20:00Z' },
  // private case
  { source_id: 'src_21', collection_id: 'col_priv_case', filename: '我的爆款-早餐机.md', title: '我的爆款：早餐机测评', ingest_status: 'done', chunk_count: 38, size_kb: 33, created_at: '2026-07-29T19:44:00Z' },
  { source_id: 'src_22', collection_id: 'col_priv_case', filename: '我的爆款-工位好物.md', title: '我的爆款：工位好物', ingest_status: 'done', chunk_count: 29, size_kb: 27, created_at: '2026-07-27T20:10:00Z' },
  // private material
  { source_id: 'src_31', collection_id: 'col_priv_material', filename: '我的素材-探店照片.md', title: '探店照片素材', ingest_status: 'done', chunk_count: 51, size_kb: 88, created_at: '2026-07-25T15:00:00Z' },
  { source_id: 'src_32', collection_id: 'col_priv_material', filename: '我的素材-口播稿.md', title: '口播逐字稿', ingest_status: 'done', chunk_count: 33, size_kb: 19, created_at: '2026-07-24T16:30:00Z' },
  { source_id: 'src_33', collection_id: 'col_priv_material', filename: '选题脑暴记录.docx', title: '选题脑暴记录', ingest_status: 'done', chunk_count: 18, size_kb: 96, created_at: '2026-07-26T10:05:00Z' }
]

export function listCollections(kind) {
  let list = collections.slice()
  if (kind) list = list.filter((c) => c.kind === kind)
  return { items: list, total: list.length }
}

export function createCollection(kind, name) {
  const existing = collections.find((c) => c.scope === 'private' && c.kind === kind && c.name === name)
  if (existing) {
    const err = new Error('已存在同名私有库')
    err.code = 'ALREADY_EXISTS'
    throw err
  }
  const col = {
    id: uid('col'),
    kind,
    scope: 'private',
    name,
    source_count: 0,
    document_count: 0,
    chunk_count: 0
  }
  collections.push(col)
  return col
}

export function getCollection(id) {
  return collections.find((c) => c.id === id) || null
}

export function listSources(collectionId, empty) {
  if (empty) return { items: [], total: 0 }
  const list = sources.filter((s) => s.collection_id === collectionId)
  return { items: list, total: list.length }
}

export function deleteSource(id) {
  const i = sources.findIndex((s) => s.source_id === id)
  if (i >= 0) {
    const [removed] = sources.splice(i, 1)
    const col = collections.find((c) => c.id === removed.collection_id)
    if (col) {
      col.source_count = Math.max(0, col.source_count - 1)
      col.document_count = Math.max(0, col.document_count - 1)
      col.chunk_count = Math.max(0, col.chunk_count - removed.chunk_count)
    }
  }
  return { ok: true }
}

export function deleteCollection(id) {
  const i = collections.findIndex((c) => c.id === id)
  if (i >= 0) collections.splice(i, 1)
  for (let j = sources.length - 1; j >= 0; j--) {
    if (sources[j].collection_id === id) sources.splice(j, 1)
  }
  return { ok: true }
}

export function uploadSource(collectionId, filename, sizeKb) {
  const ext = (filename.split('.').pop() || 'md').toLowerCase()
  const title = filename.replace(/\.[^.]+$/, '')
  const src = {
    source_id: uid('src'),
    collection_id: collectionId,
    filename,
    title,
    ingest_status: 'done',
    chunk_count: Math.max(8, Math.round((sizeKb || 20) / 1.2)),
    size_kb: sizeKb || 20,
    created_at: new Date().toISOString()
  }
  sources.push(src)
  const col = collections.find((c) => c.id === collectionId)
  if (col) {
    col.source_count += 1
    col.document_count += 1
    col.chunk_count += src.chunk_count
  }
  return src
}

/* ---- preview ----
   Mirrors SourcePreviewResponse. The mock has no bytes on disk, so a text file gets a
   synthesized original and the binary formats report original_available: false — the
   same "parsed text only" state the real backend returns for seeded public libraries.
   Rendering a real PDF in the drawer therefore needs the live backend. */

const PREVIEW_MODE_BY_SUFFIX = {
  md: 'text',
  markdown: 'text',
  txt: 'text',
  pdf: 'pdf',
  docx: 'download',
  htm: 'download',
  html: 'download'
}
const MEDIA_TYPE_BY_SUFFIX = {
  md: 'text/markdown; charset=utf-8',
  markdown: 'text/markdown; charset=utf-8',
  txt: 'text/plain; charset=utf-8',
  pdf: 'application/pdf',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  htm: 'text/plain; charset=utf-8',
  html: 'text/plain; charset=utf-8'
}

function suffixOf(filename) {
  const parts = filename.split('.')
  return parts.length > 1 ? parts.pop().toLowerCase() : ''
}

function mockRawText(source) {
  return [
    `# ${source.title}`,
    '',
    `> 来源文件：${source.filename}`,
    '',
    '## 核心结论',
    '',
    '这是一段用于演示原文预览的解析文本。真实环境里，这里显示的是 `Document.raw_text`，',
    '也就是解析器（Markdown / TXT / PDF / DOCX）清洗后的正文。',
    '',
    '## 可复用表达',
    '',
    '1. 开头三秒钩子：先说结论，再给理由。',
    '2. 中段用具体数字替代形容词。',
    '3. 结尾给一个可立即执行的动作。',
    '',
    '---',
    '',
    `切片数：${source.chunk_count} · 状态：${source.ingest_status}`
  ].join('\n')
}

export function getSourcePreview(sourceId) {
  const source = sources.find((s) => s.source_id === sourceId)
  if (!source) {
    const err = new Error('文档不存在或已被删除')
    err.code = 'HTTP_404'
    throw err
  }
  const suffix = suffixOf(source.filename)
  const previewMode = PREVIEW_MODE_BY_SUFFIX[suffix] || 'download'
  const rawText = source.ingest_status === 'done' ? mockRawText(source) : null
  const chunks = Array.from({ length: Math.min(source.chunk_count, 12) }, (_, i) => ({
    chunk_id: `${source.source_id}_c${i}`,
    ordinal: i,
    text: `【${source.title}】切片 ${i + 1}：这段文本演示了切片的存储顺序与长度，真实数据来自 chunks 表。`,
    token_count: 96 + i
  }))
  return {
    source_id: source.source_id,
    filename: source.filename,
    suffix: suffix ? `.${suffix}` : '',
    media_type: MEDIA_TYPE_BY_SUFFIX[suffix] || 'application/octet-stream',
    preview_mode: previewMode,
    ingest_status: source.ingest_status,
    dir_path: null,
    created_at: source.created_at,
    error_message: source.ingest_status === 'failed' ? '解析失败：文件内容为空或格式不受支持。' : null,
    original_available: previewMode === 'text',
    size_bytes: previewMode === 'text' ? Math.round(source.size_kb * 1024) : null,
    document_id: source.ingest_status === 'done' ? `${source.source_id}_doc` : null,
    title: source.title,
    raw_text: rawText,
    raw_text_truncated: false,
    chunk_count: source.chunk_count,
    chunks,
    chunks_truncated: source.chunk_count > chunks.length
  }
}

export function getSourceFile(sourceId) {
  const preview = getSourcePreview(sourceId)
  if (!preview.original_available) {
    const err = new Error('该文档没有留存原始文件，仅可查看解析后的文本。')
    err.code = 'HTTP_404'
    throw err
  }
  return new Blob([preview.raw_text ?? ''], { type: preview.media_type })
}

export function searchChunks(collectionId, query) {
  const list = sources.filter((s) => s.collection_id === collectionId && s.ingest_status === 'done')
  const q = (query || '').trim().toLowerCase()
  const matched = q
    ? list.filter((s) => s.title.toLowerCase().includes(q) || s.filename.toLowerCase().includes(q))
    : list.slice(0, 5)
  const chunks = matched.flatMap((s, idx) =>
    Array.from({ length: 3 }, (_, k) => ({
      chunk_id: `${s.source_id}_${k}`,
      source_id: s.source_id,
      title: s.title,
      text: `【${s.title}】片段 ${k + 1}：关于「${q || s.title}」的要点摘录与可复用表达……`,
      score: (0.92 - idx * 0.04 - k * 0.01).toFixed(2)
    }))
  )
  return { items: chunks, total: chunks.length }
}

export const KIND_META = {
  case: { label: KIND_LABEL.case, color: 'var(--wine)' },
  rule: { label: KIND_LABEL.rule, color: 'var(--denim)' },
  template: { label: KIND_LABEL.template, color: 'var(--blush)' },
  material: { label: KIND_LABEL.material, color: 'var(--warning)' }
}
