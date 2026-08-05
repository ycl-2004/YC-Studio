<template>
  <div class="pr yc-col" :style="{ width: size + 'px' }">
    <svg class="pr__svg" :viewBox="`0 0 ${size} ${size}`" role="img" :aria-label="`${label} ${value}%`">
      <circle :cx="c" :cy="c" :r="r" fill="none" stroke="var(--cream-deep)" :stroke-width="thickness" />
      <circle
        :cx="c"
        :cy="c"
        :r="r"
        fill="none"
        :stroke="color"
        :stroke-width="thickness"
        :stroke-dasharray="`${len} ${C}`"
        :stroke-dashoffset="0"
        :transform="`rotate(-90 ${c} ${c})`"
        stroke-linecap="round"
        class="pr__bar"
      />
      <text :x="c" :y="c - 2" class="pr__val" text-anchor="middle">{{ value }}<tspan class="pr__pct">%</tspan></text>
      <text :x="c" :y="c + 18" class="pr__lab" text-anchor="middle">{{ label }}</text>
    </svg>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  value: { type: Number, default: 0 },
  label: { type: String, default: '' },
  color: { type: String, default: 'var(--wine)' },
  size: { type: Number, default: 124 },
  thickness: { type: Number, default: 12 }
})

const c = computed(() => props.size / 2)
const r = computed(() => (props.size - props.thickness) / 2)
const C = computed(() => 2 * Math.PI * r.value)
const len = computed(() => (Math.min(100, Math.max(0, props.value)) / 100) * C.value)
</script>

<style scoped>
.pr { align-items: center; }
.pr__svg { width: 100%; height: auto; }
.pr__bar { transition: stroke-dasharray var(--dur-slow) var(--ease-out); }
.pr__val { fill: var(--ink); font-family: var(--font-accent); font-style: italic; font-size: 1.7rem; font-weight: 600; }
.pr__pct { font-size: .9rem; fill: var(--ink-muted); }
.pr__lab { fill: var(--ink-faint); font-size: 11px; }
@media (prefers-reduced-motion: reduce){ .pr__bar { transition: none; } }
</style>
