<template>
  <Teleport to="body">
    <transition name="yc-fade">
      <div v-if="open" class="yc-overlay yc-overlay--drawer" @click.self="$emit('close')">
        <div class="yc-drawer" role="dialog" aria-modal="true">
          <div class="yc-drawer__head yc-row yc-row--between">
            <div>
              <span class="yc-eyebrow">{{ eyebrow }}</span>
              <h2 class="yc-drawer__title">{{ title }}</h2>
            </div>
            <button class="yc-btn--icon" aria-label="关闭" @click="$emit('close')">
              <Icon name="x" :size="18" />
            </button>
          </div>
          <div class="yc-drawer__body">
            <slot />
          </div>
          <div v-if="$slots.footer" class="yc-drawer__foot">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<script setup>
import Icon from './Icon.vue'

defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '' },
  eyebrow: { type: String, default: '' }
})
defineEmits(['close'])
</script>

<style scoped>
.yc-overlay--drawer { place-items: stretch; justify-content: flex-end; padding: 0; }
.yc-drawer__head { padding: var(--sp-6) var(--sp-6) var(--sp-4); border-bottom: 1px solid var(--border-subtle); gap: var(--sp-3); }
.yc-drawer__title { font-family: var(--font-serif); font-size: var(--fs-h3); color: var(--ink); margin-top: 4px; }
.yc-drawer__body { padding: var(--sp-6); overflow-y: auto; flex: 1; color: var(--ink-muted); font-size: var(--fs-small); line-height: 1.7; }
.yc-drawer__foot { padding: var(--sp-4) var(--sp-6); border-top: 1px solid var(--border-subtle); display: flex; gap: var(--sp-2); justify-content: flex-end; }
</style>
