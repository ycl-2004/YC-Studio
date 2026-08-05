/* In-browser mock for Content Library (drafts / exports / snapshots). */

let _seq = 200
const uid = (p = 'd') => `${p}_${(++_seq).toString(36)}${Date.now().toString(36).slice(-4)}`

const drafts = [
  { id: 'dft_01', title: '通勤穿搭三件套｜打工人一周不重样', topic: '通勤穿搭', angle: '三件套公式', status: 'approved', config_name: '默认 · 小红书图文', words: 742, updated_at: '2026-07-31T11:20:00Z' },
  { id: 'dft_02', title: '早餐机测评｜值不值得买', topic: '早餐机', angle: '值不值得买', status: 'in_review', config_name: '测评类结构', words: 1041, updated_at: '2026-08-01T09:05:00Z' },
  { id: 'dft_03', title: '带娃也能吃好｜一周减脂备餐', topic: '减脂餐', angle: '带娃友好', status: 'draft', config_name: '默认 · 小红书图文', words: 688, updated_at: '2026-07-30T20:48:00Z' },
  { id: 'dft_04', title: '10㎡ 租房显大改造', topic: '租房改造', angle: '小户型显大', status: 'approved', config_name: '默认 · 小红书图文', words: 905, updated_at: '2026-07-29T15:30:00Z' },
  { id: 'dft_05', title: '工位好物｜提升幸福感的 8 件', topic: '工位好物', angle: '幸福感清单', status: 'rejected', config_name: '默认 · 小红书图文', words: 560, updated_at: '2026-07-27T18:12:00Z' },
  { id: 'dft_06', title: '护肤早 C 晚 A｜新手避坑', topic: '护肤', angle: '新手避坑', status: 'draft', config_name: '默认 · 小红书图文', words: 712, updated_at: '2026-08-01T21:03:00Z' }
]

const exports = [
  { id: 'exp_01', draft_id: 'dft_01', title: '通勤穿搭三件套｜打工人一周不重样', platform: '小红书', format: 'markdown', exported_at: '2026-07-31T12:00:00Z', views: 12840, likes: 1842, collects: 2361, backfilled: true },
  { id: 'exp_02', draft_id: 'dft_04', title: '10㎡ 租房显大改造', platform: '小红书', format: 'markdown', exported_at: '2026-07-29T16:10:00Z', views: 23190, likes: 3120, collects: 4912, backfilled: true },
  { id: 'exp_03', draft_id: 'dft_05', title: '工位好物｜提升幸福感的 8 件', platform: '小红书', format: 'markdown', exported_at: '2026-07-27T18:40:00Z', views: 0, likes: 0, collects: 0, backfilled: false },
  { id: 'exp_04', draft_id: 'dft_06', title: '护肤早 C 晚 A｜新手避坑', platform: '小红书', format: 'markdown', exported_at: '2026-08-01T21:30:00Z', views: 0, likes: 0, collects: 0, backfilled: false }
]

const snapshots = [
  { id: 'snap_01', export_id: 'exp_01', title: '通勤穿搭三件套｜打工人一周不重样', created_at: '2026-07-31T12:00:00Z',
    content: '# 通勤穿搭三件套｜打工人一周不重样\n\n打工人多睡 10 分钟，靠的不是懒，是搭配公式。\n\n① 基础色打底衫——白/燕麦/雾蓝轮换\n② 一件显瘦西装——通勤气场拉满\n③ 乐福鞋收尾——舒服又不随便\n\n收藏这套，周一不再选择困难 ✦' },
  { id: 'snap_02', export_id: 'exp_02', title: '10㎡ 租房显大改造', created_at: '2026-07-29T16:10:00Z',
    content: '# 10㎡ 租房显大改造\n\n小户型不是将就，是做减法。\n\n· 浅色墙面 + 一面落地镜延伸视线\n· 床底收纳，地面留白\n· 一盏暖光，氛围感立刻上来\n\n租房也要认真生活 ✦' }
]

export function listDrafts() {
  return { items: drafts.slice(), total: drafts.length }
}

export function listExports() {
  return { items: exports.slice(), total: exports.length }
}

export function listSnapshots(exportId) {
  const list = snapshots.filter((s) => !exportId || s.export_id === exportId)
  return { items: list, total: list.length }
}

export function getSnapshot(id) {
  return snapshots.find((s) => s.id === id) || null
}

export function deleteDraft(id) {
  const i = drafts.findIndex((d) => d.id === id)
  if (i >= 0) drafts.splice(i, 1)
  return { ok: true }
}

export function backfillMetrics(id, metrics) {
  const e = exports.find((x) => x.id === id)
  if (!e) {
    const err = new Error('导出记录不存在')
    err.code = 'NOT_FOUND'
    throw err
  }
  e.views = metrics.views ?? e.views
  e.likes = metrics.likes ?? e.likes
  e.collects = metrics.collects ?? e.collects
  e.backfilled = true
  return e
}

export const STATUS_META = {
  draft: { label: '草稿', tone: 'neutral' },
  in_review: { label: '人审中', tone: 'warning' },
  approved: { label: '已通过', tone: 'success' },
  rejected: { label: '已退回', tone: 'error' }
}
