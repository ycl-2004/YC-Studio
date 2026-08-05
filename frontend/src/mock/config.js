/* In-browser mock for Output Config (content generation profiles). */

let _seq = 50
const uid = (p = 'cfg') => `${p}_${(++_seq).toString(36)}${Date.now().toString(36).slice(-4)}`

const profiles = [
  {
    id: 'cfg_default',
    name: '默认 · 小红书图文',
    platform: '小红书',
    format: '图文',
    description: '通用图文笔记结构，适用于大多数生活/好物类选题。',
    updated_at: '2026-07-30T10:20:00Z',
    persona: '一个审美在线、生活有节奏的同温层朋友，不说教、不爹味。',
    tone: '亲切、专业、带一点俏皮',
    banned_words: ['绝对', '最便宜', '加微信', '私聊'],
    word_range: [600, 900],
    emoji_policy: 'moderate',
    hashtag_count: 6,
    structure: [
      { key: 'title', label: '标题', required: true, hint: '12–18 字，含数字或反差' },
      { key: 'hook', label: '开头钩子', required: true, hint: '前 2 行必须留住人' },
      { key: 'body', label: '正文分段', required: true, hint: '3–5 个信息块，每块一个要点' },
      { key: 'cta', label: '结尾行动号召', required: true, hint: '提问或收藏引导' }
    ],
    few_shot: [
      {
        input: '选题：通勤穿搭，受众 25–35 上班族，角度「三件套搞定一周」',
        output:
          '标题：打工人通勤穿搭｜这三件套我穿了一整月\n钩子：每天早上多睡 10 分钟，靠的不是懒，是搭配公式。\n正文：① 基础色打底衫 ② 一件显瘦西装 ③ 乐福鞋收尾……'
      },
      {
        input: '选题：减脂餐，受众新手妈妈，角度「带娃也能吃好」',
        output:
          '标题：带娃没空做饭？这 5 餐我囤了一周\n钩子：不是代餐，是真的不费妈。\n正文：提前备菜 + 一锅出 + 冷冻分装……'
      }
    ]
  },
  {
    id: 'cfg_review',
    name: '测评类结构',
    platform: '小红书',
    format: '图文',
    description: '开箱/参数/实测/结论四段式，适合数码与好物测评。',
    updated_at: '2026-07-28T16:05:00Z',
    persona: '认真做功课、帮读者避坑的测评控。',
    tone: '理性、克制、用数据说话',
    banned_words: ['智商税', '踩雷', '绝绝子'],
    word_range: [800, 1200],
    emoji_policy: 'light',
    hashtag_count: 8,
    structure: [
      { key: 'unbox', label: '开箱第一印象', required: true, hint: '外观/做工/配件' },
      { key: 'spec', label: '关键参数', required: true, hint: '只列读者关心的 3–5 项' },
      { key: 'test', label: '实测结论', required: true, hint: '好用/不够好用，分开说' },
      { key: 'verdict', label: '购买建议', required: true, hint: '适合谁 / 不适合谁' }
    ],
    few_shot: [
      {
        input: '选题：早餐机测评，角度「值不值得买」',
        output:
          '开箱：磨砂白机身，占地比 A4 小。\n参数：功率 600W，双面加热。\n实测：煎蛋 90 秒、华夫饼 3 分钟，不粘表现 OK。\n建议：独居/小厨房友好，大家庭略小。'
      }
    ]
  },
  {
    id: 'cfg_video',
    name: '口播视频脚本',
    platform: '小红书',
    format: '视频脚本',
    description: '黄金 3 秒 + 信息密度 + 互动提问，适配短视频口播。',
    updated_at: '2026-07-25T09:40:00Z',
    persona: '镜头前松弛、像跟朋友聊天的主讲人。',
    tone: '口语化、节奏快、有梗',
    banned_words: ['家人们谁懂啊', '无语子'],
    word_range: [300, 500],
    emoji_policy: 'none',
    hashtag_count: 5,
    structure: [
      { key: 'hook3s', label: '黄金 3 秒', required: true, hint: '反差/悬念/利益点' },
      { key: 'payload', label: '信息主体', required: true, hint: '每 15 秒一个爆点' },
      { key: 'ask', label: '互动提问', required: true, hint: '结尾抛问题引导评论' }
    ],
    few_shot: []
  }
]

export function listConfigs() {
  return { items: profiles.slice(), total: profiles.length }
}

export function getConfig(id) {
  return profiles.find((p) => p.id === id) || null
}

export function saveConfig(cfg) {
  const i = profiles.findIndex((p) => p.id === cfg.id)
  const next = { ...cfg, updated_at: new Date().toISOString() }
  if (i >= 0) profiles[i] = next
  else profiles.push(next)
  return next
}

export function createConfig(name) {
  const cfg = {
    id: uid(),
    name: name || '未命名配置',
    platform: '小红书',
    format: '图文',
    description: '新建的输出配置，请编辑结构与风格约束。',
    updated_at: new Date().toISOString(),
    persona: '',
    tone: '',
    banned_words: [],
    word_range: [600, 900],
    emoji_policy: 'moderate',
    hashtag_count: 6,
    structure: [
      { key: 'title', label: '标题', required: true, hint: '' },
      { key: 'body', label: '正文', required: true, hint: '' }
    ],
    few_shot: []
  }
  profiles.push(cfg)
  return cfg
}

export function deleteConfig(id) {
  const i = profiles.findIndex((p) => p.id === id)
  if (i >= 0) profiles.splice(i, 1)
  return { ok: true }
}

export const EMOJI_POLICY = {
  none: { label: '不使用', desc: '纯文字，克制专业' },
  light: { label: '少量', desc: '每段至多 1 个' },
  moderate: { label: '适度', desc: '标题 + 分区点缀' },
  rich: { label: '丰富', desc: '高频表情增强活力' }
}
