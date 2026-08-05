/* In-browser mock for the Retrospective Dashboard (复盘看板). */

let extra = { views: 0, likes: 0, collects: 0, count: 0 }

const base = {
  kpis: [
    { key: 'total', label: '已发布内容', value: 24, unit: '篇', delta: 12, spark: [12, 13, 14, 15, 17, 18, 20, 21, 22, 23, 23, 24], color: 'var(--wine)' },
    { key: 'eng', label: '平均互动率', value: 8.7, unit: '%', delta: 1.4, spark: [6.1, 6.4, 6.9, 7.2, 7.0, 7.6, 8.0, 8.1, 8.3, 8.5, 8.6, 8.7], color: 'var(--denim)' },
    { key: 'recycled', label: '回流案例', value: 6, unit: '条', delta: 2, spark: [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6], color: 'var(--blush)' },
    { key: 'weekly', label: '本周发布', value: 4, unit: '篇', delta: 1, spark: [1, 2, 1, 3, 2, 3, 4, 3, 4, 2, 3, 4], color: 'var(--warning)' }
  ],
  trend: {
    weeks: ['W1', 'W2', 'W3', 'W4', 'W5', 'W6', 'W7', 'W8'],
    series: [
      { name: '浏览', color: 'var(--wine)', values: [3200, 4100, 5200, 6100, 7400, 8800, 10200, 12840] },
      { name: '点赞', color: 'var(--denim)', values: [420, 560, 720, 880, 1020, 1280, 1510, 1842] },
      { name: '收藏', color: 'var(--blush)', values: [610, 820, 1040, 1260, 1500, 1900, 2120, 2361] }
    ]
  },
  byAngle: [
    { angle: '穿搭', value: 8 },
    { angle: '家居', value: 6 },
    { angle: '护肤', value: 5 },
    { angle: '美食', value: 3 },
    { angle: '数码', value: 2 }
  ],
  statusDist: [
    { label: '已发布', value: 18, color: 'var(--wine)' },
    { label: '人审中', value: 3, color: 'var(--warning)' },
    { label: '草稿', value: 6, color: 'var(--denim-300)' },
    { label: '已退回', value: 1, color: 'var(--error)' },
    { label: '已回流', value: 6, color: 'var(--success)' }
  ],
  rates: [
    { key: 'review', label: '人审通过率', value: 82, color: 'var(--denim)' },
    { key: 'recycle', label: '回流阈值达标率', value: 75, color: 'var(--wine)' }
  ],
  recycled: [
    { id: 'rc_01', title: '通勤穿搭三件套｜打工人一周不重样', views: 12840, likes: 1842, collects: 2361, score: 92, recycled_at: '2026-08-01T10:00:00Z', status: 'done' },
    { id: 'rc_02', title: '10㎡ 租房显大改造', views: 23190, likes: 3120, collects: 4912, score: 95, recycled_at: '2026-07-31T16:00:00Z', status: 'done' },
    { id: 'rc_03', title: '早餐机测评｜值不值得买', views: 9800, likes: 1402, collects: 1880, score: 88, recycled_at: '2026-08-02T09:00:00Z', status: 'done' },
    { id: 'rc_04', title: '早 C 晚 A 护肤｜新手避坑', views: 7600, likes: 990, collects: 1320, score: 85, recycled_at: '2026-08-03T08:00:00Z', status: 'pending' },
    { id: 'rc_05', title: '带娃也能吃好｜一周减脂备餐', views: 6200, likes: 880, collects: 1100, score: 83, recycled_at: '2026-08-03T12:00:00Z', status: 'pending' },
    { id: 'rc_06', title: '工位好物｜提升幸福感 8 件', views: 5400, likes: 720, collects: 980, score: 80, recycled_at: '2026-08-04T11:00:00Z', status: 'pending' }
  ],
  top: [
    { title: '10㎡ 租房显大改造', views: 23190, engagement: 14.2 },
    { title: '通勤穿搭三件套', views: 12840, engagement: 9.8 },
    { title: '早餐机测评', views: 9800, engagement: 8.1 },
    { title: '早 C 晚 A 护肤', views: 7600, engagement: 7.4 },
    { title: '带娃也能吃好', views: 6200, engagement: 6.9 }
  ]
}

export function getDashboard() {
  const d = JSON.parse(JSON.stringify(base))
  // fold any backfilled metrics into the totals so the board feels live
  d.kpis[0].value += extra.count
  d.kpis[0].spark = [...d.kpis[0].spark.slice(0, -1), d.kpis[0].value]
  return d
}

export function backfillExport(id, metrics) {
  extra.views += metrics.views || 0
  extra.likes += metrics.likes || 0
  extra.collects += metrics.collects || 0
  extra.count += 1
  return { ok: true, id }
}
