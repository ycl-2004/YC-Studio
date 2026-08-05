<template>
  <div class="yc-state" :class="{ 'yc-state--compact': compact }">
    <div class="yc-state__icon"><Icon :name="icon" :size="26" /></div>
    <h3 class="yc-state__title">{{ title }}</h3>
    <p class="yc-state__desc">{{ desc }}</p>
    <div v-if="$slots.actions" class="yc-state__actions yc-row">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'

defineProps({
  icon: { type: String, default: 'inbox' },
  title: { type: String, default: '这里还什么都没有' },
  desc: { type: String, default: '' },
  compact: { type: Boolean, default: false }
})
</script>

<style scoped>
.yc-state--compact { padding: var(--sp-8) var(--sp-4); }
.yc-state--compact .yc-state__icon { width: 44px; height: 44px; }
.yc-state--compact .yc-state__title { font-size: var(--fs-h3); }
.yc-state__actions { margin-top: var(--sp-2); }
</style>
