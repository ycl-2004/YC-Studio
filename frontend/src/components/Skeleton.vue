<template>
  <span class="yc-skel" :style="style" :class="{ 'yc-skel--circle': variant === 'circle' }"></span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  variant: { type: String, default: 'text' }, // text | block | circle
  width: { type: String, default: '100%' },
  height: { type: String, default: '14px' }
})

const style = computed(() => {
  if (props.variant === 'circle') {
    const s = props.width
    return { width: s, height: s, borderRadius: '50%' }
  }
  return { width: props.width, height: props.height, borderRadius: props.variant === 'block' ? 'var(--r-content)' : 'var(--r-control)' }
})
</script>
