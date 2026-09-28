import { createRouter, createWebHistory } from 'vue-router'
import { restoreSession, session } from '../api/session'
import AuthView from '../views/AuthView.vue'
import DashboardView from '../views/DashboardView.vue'
import HistoryView from '../views/HistoryView.vue'
import ModelsView from '../views/ModelsView.vue'
import ProfileView from '../views/ProfileView.vue'
import ResourceView from '../views/ResourceView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: AuthView, meta: { public: true } },
    { path: '/', component: DashboardView },
    { path: '/profile', component: ProfileView },
    { path: '/models', component: ModelsView },
    { path: '/history', component: HistoryView },
    { path: '/resources/:id', component: ResourceView },
  ],
})

router.beforeEach(async to => {
  if (!session.checked) {
    try { await restoreSession() } catch { if (!to.meta.public) return '/login' }
  }
  if (!to.meta.public && !session.user) return '/login'
  if (to.path === '/login' && session.user) return '/'
})
