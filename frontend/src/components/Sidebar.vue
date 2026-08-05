<template>
  <aside class="sb" :class="{ 'sb--open': open }">
    <div class="sb__brand">
      <div class="sb__mark" aria-hidden="true">YC</div>
      <div class="sb__brand-text">
        <strong>YC Studio</strong>
        <span class="yc-eyebrow">内容生成工作台</span>
      </div>
    </div>

    <nav class="sb__nav">
      <div v-for="g in groups" :key="g.label" class="sb__group">
        <p class="sb__group-label">{{ g.label }}</p>
        <router-link
          v-for="item in g.items"
          :key="item.to"
          :to="item.to"
          class="sb__item"
          @click="$emit('close')"
        >
          <Icon :name="item.icon" :size="19" />
          <span>{{ item.label }}</span>
        </router-link>
      </div>
    </nav>

    <div class="sb__foot">
      <div class="sb__tip">
        <Icon name="sparkles" :size="15" />
        <p>上传资料 → 聊出选题 → 生成 → 发布回填，<br />飞轮自动回流高表现内容。</p>
      </div>
      <p class="sb__ver"><span class="yc-mono">v0.1</span></p>
    </div>
  </aside>
</template>

<script setup>
import Icon from './Icon.vue'

defineProps({ open: { type: Boolean, default: false } })
defineEmits(['close'])

const groups = [
  {
    label: '知识资产',
    items: [
      { to: '/kb', label: '知识库管理', icon: 'library' },
      { to: '/config', label: '输出配置', icon: 'sliders' }
    ]
  },
  {
    label: '创作流',
    items: [
      { to: '/studio', label: '生成工作台', icon: 'spark' },
      { to: '/library', label: '内容库', icon: 'doc' }
    ]
  },
  {
    label: '复盘',
    items: [
      { to: '/dashboard', label: '复盘看板', icon: 'chart' }
    ]
  }
]
</script>

<style scoped>
.sb {
  width: 248px;
  flex: 0 0 248px;
  background: var(--paper);
  border-right: 1px solid var(--border-default);
  display: flex;
  flex-direction: column;
  height: 100%;
}
.sb__brand {
  display: flex; align-items: center; gap: var(--sp-3);
  padding: var(--sp-6) var(--sp-6) var(--sp-6);
}
.sb__mark {
  font-family: var(--font-serif); font-weight: 900; font-size: 1.4rem;
  letter-spacing: -.04em; line-height: 1; white-space: nowrap;
  color: #fff; background: var(--wine); width: 44px; height: 44px;
  border-radius: 12px; display: grid; place-items: center;
  box-shadow: var(--sh-wine); letter-spacing: -.04em;
}
.sb__brand-text { display: flex; flex-direction: column; gap: 2px; }
.sb__brand-text strong { font-family: var(--font-serif); font-size: 1.05rem; color: var(--ink); }
.sb__nav { flex: 1 1 auto; min-height: 0; overflow-y: auto; padding: 0 var(--sp-4) var(--sp-4); }
.sb__group { margin-bottom: var(--sp-6); }
.sb__group:last-child { margin-bottom: 0; }
.sb__group-label {
  font-size: var(--fs-caption); letter-spacing: var(--tracking-caption);
  text-transform: uppercase; color: var(--ink-faint);
  padding: 0 var(--sp-3); margin: 0 0 var(--sp-2);
}
.sb__item {
  display: flex; align-items: center; gap: var(--sp-3);
  padding: 10px var(--sp-3); border-radius: var(--r-control);
  color: var(--ink-muted); font-size: var(--fs-small); font-weight: 500;
  text-decoration: none; position: relative;
  transition: background var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out);
}
.sb__item:hover { background: var(--cream-deep); color: var(--ink); text-decoration: none; }
.sb__item.router-link-active {
  background: var(--denim-50); color: var(--denim-deep); font-weight: 700;
}
.sb__item.router-link-active::before {
  content: ""; position: absolute; left: -4px; top: 8px; bottom: 8px;
  width: 4px; border-radius: var(--r-pill); background: var(--wine);
}
.sb__foot {
  flex: 0 0 auto;
  padding: var(--sp-4) var(--sp-6) var(--sp-6);
  background: var(--paper);
  border-top: 1px solid var(--border-subtle);
}
.sb__tip { display: flex; gap: var(--sp-2); color: var(--ink-faint); font-size: var(--fs-caption); line-height: 1.7; }
.sb__tip :deep(svg) { color: var(--blush); flex: 0 0 auto; margin-top: 3px; }
.sb__tip p { margin: 0; }
.sb__ver { font-size: var(--fs-caption); color: var(--n-400); margin: var(--sp-3) 0 0; letter-spacing: .02em; }

@media (max-width: 900px) {
  .sb {
    position: fixed; left: 0; top: 0; z-index: 60;
    transform: translateX(-100%);
    transition: transform var(--dur-base) var(--ease-out);
    box-shadow: var(--sh-md);
  }
  .sb--open { transform: translateX(0); }
}
@media (prefers-reduced-motion: reduce) {
  .sb { transition: none; }
}
</style>
