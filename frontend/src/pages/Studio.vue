<template>
  <div class="page">
    <PageHeader
      eyebrow="创作流 · Studio"
      title="生成工作台"
      desc="左边和 Agent 聊出结构化选题卡，右边由工作流生成大纲与正文，两处人审把关后导出。"
    >
      <template #actions>
        <select v-model="platform" class="yc-select" style="width:auto">
          <option>小红书</option>
        </select>
        <button class="yc-btn yc-btn--wine" :disabled="!topic || running" @click="runGeneration">
          <Icon :name="running ? 'pause' : 'play'" :size="15" /> {{ running ? '生成中…' : '运行生成' }}
        </button>
      </template>
    </PageHeader>

    <div class="st-body">
      <!-- LEFT: chat -->
      <section class="st-chat yc-card yc-card--flush" :class="{ 'st-chat--intro': !messages.length && !chatError }">
        <div class="st-chat__head">
          <span class="yc-label">选题探索</span>
          <span class="st-chat__status"><i class="st-dot"></i> ChatAgent 在线</span>
        </div>

        <div class="st-chat__log" ref="logEl">
          <ErrorState
            v-if="chatError"
            title="对话服务异常"
            :desc="chatError.message"
            :code="chatError.code"
            @retry="chatError = null"
          />
          <template v-else>
            <!-- opening note instead of a full-panel empty placeholder -->
            <div v-if="messages.length === 0" class="st-hello">
              <p class="st-hello__t">先说说你想做什么</p>
              <p class="st-hello__d">哪类内容、给谁看就够了。它会反问、补角度，聊定后一键落成选题卡。不确定的话，从下面挑一个开头。</p>
            </div>

            <div
              v-for="(m, i) in messages"
              :key="i"
              class="st-msg"
              :class="m.role === 'user' ? 'st-msg--user' : 'st-msg--agent'"
            >
              <div class="st-msg__bubble">{{ m.text }}</div>
            </div>

            <div v-if="chatLoading" class="st-msg st-msg--agent">
              <div class="st-msg__bubble st-msg__bubble--wait"><span class="yc-spin yc-spin--sm"></span> 正在想…</div>
            </div>
          </template>
        </div>

        <div v-if="!chatError" class="st-chat__suggest">
          <button v-for="p in suggestions" :key="p" class="st-chip" @click="usePrompt(p)">{{ p }}</button>
        </div>

        <div class="st-chat__input">
          <div class="st-chat__box">
            <textarea v-model="input" class="yc-textarea" placeholder="说说你的选题方向…" @keyup.enter.exact="send" rows="1"></textarea>
            <button class="yc-btn yc-btn--wine st-send" :disabled="!input.trim() || chatLoading" aria-label="发送" @click="send">
              <Icon name="arrow" :size="16" />
            </button>
          </div>
          <button v-if="messages.length" class="yc-btn yc-btn--soft yc-btn--sm st-commit" @click="commitTopic">
            就它了 · 落成选题卡
          </button>
        </div>
      </section>

      <!-- RIGHT: work -->
      <section class="st-work">
        <!-- No topic yet: show what the pipeline actually does, not a blank box -->
        <div v-if="!topic" class="st-card yc-card st-intro">
          <div class="st-card__head yc-row yc-row--between">
            <span class="yc-label">选题卡确定后，这条流水线会跑起来</span>
            <span class="yc-faint yc-mono">{{ nodes.length }} 节点</span>
          </div>

          <div class="st-flow st-flow--idle">
            <div v-for="(n, i) in nodes" :key="n.id" class="st-node">
              <div class="st-node__dot">{{ i + 1 }}</div>
              <span class="st-node__label">{{ n.label }}</span>
              <span v-if="n.kind === 'review'" class="st-node__badge">人审</span>
            </div>
          </div>

          <p class="yc-note">标「人审」的两步会停下来等你，AI 不替你拍板</p>

          <div class="st-intro__cta">
            <button class="yc-btn yc-btn--wine" @click="commitTopic">
              <Icon name="spark" :size="15" /> 直接起草选题卡
            </button>
            <span class="yc-faint">或者先在左边聊两句</span>
          </div>
        </div>

        <template v-else>
          <!-- topic card -->
          <div class="st-card yc-card">
            <div class="st-card__head yc-row yc-row--between">
              <span class="yc-label">选题卡</span>
              <button class="yc-btn--icon yc-btn--sm" @click="topic = null" title="清空"><Icon name="x" :size="15" /></button>
            </div>
            <div class="st-topic">
              <div class="yc-field"><label>主题</label><input v-model="topic.topic" class="yc-input" /></div>
              <div class="yc-field"><label>角度</label><input v-model="topic.angle" class="yc-input" /></div>
              <div class="yc-grid2">
                <div class="yc-field"><label>受众</label><input v-model="topic.audience" class="yc-input" /></div>
                <div class="yc-field"><label>输出配置</label>
                  <select v-model="topic.config" class="yc-select">
                    <option v-for="c in configs" :key="c.id" :value="c.name">{{ c.name }}</option>
                  </select>
                </div>
              </div>
              <div class="yc-field"><label>核心要点（每行一条）</label>
                <textarea v-model="pointsText" class="yc-textarea" style="min-height:72px"></textarea>
              </div>
            </div>
          </div>

          <!-- workflow -->
          <div class="st-card yc-card">
            <div class="st-card__head yc-row yc-row--between">
              <span class="yc-label">生成流水线</span>
              <span class="yc-faint yc-mono">{{ doneCount }} / {{ nodes.length }} 节点</span>
            </div>
            <div class="st-flow">
              <div v-for="(n, i) in nodes" :key="n.id" class="st-node" :class="`is-${n.status}`">
                <div class="st-node__dot">
                  <Icon v-if="n.status === 'done'" name="check" :size="14" />
                  <Icon v-else-if="n.status === 'review'" name="chat" :size="14" />
                  <Icon v-else-if="n.status === 'rejected'" name="x" :size="14" />
                  <Icon v-else-if="n.status === 'active'" name="play" :size="13" />
                  <span v-else>{{ i + 1 }}</span>
                </div>
                <span class="st-node__label">{{ n.label }}</span>
                <span v-if="n.kind === 'review'" class="st-node__badge">人审</span>
              </div>
            </div>

            <!-- review actions -->
            <div v-for="n in reviewNodes" :key="n.id" v-show="n.status === 'review'" class="st-review">
              <span class="st-review__t"><Icon name="pause" :size="15" /> 停在 <strong>{{ n.label }}</strong>，请人工确认</span>
              <div class="yc-row">
                <button class="yc-btn yc-btn--wine yc-btn--sm" @click="approveReview(n.id)"><Icon name="check" :size="14" /> 通过</button>
                <button class="yc-btn yc-btn--danger yc-btn--sm" @click="rejectReview(n.id)"><Icon name="x" :size="14" /> 退回</button>
              </div>
            </div>
          </div>

          <!-- outline + body -->
          <div class="st-card yc-card">
            <div class="st-card__head yc-row yc-row--between">
              <span class="yc-label">大纲与正文</span>
              <span class="yc-faint yc-mono">{{ outline.length }} / {{ body.length }} 字</span>
            </div>
            <div class="st-edit">
              <label class="st-edit__l">大纲</label>
              <textarea v-model="outline" class="yc-textarea" placeholder="运行生成后自动产出，也可手动调整"></textarea>
            </div>
            <div class="st-edit">
              <label class="st-edit__l">正文</label>
              <textarea v-model="body" class="yc-textarea" style="min-height:200px" placeholder="人审通过后产出正文"></textarea>
            </div>
            <div class="st-card__foot yc-row yc-row--between">
              <span class="yc-faint">人审通过后即可导出到内容库</span>
              <button class="yc-btn yc-btn--wine yc-btn--sm" :disabled="!body.trim()" @click="exportDraft"><Icon name="download" :size="14" /> 导出草稿</button>
            </div>
          </div>
        </template>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import Icon from '@/components/Icon.vue'
import PageHeader from '@/components/PageHeader.vue'
import ErrorState from '@/components/ErrorState.vue'
import { useToast } from '@/composables/useToast'
import * as cfgApi from '@/api/config'

const { push } = useToast()
const route = useRoute()
const demo = computed(() => route.query.demo)

const platform = computed({
  get: () => (topic.value ? topic.value.platform : '小红书'),
  set: (v) => { if (topic.value) topic.value.platform = v }
})

/* ---- chat ---- */
const messages = ref([])
const input = ref('')
const chatLoading = ref(false)
const chatError = ref(null)
const logEl = ref(null)
const suggestions = ['通勤穿搭三件套', '10㎡ 租房显大', '早 C 晚 A 护肤', '一周减脂备餐']

const replies = {
  穿搭: '通勤穿搭很适合做「公式化」内容——三件套打底就能一周不重样。受众建议锁定 25–35 上班族，角度用「多睡 10 分钟」比「好看」更有钩子。要不要我把它整理成选题卡？',
  租房: '小户型是永恒流量池。建议角度落在「做减法显大」，而不是「买买买」。可以引用你素材库里的镜面与浅色墙案例。',
  护肤: '护肤类要避开绝对化表述（平台规则禁用）。「早 C 晚 A」用「新手避坑」角度最稳，结尾引导收藏。',
  减脂: '减脂餐的关键是「带娃/上班也能执行」，别做成苦行。用你素材里的备餐模板，强调冷冻分装。'
}

function botReply(text) {
  const key = Object.keys(replies).find((k) => text.includes(k)) || '穿搭'
  return replies[key]
}

async function send() {
  const text = input.value.trim()
  if (!text || chatLoading.value) return
  if (demo.value === 'error') { chatError.value = Object.assign(new Error('演示错误：对话服务不可用（HTTP 503）。'), { code: 'SERVICE_UNAVAILABLE' }); return }
  messages.value.push({ role: 'user', text })
  input.value = ''
  chatLoading.value = true
  scroll()
  await wait(700)
  messages.value.push({ role: 'agent', text: botReply(text) })
  chatLoading.value = false
  scroll()
}
function usePrompt(p) { input.value = p; send() }
function wait(ms) { return new Promise((r) => setTimeout(r, ms)) }
function scroll() { nextTick(() => { if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight }) }

/* ---- topic card ---- */
const topic = ref(null)
const configs = ref([])
const pointsText = computed({
  get: () => (topic.value ? topic.value.points.join('\n') : ''),
  set: (v) => { if (topic.value) topic.value.points = v.split('\n').filter(Boolean) }
})

function commitTopic() {
  const seed = messages.value.filter((m) => m.role === 'user').pop()
  const t = seed ? seed.text : '通勤穿搭三件套'
  topic.value = {
    topic: t,
    angle: '从对话中提炼',
    audience: '25–35 同温层',
    platform: '小红书',
    config: configs.value[0]?.name || '默认 · 小红书图文',
    points: ['开头钩子：反差或利益点', '主体：3 个信息块', '结尾：收藏 / 提问引导']
  }
  resetFlow()
  push('已生成选题卡', 'success')
}

/* ---- workflow ---- */
const nodes = ref([
  { id: 'parse', label: '参数解析', kind: 'step', status: 'pending' },
  { id: 'retrieve', label: '知识检索', kind: 'step', status: 'pending' },
  { id: 'angle', label: '选题角度', kind: 'step', status: 'pending' },
  { id: 'outline', label: '大纲', kind: 'step', status: 'pending' },
  { id: 'review_outline', label: '人审·大纲', kind: 'review', status: 'pending' },
  { id: 'draft', label: '正文', kind: 'step', status: 'pending' },
  { id: 'check', label: '校验', kind: 'step', status: 'pending' },
  { id: 'review_draft', label: '人审·正文', kind: 'review', status: 'pending' }
])
const reviewNodes = computed(() => nodes.value.filter((n) => n.kind === 'review'))
const doneCount = computed(() => nodes.value.filter((n) => n.status === 'done').length)
const running = ref(false)
let stepIndex = 0
let timer = null

const outline = ref('')
const body = ref('')

const SAMPLE_OUTLINE = '一、开头钩子：打工人多睡 10 分钟，靠搭配公式\n二、基础色打底衫（白 / 燕麦 / 雾蓝轮换）\n三、一件显瘦西装，通勤气场拉满\n四、乐福鞋收尾，舒服不随便\n五、结尾：收藏这套，周一不纠结'
const SAMPLE_BODY = '打工人多睡 10 分钟，靠的不是懒，是搭配公式。\n\n① 基础色打底衫——白、燕麦、雾蓝轮换，三件搞定一周底色。\n② 一件显瘦西装——通勤气场拉满，会议室也hold住。\n③ 乐福鞋收尾——舒服又不随便，走路带风。\n\n收藏这套，周一不再选择困难 ✦'

function resetFlow() {
  nodes.value.forEach((n) => (n.status = 'pending'))
  outline.value = ''
  body.value = ''
  running.value = false
  if (timer) clearTimeout(timer)
}

function runGeneration() {
  if (!topic.value) { push('请先生成选题卡', 'error'); return }
  if (demo.value === 'error') { push('演示错误：生成服务不可用', 'error'); return }
  if (running.value) return
  resetFlow()
  running.value = true
  stepIndex = 0
  advance()
}

function advance() {
  const n = nodes.value[stepIndex]
  if (!n) { running.value = false; return }
  n.status = 'active'
  timer = setTimeout(() => {
    if (n.kind === 'step') {
      n.status = 'done'
      if (n.id === 'outline') outline.value = SAMPLE_OUTLINE
      if (n.id === 'draft') body.value = SAMPLE_BODY
      stepIndex++
      advance()
    } else {
      n.status = 'review'
      running.value = false
    }
  }, 720)
}

function approveReview(id) {
  const n = nodes.value.find((x) => x.id === id)
  n.status = 'done'
  stepIndex = nodes.value.findIndex((x) => x.id === id) + 1
  running.value = true
  advance()
}
function rejectReview(id) {
  const n = nodes.value.find((x) => x.id === id)
  n.status = 'rejected'
  running.value = false
  push('已退回，可调整后重新运行', 'info')
}

function exportDraft() {
  push('草稿已导出到内容库', 'success')
}

/* ---- init ---- */
async function loadConfigs() {
  try {
    const res = await cfgApi.listConfigs()
    configs.value = res.items
  } catch (e) { /* non-blocking */ }
}
loadConfigs()
if (demo.value === 'empty') topic.value = null
</script>

<style scoped>
/* ---------------------------------------------------------------------------
   Two-column workspace. Left pane is a fixed-height conversation surface that
   sticks while the right column scrolls; it is sized so the composer is never
   cut off on first paint (the previous calc(100vh - 180px) pushed it below the
   fold and, combined with the shell's blocked scroll chaining, made the page
   feel frozen).
   --------------------------------------------------------------------------- */
.st-body {
  display: grid;
  grid-template-columns: minmax(330px, 400px) 1fr;
  gap: var(--sp-6);
  align-items: start;
}

/* ---- left: conversation ---- */
.st-chat {
  display: flex; flex-direction: column;
  position: sticky; top: var(--stick-top);
  height: clamp(430px, calc(var(--view-h) - 250px), 760px);
  overflow: hidden;
}
/* Before the first message there is nothing to scroll, so the panel shrinks to
   its content instead of holding open a tall empty well. */
.st-chat--intro { height: auto; }
.st-chat__head {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--sp-4) var(--sp-5, 20px);
  border-bottom: 1px solid var(--border-subtle);
  flex: 0 0 auto;
}
.st-chat__status { font-size: var(--fs-caption); color: var(--success-deep); display: inline-flex; align-items: center; gap: 6px; }
.st-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--success); }

.st-chat__log {
  flex: 1 1 auto; min-height: 0; overflow-y: auto;
  padding: var(--sp-4) var(--sp-5, 20px);
  display: flex; flex-direction: column; gap: var(--sp-3);
}

/* opening note: sits in the flow at the top of the log, not a centred
   full-panel placeholder */
.st-hello { padding: var(--sp-2) 0 var(--sp-1); }
.st-hello__t {
  font-family: var(--font-serif); font-weight: 700;
  font-size: 1.18rem; color: var(--ink); margin: 0 0 6px;
}
.st-hello__d { margin: 0 0 var(--sp-4); font-size: var(--fs-small); color: var(--ink-muted); line-height: 1.8; }

.st-msg { display: flex; }
.st-msg--user { justify-content: flex-end; }
.st-msg__bubble {
  max-width: 84%; padding: 10px 14px; border-radius: var(--r-content);
  font-size: var(--fs-small); line-height: 1.7;
}
.st-msg--agent .st-msg__bubble { background: var(--cream-deep); border: 1px solid var(--border-subtle); color: var(--ink); border-top-left-radius: 4px; }
.st-msg--user .st-msg__bubble { background: var(--wine); color: #fff; border-top-right-radius: 4px; }
.st-msg__bubble--wait { display: inline-flex; align-items: center; gap: var(--sp-2); color: var(--ink-faint); }

.st-chat__suggest {
  flex: 0 0 auto;
  display: flex; flex-wrap: wrap; gap: 6px;
  padding: 0 var(--sp-5, 20px) var(--sp-3);
}
.st-chip {
  font-size: var(--fs-caption); padding: 5px 11px; border-radius: var(--r-pill);
  border: 1px solid var(--border-default); background: var(--paper); color: var(--denim-deep);
  transition: background var(--dur-fast) var(--ease-out), border-color var(--dur-fast) var(--ease-out);
}
.st-chip:hover { background: var(--denim-50); border-color: var(--denim); }

.st-chat__input {
  flex: 0 0 auto;
  display: flex; flex-direction: column; gap: var(--sp-2);
  padding: var(--sp-3) var(--sp-5, 20px) var(--sp-4);
  border-top: 1px solid var(--border-subtle);
  background: var(--paper);
}
.st-chat__box { display: flex; gap: var(--sp-2); align-items: flex-end; }
.st-chat__box .yc-textarea { flex: 1; min-height: 42px; max-height: 120px; }
.st-send { flex: 0 0 auto; height: 42px; width: 42px; padding: 0; }
.st-commit { align-self: flex-start; }

/* ---- right: work column ---- */
.st-work { display: flex; flex-direction: column; gap: var(--sp-6); }
.st-card { padding: var(--sp-6); }
.st-card__head { margin-bottom: var(--sp-4); gap: var(--sp-3); }
.st-card__foot { margin-top: var(--sp-5, 20px); gap: var(--sp-3); }
.st-topic { display: flex; flex-direction: column; gap: var(--sp-3); }

/* pipeline preview standing in for the old blank placeholder card */
.st-intro__cta {
  display: flex; align-items: center; gap: var(--sp-3); flex-wrap: wrap;
  margin-top: var(--sp-5, 20px); padding-top: var(--sp-5, 20px);
  border-top: 1px solid var(--border-subtle);
}
.st-intro__cta .yc-faint { font-size: var(--fs-small); }
.st-intro .yc-note { margin-top: var(--sp-4); }

/* ---- flow ---- */
.st-flow {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--sp-2);
}
.st-node {
  display: flex; flex-direction: column; align-items: center; gap: 7px;
  min-width: 0;
  padding: var(--sp-3) var(--sp-2);
  border-radius: var(--r-content); border: 1px solid var(--border-subtle);
  background: var(--cream-deep); position: relative;
  transition: background var(--dur-base) var(--ease-out),
              border-color var(--dur-base) var(--ease-out),
              box-shadow var(--dur-base) var(--ease-out);
}
.st-flow--idle .st-node { background: transparent; }
.st-node__dot {
  width: 28px; height: 28px; border-radius: 50%;
  display: grid; place-items: center;
  background: var(--paper); border: 1px solid var(--border-default); color: var(--ink-faint);
  font-family: var(--font-code); font-size: var(--fs-caption); font-weight: 700;
}
.st-node__label { font-size: var(--fs-caption); color: var(--ink-muted); text-align: center; line-height: 1.35; }
.st-node__badge {
  position: absolute; top: -7px; right: 4px;
  font-size: 10px; background: var(--warning); color: #fff;
  padding: 1px 6px; border-radius: var(--r-pill);
}
.st-node.is-done { background: var(--success-soft); border-color: var(--success-soft); }
.st-node.is-done .st-node__dot { background: var(--success); color: #fff; border-color: var(--success); }
.st-node.is-active { background: var(--denim-50); border-color: var(--denim); box-shadow: 0 0 0 3px rgba(59,110,165,.18); }
.st-node.is-active .st-node__dot { background: var(--denim); color: #fff; border-color: var(--denim); }
.st-node.is-review { background: var(--warning-soft); border-color: var(--warning); }
.st-node.is-review .st-node__dot { background: var(--warning); color: #fff; border-color: var(--warning); }
.st-node.is-rejected { background: var(--error-soft); border-color: var(--error); }
.st-node.is-rejected .st-node__dot { background: var(--error); color: #fff; border-color: var(--error); }

.st-review {
  display: flex; align-items: center; justify-content: space-between;
  gap: var(--sp-3); margin-top: var(--sp-4);
  padding: var(--sp-3) var(--sp-4);
  background: var(--warning-soft); border-radius: var(--r-content);
  font-size: var(--fs-small); color: var(--warning-deep); flex-wrap: wrap;
}
.st-review__t { display: inline-flex; align-items: center; gap: 6px; }
.st-review strong { color: var(--ink); }

.st-edit { display: flex; flex-direction: column; gap: 6px; margin-top: var(--sp-4); }
.st-edit__l { font-size: var(--fs-caption); font-weight: 700; color: var(--ink-muted); letter-spacing: .02em; }

@media (max-width: 1200px) {
  .st-flow { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 980px) {
  .st-body { grid-template-columns: 1fr; }
  .st-flow { grid-template-columns: repeat(4, minmax(0, 1fr)); }
  .st-chat--intro { height: auto; }
  .st-chat { height: 66vh; position: static; }
}
</style>
