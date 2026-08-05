<template>
  <header class="topbar">
    <button class="topbar__menu yc-btn--icon" @click="$emit('toggle')" aria-label="菜单">
      <Icon name="menu" :size="20" />
    </button>

    <nav class="topbar__crumb" aria-label="breadcrumb">
      <span class="topbar__crumb-root">YC Studio</span>
      <Icon name="chevron" :size="14" />
      <span class="topbar__crumb-page">{{ title }}</span>
    </nav>

    <div class="topbar__spacer"></div>

    <div class="topbar__search">
      <Icon name="search" :size="16" />
      <input class="topbar__search-input" type="search" placeholder="搜索内容、选题、文档…" aria-label="全局搜索" />
    </div>

    <button class="topbar__icon yc-btn--icon" aria-label="通知">
      <Icon name="bell" :size="19" />
      <span class="topbar__dot"></span>
    </button>

    <div class="topbar__user">
      <div class="topbar__avatar">Y</div>
      <div class="topbar__user-text">
        <strong>林羿辰</strong>
        <span>创作者 · Pro</span>
      </div>
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import Icon from './Icon.vue'

defineEmits(['toggle'])
const route = useRoute()
const title = computed(() => route.meta.title || '工作台')
</script>

<style scoped>
/* Sits above the scroll container, so it needs no sticky positioning —
   it is structurally fixed by the shell's flex column. */
.topbar {
  height: var(--topbar-h); flex: 0 0 var(--topbar-h);
  background: var(--paper);
  border-bottom: 1px solid var(--border-default);
  display: flex; align-items: center; gap: var(--sp-3);
  padding: 0 var(--sp-6);
  z-index: 40;
}
.topbar__menu { display: none; }
.topbar__crumb { display: flex; align-items: center; gap: var(--sp-2); font-size: var(--fs-small); }
.topbar__crumb-root { color: var(--ink-faint); }
.topbar__crumb :deep(.yc-icon) { color: var(--n-400); }
.topbar__crumb-page { font-family: var(--font-serif); font-weight: 700; color: var(--ink); }
.topbar__spacer { flex: 1; }
.topbar__search {
  display: flex; align-items: center; gap: var(--sp-2);
  background: var(--cream-deep); border: 1px solid var(--border-default);
  border-radius: var(--r-pill); padding: 8px 14px; min-width: 240px;
  color: var(--ink-faint);
}
.topbar__search:focus-within { border-color: var(--denim); box-shadow: 0 0 0 3px rgba(59,110,165,.16); }
.topbar__search-input { border: 0; background: transparent; outline: none; font-family: var(--font-sans); font-size: var(--fs-small); color: var(--ink); width: 100%; }
.topbar__icon { position: relative; }
.topbar__dot { position: absolute; top: 6px; right: 7px; width: 8px; height: 8px; border-radius: 50%; background: var(--blush); border: 2px solid var(--paper); }
.topbar__user { display: flex; align-items: center; gap: var(--sp-2); padding-left: var(--sp-3); border-left: 1px solid var(--border-subtle); }
.topbar__avatar { width: 36px; height: 36px; border-radius: 50%; background: var(--wine); color: #fff; display: grid; place-items: center; font-family: var(--font-serif); font-weight: 900; }
.topbar__user-text { display: flex; flex-direction: column; line-height: 1.2; }
.topbar__user-text strong { font-size: var(--fs-small); color: var(--ink); }
.topbar__user-text span { font-size: var(--fs-caption); color: var(--ink-faint); }

@media (max-width: 900px) {
  .topbar__menu { display: inline-flex; }
  .topbar__search { display: none; }
  .topbar__user-text { display: none; }
  .topbar__crumb-root { display: none; }
}
</style>
