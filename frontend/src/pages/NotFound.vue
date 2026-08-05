<template>
  <div class="nf">
    <div class="nf__card yc-card">
      <div class="nf__code yc-num">404</div>
      <span class="yc-eyebrow">页面走丢了</span>
      <h1 class="nf__title">这里没有内容</h1>
      <p class="nf__desc">你访问的页面不存在，或尚未生成。回到工作台继续创作吧。</p>
      <div class="nf__actions">
        <router-link to="/kb" class="yc-btn yc-btn--wine"><Icon name="arrow" :size="15" /> 回到知识库</router-link>
        <router-link to="/studio" class="yc-btn yc-btn--ghost"><Icon name="spark" :size="15" /> 去生成工作台</router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import Icon from '@/components/Icon.vue'
</script>

<style scoped>
.nf { min-height: 70vh; display: grid; place-items: center; padding: var(--sp-6); }
.nf__card { padding: var(--sp-12); text-align: center; max-width: 480px; }
.nf__code { font-size: 4rem; color: var(--wine); line-height: 1; }
.nf__title { font-family: var(--font-serif); font-size: var(--fs-section); color: var(--ink); margin: var(--sp-2) 0; }
.nf__desc { color: var(--ink-muted); font-size: var(--fs-small); margin: 0 0 var(--sp-6); }
.nf__actions { display: flex; gap: var(--sp-3); justify-content: center; flex-wrap: wrap; }
</style>
