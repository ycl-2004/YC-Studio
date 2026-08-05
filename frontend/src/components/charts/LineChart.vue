<template>
  <div class="lc">
    <svg class="lc__svg" :viewBox="`0 0 ${W} ${H}`" role="img" :aria-label="ariaLabel">
      <!-- gridlines + y labels -->
      <g>
        <line v-for="(g, i) in grid" :key="'g' + i" :x1="padL" :x2="W - padR" :y1="g.y" :y2="g.y" class="lc__grid" />
        <text v-for="(g, i) in grid" :key="'yl' + i" :x="padL - 8" :y="g.y + 4" class="lc__ylab">{{ g.label }}</text>
      </g>

      <!-- x labels -->
      <text v-for="(x, i) in xPoints" :key="'xl' + i" :x="x" :y="H - 8" class="lc__xlab">{{ xLabels[i] }}</text>

      <!-- series -->
      <g v-for="s in series" :key="s.name">
        <polyline :points="s._points" fill="none" :stroke="s.color" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />
        <circle v-for="(p, i) in s._pts" :key="i" :cx="p.x" :cy="p.y" r="3" :fill="s.color" />
      </g>
    </svg>

    <div class="lc__legend">
      <span v-for="s in series" :key="s.name" class="lc__leg">
        <i :style="{ background: s.color }"></i>{{ s.name }}
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  series: { type: Array, required: true }, // [{ name, color, values:[] }]
  xLabels: { type: Array, default: () => [] },
  height: { type: Number, default: 260 },
  ariaLabel: { type: String, default: '折线图' }
})

const W = 720
const H = computed(() => props.height).value
const padL = 46
const padR = 16
const padT = 16
const padB = 30
const plotW = W - padL - padR
const plotH = H - padT - padB

function niceMax(v) {
  if (v <= 0) return 1
  const pow = Math.pow(10, Math.floor(Math.log10(v)))
  const n = v / pow
  let m
  if (n <= 1) m = 1
  else if (n <= 2) m = 2
  else if (n <= 5) m = 5
  else m = 10
  return m * pow
}

const maxV = computed(() => {
  const all = props.series.flatMap((s) => s.values || [])
  return niceMax(Math.max(0, ...all) * 1.1) || 1
})

const grid = computed(() => {
  const ticks = 4
  return Array.from({ length: ticks + 1 }, (_, i) => {
    const val = (maxV.value / ticks) * i
    const y = padT + plotH - (val / maxV.value) * plotH
    return { y, label: formatNum(val) }
  })
})

const xPoints = computed(() =>
  props.xLabels.map((_, i) => {
    const n = props.xLabels.length
    return padL + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW)
  })
)

function formatNum(n) {
  if (n >= 1000) return (n / 1000).toFixed(n % 1000 === 0 ? 0 : 1) + 'k'
  return Math.round(n).toString()
}

const prepared = computed(() =>
  props.series.map((s) => {
    const pts = (s.values || []).map((v, i) => {
      const n = (s.values || []).length
      const x = padL + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW)
      const y = padT + plotH - (v / maxV.value) * plotH
      return { x, y }
    })
    return { ...s, _pts: pts, _points: pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ') }
  })
)
// expose prepared as `series` in template via alias
const series = prepared
</script>

<style scoped>
.lc { width: 100%; }
.lc__svg { width: 100%; height: auto; display: block; }
.lc__grid { stroke: var(--border-subtle); stroke-width: 1; }
.lc__ylab { fill: var(--ink-faint); font-size: 11px; text-anchor: end; font-family: var(--font-code); }
.lc__xlab { fill: var(--ink-faint); font-size: 11px; text-anchor: middle; }
.lc__legend { display: flex; flex-wrap: wrap; gap: var(--sp-4); margin-top: var(--sp-3); }
.lc__leg { display: inline-flex; align-items: center; gap: 6px; font-size: var(--fs-caption); color: var(--ink-muted); }
.lc__leg i { width: 12px; height: 4px; border-radius: 2px; display: inline-block; }
</style>
