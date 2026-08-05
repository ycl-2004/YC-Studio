<template>
  <div class="dt">
    <!-- ERROR STATE -->
    <ErrorState
      v-if="error"
      :title="errorTitle"
      :desc="error && error.message ? error.message : '数据加载失败，请重试。'"
      :code="error && error.code ? error.code : ''"
      @retry="$emit('retry')"
    >
      <template #actions><slot name="error-actions" /></template>
    </ErrorState>

    <!-- TABLE (loading shows skeleton, empty shows empty state) -->
    <div v-else class="yc-table-wrap">
      <table class="yc-table">
        <thead>
          <tr>
            <th v-if="selectable" class="dt__check">
              <input type="checkbox" :checked="allOnPage" :indeterminate="someOnPage" @change="toggleAll" aria-label="全选" />
            </th>
            <th
              v-for="col in columns"
              :key="col.key"
              :style="{ width: col.width, textAlign: col.align || 'left' }"
            >{{ col.label }}</th>
            <th v-if="$slots.actions" class="dt__actions-h"></th>
          </tr>
        </thead>

        <tbody v-if="loading">
          <tr v-for="i in pageSize" :key="'sk' + i">
            <td v-if="selectable" class="dt__check"><Skeleton variant="circle" width="16px" /></td>
            <td v-for="col in columns" :key="col.key"><Skeleton :width="col.skelW || '80%'" /></td>
            <td v-if="$slots.actions"></td>
          </tr>
        </tbody>

        <tbody v-else-if="rows.length === 0">
          <tr>
            <td :colspan="totalCols">
              <EmptyState :icon="emptyIcon" :title="emptyTitle" :desc="emptyDesc" :compact="true">
                <template #actions><slot name="empty-actions" /></template>
              </EmptyState>
            </td>
          </tr>
        </tbody>

        <tbody v-else>
          <tr
            v-for="row in pagedRows"
            :key="keyOf(row)"
            :class="{ 'dt__row--sel': isSelected(row) }"
            @click="$emit('row-click', row)"
          >
            <td v-if="selectable" class="dt__check" @click.stop>
              <input type="checkbox" :checked="isSelected(row)" @change="toggleRow(row)" :aria-label="`选择 ${keyOf(row)}`" />
            </td>
            <td
              v-for="col in columns"
              :key="col.key"
              :style="{ textAlign: col.align || 'left', width: col.width }"
            >
              <slot :name="'cell-' + col.key" :row="row" :value="row[col.key]">{{ row[col.key] }}</slot>
            </td>
            <td v-if="$slots.actions" class="dt__actions" @click.stop>
              <div class="row-actions"><slot name="actions" :row="row" /></div>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- PAGINATION -->
      <div v-if="!loading && rows.length > 0 && pageCount > 1" class="dt__pager yc-row yc-row--between">
        <span class="dt__count">共 {{ rows.length }} 条 · 第 {{ page }} / {{ pageCount }} 页</span>
        <div class="dt__pager-ctrls yc-row">
          <button class="yc-btn--icon" :disabled="page === 1" @click="page--" aria-label="上一页"><Icon name="chevron" :size="16" style="transform:rotate(90deg)" /></button>
          <button
            v-for="p in pageCount"
            :key="p"
            class="dt__page"
            :class="{ 'is-active': p === page }"
            @click="page = p"
          >{{ p }}</button>
          <button class="yc-btn--icon" :disabled="page === pageCount" @click="page++" aria-label="下一页"><Icon name="chevron" :size="16" style="transform:rotate(-90deg)" /></button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, useSlots } from 'vue'
import Icon from './Icon.vue'
import Skeleton from './Skeleton.vue'
import EmptyState from './EmptyState.vue'
import ErrorState from './ErrorState.vue'

const props = defineProps({
  columns: { type: Array, required: true },
  rows: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: [Object, null], default: null },
  rowKey: { type: String, default: 'id' },
  pageSize: { type: Number, default: 8 },
  selectable: { type: Boolean, default: false },
  emptyTitle: { type: String, default: '这里还什么都没有' },
  emptyDesc: { type: String, default: '' },
  emptyIcon: { type: String, default: 'inbox' },
  errorTitle: { type: String, default: '加载失败' }
})
const emit = defineEmits(['retry', 'row-click', 'selection-change'])

const slots = useSlots()
const page = ref(1)
const selected = ref(new Set())

const totalCols = computed(() => props.columns.length + (props.selectable ? 1 : 0) + (slots.actions ? 1 : 0))
const pageCount = computed(() => Math.max(1, Math.ceil(props.rows.length / props.pageSize)))
const pagedRows = computed(() => props.rows.slice((page.value - 1) * props.pageSize, page.value * props.pageSize))

watch(() => props.rows, () => { page.value = 1; pruneSelection() })
watch(() => props.selectable, (v) => { if (!v) selected.value = new Set() })

function keyOf(row) { return row[props.rowKey] }
function isSelected(row) { return selected.value.has(keyOf(row)) }
function pruneSelection() {
  const ids = new Set(props.rows.map(keyOf))
  for (const k of [...selected.value]) if (!ids.has(k)) selected.value.delete(k)
  emitSelection()
}
function emitSelection() { emit('selection-change', [...selected.value]) }
function toggleRow(row) {
  const k = keyOf(row)
  if (selected.value.has(k)) selected.value.delete(k)
  else selected.value.add(k)
  selected.value = new Set(selected.value)
  emitSelection()
}
const allOnPage = computed(() => pagedRows.value.length > 0 && pagedRows.value.every(isSelected))
const someOnPage = computed(() => pagedRows.value.some(isSelected) && !allOnPage.value)
function toggleAll(e) {
  const checked = e.target.checked
  for (const row of pagedRows.value) {
    const k = keyOf(row)
    if (checked) selected.value.add(k)
    else selected.value.delete(k)
  }
  selected.value = new Set(selected.value)
  emitSelection()
}
</script>

<style scoped>
.dt { width: 100%; }
.dt__check { width: 40px; text-align: center; }
.dt__check input, .dt__row--sel { }
tr.dt__row--sel { background: var(--denim-50); }
.dt__actions-h, .dt__actions { width: 88px; }
.dt__actions { padding-right: var(--sp-4); }
.dt__pager { padding: var(--sp-3) var(--sp-2) 0; flex-wrap: wrap; gap: var(--sp-3); }
.dt__count { font-size: var(--fs-caption); color: var(--ink-faint); font-family: var(--font-code); }
.dt__pager-ctrls { gap: 6px; }
.dt__page {
  min-width: 30px; height: 30px; border-radius: var(--r-control);
  border: 1px solid var(--border-default); background: var(--paper);
  font-size: var(--fs-caption); color: var(--ink-muted); font-family: var(--font-code);
  transition: all var(--dur-fast) var(--ease-out);
}
.dt__page:hover { border-color: var(--denim); color: var(--denim-deep); }
.dt__page.is-active { background: var(--wine); color: #fff; border-color: var(--wine); }
input[type='checkbox'] { width: 16px; height: 16px; accent-color: var(--wine); cursor: pointer; }
</style>
