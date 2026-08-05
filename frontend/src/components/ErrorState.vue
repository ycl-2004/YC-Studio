<template>
  <div class="yc-state yc-state--error">
    <div class="yc-state__icon"><Icon name="alert" :size="26" /></div>
    <h3 class="yc-state__title">{{ title }}</h3>
    <p class="yc-state__desc">{{ desc }}</p>
    <p v-if="code" class="yc-state__code yc-mono">错误码 {{ code }}</p>
    <div class="yc-state__actions yc-row">
      <button class="yc-btn yc-btn--wine yc-btn--sm" @click="$emit('retry')">
        <Icon name="refresh" :size="15" /> 重试
      </button>
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'

defineProps({
  title: { type: String, default: '加载失败了' },
  desc: { type: String, default: '数据未能加载，请稍后重试。' },
  code: { type: String, default: '' }
})
defineEmits(['retry'])
</script>

<style scoped>
.yc-state__code {
  margin: 0; font-size: var(--fs-caption); color: var(--ink-faint);
  background: var(--n-100); padding: 3px 10px; border-radius: var(--r-pill);
}
</style>
