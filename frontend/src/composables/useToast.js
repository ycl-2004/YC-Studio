import { reactive } from 'vue'

const state = reactive({ items: [] })
let seq = 0

export function useToast() {
  function push(message, type = 'success') {
    const id = ++seq
    state.items.push({ id, message, type })
    setTimeout(() => dismiss(id), 3400)
    return id
  }
  function dismiss(id) {
    const i = state.items.findIndex((t) => t.id === id)
    if (i >= 0) state.items.splice(i, 1)
  }
  return { state, push, dismiss }
}
