<template>
  <div class="bc">
    <svg class="bc__svg" :viewBox="`0 0 ${W} ${H}`" role="img" :aria-label="ariaLabel">
      <g>
        <line v-for="(g, i) in grid" :key="'g' + i" :x1="padL" :x2="W - padR" :y1="g.y" :y2="g.y" class="bc__grid" />
        <text v-for="(g, i) in grid" :key="'yl' + i" :x="padL - 8" :y="g.y + 4" class="bc__ylab">{{ g.label }}</text>
      </g>

      <g v-for="(b, i) in bars" :key="i">
        <rect :x="b.x" :y="b.y" :width="b.w" :height="b.h" :rx="6" :fill="b.color" />
        <text :x="b.x + b.w / 2" :y="b.y - 7" class="bc__v">{{ b.value }}</text>
        <text :x="b.x + b.w / 2" :y="H - 10" class="bc__c">{{ categories[i] }}</text>
      </g>
    </svg>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  categories: { type: Array, required: true },
  values: { type: Array, required: true },
  colors: { type: Array, default: () => [] },
  color: { type: String, default: 'var(--wine)' },
  height: { type: Number, default: 220 },
  ariaLabel: { type: String, default: '柱状图' }
})

const W = 720
const H = props.height
const padL = 40
const padR = 16
const padT = 18
const padB = 34
const plotW = W - padL - padR
const plotH = H - padT - padB

function niceMax(v) {
  if (v <= 0) return 1
  const pow = Math.pow(10, Math.floor(Math.log10(v)))
  const n = v / pow
  const m = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10
  return m * pow
}

const maxV = computed(() => niceMax(Math.max(0, ...(props.values || [])) * 1.1) || 1)

const grid = computed(() => {
  const ticks = 4
  return Array.from({ length: ticks + 1 }, (_, i) => {
    const val = (maxV.value / ticks) * i
    const y = padT + plotH - (val / maxV.value) * plotH
    return { y, label: val >= 1000 ? (val / 1000).toFixed(val % 1000 ? 1 : 0) + 'k' : Math.round(val) }
  })
})

const bars = computed(() => {
  const n = props.categories.length || 1
  const slot = plotW / n
  const bw = Math.min(64, slot * 0.56)
  return (props.values || []).map((v, i) => {
    const h = (v / maxV.value) * plotH
    const x = padL + i * slot + (slot - bw) / 2
    const y = padT + plotH - h
    return {
      x,
      y,
      w: bw,
      h: Math.max(2, h),
      value: v,
      color: props.colors[i] || props.color
    }
  })
})
</script>

<style scoped>
.bc { width: 100%; }
.bc__svg { width: 100%; height: auto; display: block; }
.bc__grid { stroke: var(--border-subtle); stroke-width: 1; }
.bc__ylab { fill: var(--ink-faint); font-size: 11px; text-anchor: end; font-family: var(--font-code); }
.bc__v { fill: var(--ink); font-size: 12px; text-anchor: middle; font-weight: 700; font-family: var(--font-code); }
.bc__c { fill: var(--ink-muted); font-size: 12px; text-anchor: middle; }
</style>
