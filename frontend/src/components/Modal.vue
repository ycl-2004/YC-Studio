<template>
  <Teleport to="body">
    <transition name="yc-fade">
      <div v-if="open" class="yc-overlay" @click.self="$emit('close')">
        <div class="yc-modal" role="dialog" aria-modal="true">
          <div class="yc-modal__head yc-row yc-row--between">
            <h2 class="yc-modal__title">{{ title }}</h2>
            <button class="yc-btn--icon" aria-label="关闭" @click="$emit('close')">
              <Icon name="x" :size="18" />
            </button>
          </div>
          <div class="yc-modal__body">
            <slot />
          </div>
          <div v-if="$slots.footer" class="yc-modal__foot yc-row yc-row--between">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import Icon from './Icon.vue'

defineProps({ open: { type: Boolean, default: false }, title: { type: String, default: '' } })
defineEmits(['close'])
</script>

<style scoped>
.yc-modal__head { margin-bottom: var(--sp-4); }
.yc-modal__title { font-size: var(--fs-h3); font-family: var(--font-serif); color: var(--ink); }
.yc-modal__body { color: var(--ink-muted); font-size: var(--fs-small); line-height: 1.7; }
.yc-modal__foot { margin-top: var(--sp-6); }
</style>
