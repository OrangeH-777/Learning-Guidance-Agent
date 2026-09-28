import { createRouter, createWebHistory } from 'vue-router'
import { restoreSession, session } from '../api/session'
import AuthView from '../views/AuthView.vue'
import DashboardView from '../views/DashboardView.vue'
import HistoryView from '../views/HistoryView.vue'
import ModelsView from '../views/ModelsView.vue'
import ProfileView from '../views/ProfileView.vue'
import ResourceView from '../views/ResourceView.vue'
import MaterialsView from '../views/MaterialsView.vue'

export const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    if (to.path === from.path) return false
    return { top: 0 }
  },
  routes: [
    { path: '/login', component: AuthView, meta: { public: true } },
    { path: '/', component: DashboardView },
    { path: '/profile', component: ProfileView },
    { path: '/models', component: ModelsView },
    { path: '/history', component: HistoryView },
    { path: '/resources/:id', component: ResourceView },
    { path: '/admin/materials', component: MaterialsView, meta: { admin: true } },
  ],
})

router.beforeEach(async to => {
  if (!session.checked) {
    try { await restoreSession() } catch { if (!to.meta.public) return '/login' }
  }
  if (!to.meta.public && !session.user) return '/login'
  if (to.meta.admin && !session.user?.is_admin) return '/'
  if (to.path === '/login' && session.user) return '/'
})
