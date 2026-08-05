<template>
  <div class="shell" :class="{ 'shell--nav-open': navOpen }">
    <Sidebar :open="navOpen" @close="navOpen = false" />

    <div v-if="navOpen" class="shell__scrim" @click="navOpen = false"></div>

    <div class="shell__main">
      <TopBar @toggle="navOpen = !navOpen" />

      <!-- The single scroll container of the app. Nothing above or below it
           scrolls, so sticky panels inside pages pin against this scrollport. -->
      <main ref="scroller" class="shell__scroll">
        <div class="shell__inner">
          <router-view v-slot="{ Component }">
            <transition name="page" mode="out-in">
              <component :is="Component" />
            </transition>
          </router-view>
        </div>
      </main>
    </div>

    <Toaster />
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import Sidebar from '@/components/Sidebar.vue'
import TopBar from '@/components/TopBar.vue'
import Toaster from '@/components/Toaster.vue'

const navOpen = ref(false)
const scroller = ref(null)
const route = useRoute()

/* The document never scrolls, so the router's scrollBehavior cannot reset the
   view on navigation — do it on the real scrollport instead. */
watch(() => route.fullPath, () => {
  if (scroller.value) scroller.value.scrollTop = 0
})
</script>

<style scoped>
.shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--cream);
}
@supports (height: 100dvh) { .shell { height: 100dvh; } }

.shell__main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.shell__scroll {
  flex: 1 1 auto;
  min-height: 0;          /* without this a flex child refuses to shrink and the scroll dies */
  overflow-y: auto;
  overflow-x: hidden;
}

.shell__inner {
  max-width: 1280px;
  width: 100%;
  margin: 0 auto;
  padding: var(--sp-8) var(--sp-8) var(--sp-16);
}

.shell__scrim { display: none; }

.page-enter-active, .page-leave-active { transition: opacity var(--dur-base) var(--ease-out), transform var(--dur-base) var(--ease-out); }
.page-enter-from { opacity: 0; transform: translateY(8px); }
.page-leave-to { opacity: 0; transform: translateY(-8px); }

@media (prefers-reduced-motion: reduce) {
  .page-enter-active, .page-leave-active { transition: none; }
}

@media (max-width: 900px) {
  .shell__scrim {
    display: block; position: fixed; inset: 0; background: rgba(21,24,33,.42);
    z-index: 55;
  }
  .shell__inner { padding: var(--sp-4) var(--sp-4) var(--sp-12); }
}
</style>
