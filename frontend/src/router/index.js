import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/kb' },
  {
    path: '/',
    component: () => import('@/layout/AppShell.vue'),
    children: [
      {
        path: 'kb',
        name: 'kb',
        component: () => import('@/pages/KnowledgeBase.vue'),
        meta: { title: '知识库管理', group: 'knowledge' }
      },
      {
        path: 'config',
        name: 'config',
        component: () => import('@/pages/OutputConfig.vue'),
        meta: { title: '输出配置', group: 'knowledge' }
      },
      {
        path: 'studio',
        name: 'studio',
        component: () => import('@/pages/Studio.vue'),
        meta: { title: '生成工作台', group: 'create' }
      },
      {
        path: 'library',
        name: 'library',
        component: () => import('@/pages/ContentLibrary.vue'),
        meta: { title: '内容库', group: 'create' }
      },
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/pages/Dashboard.vue'),
        meta: { title: '复盘看板', group: 'review' }
      },
    ]
  },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/pages/NotFound.vue') }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 })
})

export default router
