import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'

/**
 * Generic async state composable. Respects a global ?demo= query override so
 * any page can be forced into loading / error for QA (or naturally shows empty
 * when the data array is empty). Each page passes `empty` into its fetcher.
 */
export function useAsync(fetcher, { immediate = true, initial = null } = {}) {
  const data = ref(initial)
  const loading = ref(false)
  const error = ref(null)
  const route = useRoute()
  const demo = computed(() => route.query.demo)

  async function run() {
    if (demo.value === 'loading') {
      loading.value = true
      error.value = null
      return
    }
    if (demo.value === 'error') {
      loading.value = false
      error.value = Object.assign(new Error('演示错误：知识库服务暂时不可用（HTTP 503）。请检查后端连接后重试。'), {
        code: 'SERVICE_UNAVAILABLE'
      })
      return
    }
    loading.value = true
    error.value = null
    try {
      data.value = await fetcher()
    } catch (e) {
      error.value = e
    } finally {
      if (demo.value !== 'loading') loading.value = false
    }
  }

  if (immediate) onMounted(run)

  return { data, loading, error, reload: run, demo }
}

export function isDemo(kind) {
  const route = useRoute()
  return computed(() => route.query.demo === kind)
}
