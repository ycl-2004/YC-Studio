<template>
  <div class="toaster" aria-live="polite">
    <transition-group name="toast">
      <div v-for="t in state.items" :key="t.id" class="toast" :class="`toast--${t.type}`" @click="dismiss(t.id)">
        <Icon :name="t.type === 'error' ? 'alert' : t.type === 'info' ? 'bell' : 'checkcircle'" :size="17" />
        <span>{{ t.message }}</span>
      </div>
    </transition-group>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
import { useToast } from '@/composables/useToast'

const { state, dismiss } = useToast()
</script>

<style scoped>
.toaster {
  position: fixed; right: var(--sp-6); bottom: var(--sp-6); z-index: 90;
  display: flex; flex-direction: column; gap: var(--sp-2); max-width: 360px;
}
.toast {
  display: flex; align-items: center; gap: var(--sp-2);
  background: var(--paper); border: 1px solid var(--border-default);
  border-left: 4px solid var(--success); border-radius: var(--r-content);
  padding: 12px 16px; font-size: var(--fs-small); color: var(--ink);
  box-shadow: var(--sh-sm); cursor: pointer;
}
.toast--success { border-left-color: var(--success); }
.toast--success :deep(svg) { color: var(--success-deep); }
.toast--error { border-left-color: var(--error); }
.toast--error :deep(svg) { color: var(--error-deep); }
.toast--info { border-left-color: var(--denim); }
.toast--info :deep(svg) { color: var(--denim-deep); }
.toast-enter-active, .toast-leave-active { transition: all var(--dur-base) var(--ease-out); }
.toast-enter-from { opacity: 0; transform: translateX(20px); }
.toast-leave-to { opacity: 0; transform: translateX(20px); }
</style>
