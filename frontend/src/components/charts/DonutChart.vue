<template>
  <div class="dc yc-row" :class="{ 'dc--col': stack }">
    <svg class="dc__svg" :viewBox="`0 0 ${size} ${size}`" role="img" :aria-label="ariaLabel">
      <circle :cx="c" :cy="c" :r="r" fill="none" stroke="var(--cream-deep)" :stroke-width="thickness" />
      <circle
        v-for="(s, i) in arcs"
        :key="i"
        :cx="c"
        :cy="c"
        :r="r"
        fill="none"
        :stroke="s.color"
        :stroke-width="thickness"
        :stroke-dasharray="`${s.len} ${C - s.len}`"
        :stroke-dashoffset="-s.offset"
        :transform="`rotate(-90 ${c} ${c})`"
        stroke-linecap="butt"
      />
      <text :x="c" :y="c - 4" class="dc__center" text-anchor="middle">{{ centerValue }}</text>
      <text :x="c" :y="c + 16" class="dc__sub" text-anchor="middle">{{ centerLabel }}</text>
    </svg>

    <ul class="dc__legend">
      <li v-for="s in segments" :key="s.label">
        <i :style="{ background: s.color }"></i>
        <span class="dc__leg-label">{{ s.label }}</span>
        <span class="dc__leg-val yc-mono">{{ s.value }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  segments: { type: Array, required: true }, // [{ label, value, color }]
  size: { type: Number, default: 184 },
  thickness: { type: Number, default: 22 },
  centerValue: { type: [String, Number], default: '' },
  centerLabel: { type: String, default: '' },
  stack: { type: Boolean, default: false },
  ariaLabel: { type: String, default: '环形图' }
})

const c = computed(() => props.size / 2)
const r = computed(() => (props.size - props.thickness) / 2)
const C = computed(() => 2 * Math.PI * r.value)
const total = computed(() => props.segments.reduce((a, s) => a + (s.value || 0), 0) || 1)

const arcs = computed(() => {
  let acc = 0
  return props.segments.map((s) => {
    const frac = (s.value || 0) / total.value
    const len = frac * C.value
    const offset = acc * C.value
    acc += frac
    return { ...s, len, offset }
  })
})
</script>

<style scoped>
.dc { gap: var(--sp-6); align-items: center; flex-wrap: wrap; }
.dc--col { flex-direction: column; align-items: stretch; }
.dc__svg { width: 184px; height: 184px; flex: 0 0 auto; }
.dc__center { fill: var(--ink); font-family: var(--font-accent); font-style: italic; font-size: 1.5rem; font-weight: 600; }
.dc__sub { fill: var(--ink-faint); font-size: 11px; }
.dc__legend { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; flex: 1; min-width: 160px; }
.dc__legend li { display: flex; align-items: center; gap: var(--sp-2); font-size: var(--fs-small); }
.dc__legend i { width: 11px; height: 11px; border-radius: 3px; flex: 0 0 auto; }
.dc__leg-label { color: var(--ink-muted); }
.dc__leg-val { margin-left: auto; color: var(--ink); font-weight: 700; }
</style>
