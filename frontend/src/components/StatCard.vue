<template>
  <div class="stat yc-card yc-lift">
    <div class="stat__top">
      <span class="stat__label">{{ label }}</span>
      <span class="stat__icon" :style="{ color }"><Icon :name="icon" :size="18" /></span>
    </div>

    <div class="stat__value">
      <span class="yc-num">{{ display }}</span>
      <span v-if="unit" class="stat__unit">{{ unit }}</span>
    </div>

    <div class="stat__foot">
      <span class="stat__delta" :class="deltaNum >= 0 ? 'is-up' : 'is-down'">
        <Icon name="arrow" :size="13" :style="deltaNum >= 0 ? 'transform:rotate(-45deg)' : 'transform:rotate(45deg)'" />
        {{ deltaNum >= 0 ? '+' : '' }}{{ deltaNum }}{{ deltaUnit }}
      </span>
      <svg class="stat__spark" viewBox="0 0 100 36" preserveAspectRatio="none" aria-hidden="true">
        <polyline
          :points="points"
          fill="none"
          :stroke="color"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import Icon from './Icon.vue'

const props = defineProps({
  label: { type: String, required: true },
  value: { type: [Number, String], required: true },
  unit: { type: String, default: '' },
  delta: { type: [Number, String], default: 0 },
  deltaUnit: { type: String, default: '%' },
  color: { type: String, default: 'var(--wine)' },
  icon: { type: String, default: 'spark' },
  spark: { type: Array, default: () => [] }
})

const display = computed(() => props.value)
const deltaNum = computed(() => {
  const n = Number(props.delta)
  return Number.isFinite(n) ? n : 0
})
const points = computed(() => {
  const s = props.spark
  if (!s || s.length < 2) return ''
  const min = Math.min(...s)
  const max = Math.max(...s)
  const span = max - min || 1
  const w = 100
  const h = 36
  return s
    .map((v, i) => {
      const x = (i / (s.length - 1)) * w
      const y = h - ((v - min) / span) * (h - 4) - 2
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
})
</script>

<style scoped>
.stat { display: flex; flex-direction: column; gap: var(--sp-3); }
.stat__top { display: flex; align-items: center; justify-content: space-between; }
.stat__label { font-size: var(--fs-caption); font-weight: 700; letter-spacing: .04em; text-transform: uppercase; color: var(--ink-faint); }
.stat__icon { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 10px; background: var(--cream-deep); }
.stat__value { display: flex; align-items: baseline; gap: 4px; }
.stat__value .yc-num { font-size: clamp(1.8rem, 3vw, 2.4rem); color: var(--ink); font-weight: 600; }
.stat__unit { font-size: var(--fs-small); color: var(--ink-muted); }
.stat__foot { display: flex; align-items: center; justify-content: space-between; gap: var(--sp-3); }
.stat__delta { display: inline-flex; align-items: center; gap: 3px; font-size: var(--fs-caption); font-weight: 700; font-family: var(--font-code); }
.stat__delta.is-up { color: var(--success-deep); }
.stat__delta.is-down { color: var(--error-deep); }
.stat__spark { width: 96px; height: 34px; flex: 0 0 auto; opacity: .9; }
</style>
