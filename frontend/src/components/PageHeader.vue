<template>
  <header class="ph">
    <div class="ph__top">
      <div class="ph__text">
        <span v-if="eyebrow" class="yc-eyebrow">{{ eyebrow }}</span>
        <h1 class="ph__title">{{ title }}</h1>
        <p v-if="desc" class="ph__desc">{{ desc }}</p>
      </div>
      <div v-if="$slots.actions" class="ph__actions">
        <slot name="actions" />
      </div>
    </div>
    <div class="ph__rule" aria-hidden="true"></div>
  </header>
</template>

<script setup>
defineProps({
  eyebrow: { type: String, default: '' },
  title: { type: String, required: true },
  desc: { type: String, default: '' }
})
</script>

<style scoped>
.ph { margin-bottom: var(--sp-6); }
.ph__top {
  display: flex; align-items: flex-end; justify-content: space-between;
  gap: var(--sp-6); flex-wrap: wrap;
}
.ph__text { display: flex; flex-direction: column; gap: var(--sp-2); max-width: 62ch; }
.ph__title {
  font-size: var(--fs-section); font-weight: 700; color: var(--ink);
  letter-spacing: -.015em; margin-top: 2px;
}
.ph__desc { margin: 2px 0 0; color: var(--ink-muted); font-size: var(--fs-small); line-height: 1.75; }
.ph__actions { display: flex; align-items: center; gap: var(--sp-2); flex-wrap: wrap; padding-bottom: 4px; }

/* structural hairline — wine at the anchor, fading out to the right */
.ph__rule {
  height: 1px; margin-top: 20px;
  background: linear-gradient(90deg, var(--wine-300) 0, var(--border-subtle) 22%, transparent 78%);
}

@media (max-width: 700px) {
  .ph__top { align-items: flex-start; }
  .ph__actions { padding-bottom: 0; }
}
</style>
